"""Agent基类 - 封装LLM调用、工具注册、Prompt模板"""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from openai import APIStatusError

from src.utils.config import get_config
from src.utils.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class _NonRetryableError(Exception):
    """标记不可重试的错误（如 402 余额不足、401 认证失败）"""
    pass


class TokenBudgetExceeded(Exception):
    """Token 预算超限——调用方应捕获此异常，跳过该 Agent 而非杀进程"""
    pass


class BaseAgent(ABC):
    """所有审查Agent的基类

    提供：
    - LLM调用封装（支持多模型切换）
    - 工具注册与调用
    - 重试（指数退避）与降级策略
    - Token成本追踪
    - Dry-Run 模式（不调真实 LLM，返回 Mock 数据）
    - LLM 响应解析（JSON提取 + fallback正则兜底）
    - Finding 对象转换
    """

    def __init__(self, name: str, model: str = "deepseek-chat", dry_run: bool = False):
        self.name = name
        self.model = model
        self.dry_run = dry_run
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
        """调用LLM（带指数退避重试和模型降级）

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            model: 指定模型（None则使用默认）
            max_retries: 最大重试次数

        Returns:
            LLM响应的结构化结果

        Raises:
            RuntimeError: 所有重试失败时抛出
            TokenBudgetExceeded: Token 预算超限时抛出
        """
        # Dry-Run 模式：不调真实LLM
        if self.dry_run:
            return self._do_call_dry_run(system_prompt, user_prompt)

        # Token 预算检查（在调用前做一次估算，超限则立即阻断）
        budget = self.config.get_max_tokens()
        estimated = len(system_prompt) + len(user_prompt)
        if estimated > budget * 4:  # 1 字符 ≈ 0.25 token，超过 4 倍预算直接拒绝
            from src.utils.cost_tracker import CostTracker
            CostTracker().record(
                agent=self.name, model="budget_blocked",
                tokens_input=0, tokens_output=0,
            )
            raise TokenBudgetExceeded(
                f"[{self.name}] 输入过大 ({estimated} 字符，估算 ~{estimated // 4} tokens)"
                f"，超过预算上限 {budget} tokens，跳过此 Agent 审查"
            )

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
            except TokenBudgetExceeded:
                raise
            except _NonRetryableError:
                raise  # 4xx 客户端错误不重试，直接抛出
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[{self.name}] LLM调用失败 (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    # 指数退避：1s, 2s, 4s...
                    delay = 2 ** attempt
                    logger.info(f"[{self.name}] {delay}s 后重试...")
                    time.sleep(delay)
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

    def _do_call_dry_run(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        """Dry-Run 模式：不调真实 LLM，返回标准化 Mock 数据"""
        logger.info(f"[{self.name}] Dry-Run: 跳过 LLM 调用，返回 Mock 结果")

        # 不同 Agent 返回不同类别的 Mock 发现
        mock_responses = {
            "BugPerfAgent": json.dumps({
                "findings": [
                    {
                        "severity": "error", "category": "bug",
                        "file_path": "", "line": 1,
                        "message": "[DRY-RUN] 潜在的空指针引用",
                        "suggestion": "添加 None 检查",
                    },
                    {
                        "severity": "warning", "category": "performance",
                        "file_path": "", "line": 1,
                        "message": "[DRY-RUN] 循环内重复创建对象",
                        "suggestion": "提取到循环外",
                    },
                ],
                "handover": "Dry-run 模式，未执行真实审查",
            }),
            "StyleAcceptAgent": json.dumps({
                "findings": [
                    {
                        "severity": "info", "category": "style",
                        "file_path": "", "line": 1,
                        "message": "[DRY-RUN] 函数文档缺失",
                        "suggestion": "添加 docstring",
                    },
                ],
            }),
            "ArchitectAgent": json.dumps({
                "findings": [
                    {
                        "severity": "warning", "category": "architecture",
                        "file_path": "", "line": 1,
                        "message": "[DRY-RUN] 模块间循环依赖",
                        "suggestion": "重构为单向依赖",
                    },
                ],
            }),
            "SpecCheckAgent": json.dumps({
                "findings": [
                    {
                        "severity": "info", "category": "spec",
                        "file_path": "", "line": 1,
                        "message": "[DRY-RUN] 与 spec.md 的接口定义不一致",
                        "suggestion": "对齐接口命名",
                    },
                ],
            }),
        }

        content = mock_responses.get(
            self.name,
            json.dumps({"findings": [], "handover": "Dry-run"})
        )

        return {
            "content": content,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    # ---- 共享的 LLM 响应解析（所有 Agent 复用） ----

    _FINDING_FIELDS_RE = re.compile(
        r'"severity"\s*:\s*"(?P<severity>error|warning|info)"[^}]*?'
        r'"category"\s*:\s*"(?P<category>[^"]*)"[^}]*?'
        r'(?:"message"\s*:\s*"(?P<message>[^"]*)")?',
        re.DOTALL,
    )

    def parse_response(self, content: str, default_extra: str = "") -> dict:
        """解析 LLM 响应为结构化数据（带 fallback 正则兜底）

        解析策略：
        1. 尝试提取 ```json ... ``` 代码块
        2. 尝试提取 ``` ... ``` 代码块
        3. 尝试直接 JSON 解析
        4. Fallback：正则提取关键字段（不静默丢弃！）

        Args:
            content: LLM 原始响应文本
            default_extra: 解析失败时额外字段的默认值（如 "handover"）

        Returns:
            {"findings": [...], "handover": "..."} 或类似结构
        """
        json_str = None

        # 策略1-2：提取代码块中的 JSON
        if "```json" in content:
            try:
                start = content.index("```json") + 7
                end = content.index("```", start)
                json_str = content[start:end].strip()
            except ValueError:
                pass
        elif "```" in content:
            try:
                start = content.index("```") + 3
                end = content.index("```", start)
                candidate = content[start:end].strip()
                if candidate.startswith("{") or candidate.startswith("["):
                    json_str = candidate
            except ValueError:
                pass

        if not json_str:
            # 策略3：查找 JSON 对象
            brace_start = content.find("{")
            if brace_start >= 0:
                # 找到配对的 }
                depth = 0
                for i in range(brace_start, len(content)):
                    if content[i] == "{":
                        depth += 1
                    elif content[i] == "}":
                        depth -= 1
                        if depth == 0:
                            json_str = content[brace_start : i + 1]
                            break

        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # 策略4：Fallback — 正则提取 finding 字段，不全丢
        findings = []
        for m in self._FINDING_FIELDS_RE.finditer(content):
            findings.append({
                "severity": m.group("severity") or "warning",
                "category": m.group("category") or "bug",
                "file_path": "",
                "line": 0,
                "message": m.group("message") or "LLM 响应解析失败，请检查原始输出",
                "suggestion": "",
            })

        if findings:
            logger.warning(
                f"[{self.name}] JSON 解析失败，正则 fallback 提取了 {len(findings)} 条发现"
            )
        else:
            logger.error(
                f"[{self.name}] LLM 响应完全无法解析，内容前200字符: {content[:200]}"
            )

        return {"findings": findings, "handover": default_extra}

    def to_findings(
        self,
        raw_findings: list[dict],
        file_path: str,
        agent_source: str,
        default_category: str = "bug",
        default_severity: str = "warning",
    ) -> list:
        """将原始 dict 列表转换为 Finding 对象列表

        Args:
            raw_findings: LLM 返回的 finding dict 列表
            file_path: 当前审查的文件路径
            agent_source: 标记来源（如 "agent_a"）
            default_category: 默认分类
            default_severity: 默认严重度
        """
        from src.orchestrator.state import Finding

        result = []
        for f in raw_findings:
            result.append(Finding(
                severity=f.get("severity", default_severity),
                category=f.get("category", default_category),
                file_path=f.get("file_path", file_path),
                line=f.get("line", 0),
                message=f.get("message", ""),
                suggestion=f.get("suggestion", ""),
                agent_source=agent_source,
            ))
        return result

    def _build_dependency_context(
        self, file_path: str, dependency_graph: dict,
    ) -> str:
        """构建依赖关系上下文（公共 prompt 片段）"""
        parts = []
        dependents = dependency_graph.get("dependents", {}).get(file_path, [])
        if dependents:
            parts.append(f"依赖此文件的模块: {', '.join(dependents[:5])}")
        imports = dependency_graph.get("import_graph", {}).get(file_path, [])
        if imports:
            parts.append(f"此文件依赖的模块: {', '.join(imports[:5])}")
        return "\n".join(parts) if parts else ""

    def _build_skill_context(self, category: str) -> str:
        """构建 Skill 上下文（供 Agent 注入 prompt）"""
        try:
            from src.skills.skill_executor import SkillExecutor
            executor = SkillExecutor()
            return executor.build_skill_context_for_agent(category=category)
        except Exception as e:
            logger.debug(f"[{self.name}] Skill 上下文加载失败: {e}")
            return ""

    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取Agent的系统提示词"""
        pass

    @abstractmethod
    def review(self, state: Any) -> list[Any]:
        """执行审查，返回发现的问题列表"""
        pass
