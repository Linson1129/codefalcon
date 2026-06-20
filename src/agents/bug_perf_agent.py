"""Agent A - Bug检测 + 性能分析"""

import json
import logging
from typing import Any

from .base import BaseAgent
from src.orchestrator.state import Finding, ReviewState

logger = logging.getLogger(__name__)


class BugPerfAgent(BaseAgent):
    """Agent A: 负责逻辑Bug检测和性能问题分析

    核心能力：
    - 局部逻辑Bug检测（空指针、未初始化变量、边界条件等）
    - 性能问题分析（循环内查询、不必要开销、算法复杂度）
    - 主动工具调用搜索相关代码段
    - 生成交接文档给Agent B
    """

    def __init__(self):
        super().__init__(name="AgentA_BugPerf", model="deepseek-chat")

    def get_system_prompt(self) -> str:
        return """你是一个专业的代码审查专家，专注于发现代码中的逻辑Bug和性能问题。

审查要点：
1. 逻辑Bug：
   - 空指针/None引用风险
   - 变量未初始化或作用域错误
   - 边界条件处理（空列表、零值、负数）
   - 异常处理缺失或不完整
   - 条件判断逻辑错误
   - 循环终止条件问题

2. 性能问题：
   - 循环内的重复计算或数据库查询
   - 不必要的内存分配
   - 算法复杂度偏高
   - 资源泄漏风险（文件句柄、连接未关闭）
   - 锁竞争或并发问题

输出格式（JSON）：
{
  "findings": [
    {
      "severity": "error|warning|info",
      "category": "bug|performance",
      "file_path": "...",
      "line": 88,
      "message": "简短描述问题",
      "suggestion": "修复建议"
    }
  ],
  "handover": "给Agent B的交接文档，描述发现的关键问题和可能影响风格审查的上下文"
}
"""

    def review(self, state: ReviewState) -> list[Finding]:
        """执行Bug和性能审查"""
        logger.info(f"[{self.name}] 开始审查 {len(state.target_files)} 个文件")

        findings = []

        for file_path, content in state.target_files.items():
            try:
                user_prompt = self._build_review_prompt(
                    file_path, content, state.related_code, state.dependency_graph
                )
                result = self.call_llm(
                    system_prompt=self.get_system_prompt(),
                    user_prompt=user_prompt,
                )

                parsed = self._parse_response(result.get("content", "{}"))
                findings.extend(self._to_findings(parsed.get("findings", []), file_path))

                # 保存交接文档到state供Agent B使用
                state.diff_context["agent_a_handover"] = parsed.get("handover", "")

            except Exception as e:
                logger.error(f"[{self.name}] 审查 {file_path} 失败: {e}")
                continue

        logger.info(f"[{self.name}] 审查完成，发现 {len(findings)} 个问题")
        return findings

    def _build_review_prompt(
        self, file_path: str, content: str,
        related_code: dict[str, list[str]],
        dependency_graph: dict,
    ) -> str:
        """构建审查提示词（含代码调用关系 + 依赖上下文）"""
        prompt_parts = [f"请审查以下文件: {file_path}\n"]
        prompt_parts.append(f"```\n{content}\n```\n")

        # 调用关系
        if file_path in related_code and related_code[file_path]:
            prompt_parts.append("相关代码调用关系:")
            for snippet in related_code[file_path][:5]:
                prompt_parts.append(f"- {snippet}")

        # 依赖关系
        dependents = dependency_graph.get("dependents", {}).get(file_path, [])
        if dependents:
            prompt_parts.append(f"\n依赖此文件的模块: {', '.join(dependents[:5])}")
        imports = dependency_graph.get("import_graph", {}).get(file_path, [])
        if imports:
            prompt_parts.append(f"此文件依赖的模块: {', '.join(imports[:5])}")

        prompt_parts.append("")
        return "\n".join(prompt_parts)

    def _parse_response(self, content: str) -> dict:
        """解析LLM响应为结构化数据"""
        try:
            # 尝试提取JSON
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                content = content[start:end]
            elif "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                content = content[start:end]
            return json.loads(content.strip())
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"[{self.name}] LLM响应解析失败，使用空结果")
            return {"findings": [], "handover": ""}

    def _to_findings(self, raw_findings: list[dict], file_path: str) -> list[Finding]:
        """将原始字典转换为Finding对象"""
        result = []
        for f in raw_findings:
            result.append(Finding(
                severity=f.get("severity", "warning"),
                category=f.get("category", "bug"),
                file_path=f.get("file_path", file_path),
                line=f.get("line", 0),
                message=f.get("message", ""),
                suggestion=f.get("suggestion", ""),
                agent_source="agent_a",
            ))
        return result
