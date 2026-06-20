"""Agent基类 - 封装LLM调用、工具注册、Prompt模板"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from openai import APIStatusError

from src.utils.config import get_config
from src.utils.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class _NonRetryableError(Exception):
    """标记不可重试的错误（如 402 余额不足、401 认证失败）"""
    pass


class BaseAgent(ABC):
    """所有审查Agent的基类

    提供：
    - LLM调用封装（支持多模型切换）
    - 工具注册与调用
    - 重试与降级策略
    - Token成本追踪
    """

    def __init__(self, name: str, model: str = "deepseek-chat"):
        self.name = name
        self.model = model
        self.config = get_config()
        self.cost_tracker = CostTracker()
        self.tools: dict[str, callable] = {}

    def register_tool(self, name: str, func: callable) -> None:
        """注册Agent可调用的工具"""
        self.tools[name] = func
        logger.info(f"[{self.name}] 注册工具: {name}")

    def call_tool(self, tool_name: str, **kwargs) -> Any:
        """调用已注册的工具"""
        if tool_name not in self.tools:
            raise ValueError(f"未注册的工具: {tool_name}")
        return self.tools[tool_name](**kwargs)

    def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """调用LLM（带重试和降级）

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            model: 指定模型（None则使用默认）
            max_retries: 最大重试次数

        Returns:
            LLM响应的结构化结果

        Raises:
            RuntimeError: 所有重试失败时抛出
        """
        model_name = model or self.model
        last_error = None

        for attempt in range(max_retries):
            try:
                result = self._do_call(model_name, system_prompt, user_prompt)
                self.cost_tracker.record(
                    agent=self.name,
                    model=model_name,
                    tokens_input=result.get("usage", {}).get("prompt_tokens", 0),
                    tokens_output=result.get("usage", {}).get("completion_tokens", 0),
                )
                return result
            except _NonRetryableError:
                raise  # 4xx 客户端错误不重试，直接抛出
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[{self.name}] LLM调用失败 (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    model_name = self._downgrade_model(model_name)

        raise RuntimeError(f"[{self.name}] LLM调用全部重试失败: {last_error}")

    def _do_call(self, model: str, system_prompt: str, user_prompt: str) -> dict:
        """执行实际的LLM调用"""
        from openai import OpenAI

        timeout = self.config.get_timeout()

        client = OpenAI(
            api_key=self.config.get_api_key(model),
            base_url=self.config.get_api_base(model),
            timeout=timeout,
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
        except APIStatusError as e:
            if e.status_code == 402:
                raise _NonRetryableError(
                    f"[{self.name}] DeepSeek API 余额不足 (402)，请充值后重试"
                ) from e
            elif e.status_code == 401:
                raise _NonRetryableError(
                    f"[{self.name}] API Key 无效或已过期 (401)"
                ) from e
            elif 400 <= e.status_code < 500:
                raise _NonRetryableError(
                    f"[{self.name}] API 请求错误 ({e.status_code}): {e.body if hasattr(e, 'body') else str(e)}"
                ) from e
            raise  # 5xx 服务端错误交给上层重试

        return {
            "content": response.choices[0].message.content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        }

    def _downgrade_model(self, current_model: str) -> str:
        """模型降级策略"""
        downgrade_map = {
            "deepseek-chat": "qwen-turbo",
            "qwen-turbo": "qwen-turbo",  # 最低级别，不再降
        }
        return downgrade_map.get(current_model, "qwen-turbo")

    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取Agent的系统提示词"""
        pass

    @abstractmethod
    def review(self, state: Any) -> list[Any]:
        """执行审查，返回发现的问题列表"""
        pass
