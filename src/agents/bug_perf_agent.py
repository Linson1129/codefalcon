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

    def __init__(self, dry_run: bool = False):
        super().__init__(name="BugPerfAgent", model="deepseek-chat", dry_run=dry_run)

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

        # 获取 Skill 上下文
        skill_context = self._build_skill_context(category="bug")
        if not skill_context:
            skill_context = self._build_skill_context(category="performance")

        files_to_scan = state.filtered_files if state.filtered_files else state.target_files
        for file_path, content in files_to_scan.items():
            try:
                user_prompt = self._build_review_prompt(
                    file_path, content, state.related_code,
                    state.dependency_graph, skill_context,
                )
                result = self.call_llm(
                    system_prompt=self.get_system_prompt(),
                    user_prompt=user_prompt,
                )

                parsed = self.parse_response(
                    result.get("content", "{}"),
                    default_extra="",
                )
                findings.extend(
                    self.to_findings(
                        parsed.get("findings", []), file_path,
                        agent_source="agent_a",
                        default_category="bug",
                        default_severity="warning",
                    )
                )

                # 保存交接文档到最后一个 finding 的 metadata
                handover = parsed.get("handover", "")
                if handover and findings:
                    findings[-1].metadata["handover"] = handover

            except Exception as e:
                logger.error(f"[{self.name}] 审查 {file_path} 失败: {e}")
                continue

        logger.info(f"[{self.name}] 审查完成，发现 {len(findings)} 个问题")
        return findings

    def _build_review_prompt(
        self, file_path: str, content: str,
        related_code: dict[str, list[str]],
        dependency_graph: dict,
        skill_context: str = "",
    ) -> str:
        """构建审查提示词（含代码调用关系 + 依赖上下文 + Skill）"""
        prompt_parts = [f"请审查以下文件: {file_path}\n"]
        prompt_parts.append(f"```\n{content}\n```\n")

        # Skill 上下文
        if skill_context:
            prompt_parts.append(skill_context)

        # 调用关系
        if file_path in related_code and related_code[file_path]:
            prompt_parts.append("相关代码调用关系:")
            for snippet in related_code[file_path][:5]:
                prompt_parts.append(f"- {snippet}")

        # 依赖关系（使用基类方法）
        dep_ctx = self._build_dependency_context(file_path, dependency_graph)
        if dep_ctx:
            prompt_parts.append(f"\n{dep_ctx}")

        prompt_parts.append("")
        return "\n".join(prompt_parts)

