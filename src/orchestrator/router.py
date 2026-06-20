"""模型路由 - 根据任务复杂度选择不同级别的LLM"""

from enum import Enum
from typing import Any


class ModelTier(Enum):
    """模型级别"""
    FREE = "free"            # 规则引擎，0成本
    CHEAP = "cheap"          # Qwen，低成本
    STANDARD = "standard"    # DeepSeek-V3，主力模型


class ModelRouter:
    """根据任务类型智能路由到不同模型

    三级路由策略：
    - FREE: 确定性规则检查（正则、AST）
    - CHEAP: 简单风格检查、命名规范
    - STANDARD: 复杂逻辑推理、跨文件分析
    """

    ROUTING_RULES = {
        "security_hardcoded": ModelTier.FREE,
        "security_injection": ModelTier.FREE,
        "style_basic": ModelTier.FREE,
        "style_naming": ModelTier.CHEAP,
        "style_complex": ModelTier.CHEAP,
        "bug_local": ModelTier.STANDARD,
        "bug_cross_file": ModelTier.STANDARD,
        "performance_simple": ModelTier.CHEAP,
        "performance_complex": ModelTier.STANDARD,
        "acceptance": ModelTier.CHEAP,
    }

    @classmethod
    def route(cls, task_type: str) -> ModelTier:
        """根据任务类型返回模型级别"""
        return cls.ROUTING_RULES.get(task_type, ModelTier.STANDARD)

    @classmethod
    def get_model_name(cls, task_type: str) -> str:
        """获取具体模型名称"""
        tier = cls.route(task_type)
        mapping = {
            ModelTier.FREE: "rule_engine",
            ModelTier.CHEAP: "qwen-turbo",
            ModelTier.STANDARD: "deepseek-chat",
        }
        return mapping[tier]
