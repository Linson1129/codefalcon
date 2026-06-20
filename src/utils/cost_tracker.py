"""Token成本追踪器"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class CostTracker:
    """Token消耗追踪（全局单例）

    记录每次LLM调用的Token消耗，支持按Agent和模型汇总
    """

    _instance = None

    # 各模型的Token价格（每1K tokens，美元）
    PRICING = {
        "deepseek-chat":     {"input": 0.00014, "output": 0.00028},
        "qwen-turbo":        {"input": 0.00005, "output": 0.00010},
        "rule_engine":       {"input": 0,       "output": 0},
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.records: list[dict] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def reset(self):
        """重置追踪器（每次审查开始时调用）"""
        self.records = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def record(self, agent: str, model: str, tokens_input: int, tokens_output: int):
        """记录一次LLM调用"""
        self.records.append({
            "agent": agent,
            "model": model,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
        })
        self.total_input_tokens += tokens_input
        self.total_output_tokens += tokens_output
        logger.debug(
            f"[CostTracker] {agent} ({model}): "
            f"input={tokens_input}, output={tokens_output}"
        )

    def get_summary(self) -> dict:
        """获取成本汇总"""
        summary = {
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": self._calculate_total_cost(),
            "by_agent": self._group_by_agent(),
        }
        return summary

    def _calculate_total_cost(self) -> float:
        """计算总成本（美元）"""
        total = 0.0
        for record in self.records:
            model = record["model"]
            if model in self.PRICING:
                pricing = self.PRICING[model]
                total += (
                    record["tokens_input"] * pricing["input"] / 1000
                    + record["tokens_output"] * pricing["output"] / 1000
                )
        return round(total, 6)

    def _group_by_agent(self) -> dict:
        """按Agent分组统计"""
        grouped = defaultdict(lambda: {"tokens": 0, "calls": 0})
        for record in self.records:
            agent = record["agent"]
            grouped[agent]["tokens"] += record["tokens_input"] + record["tokens_output"]
            grouped[agent]["calls"] += 1
        return dict(grouped)
