"""Agent B - 风格检查 + 验收"""

import json
import logging
from typing import Any

from .base import BaseAgent
from src.orchestrator.state import Finding, ReviewState

logger = logging.getLogger(__name__)


class StyleAcceptAgent(BaseAgent):
    """Agent B: 负责代码风格检查和最终验收

    核心能力：
    - 代码风格审查（命名规范、格式一致性、注释质量）
    - 接收Agent A的交接文档，做交叉验证
    - 最终验收（综合规则引擎和Agent A的结果）
    """

    def __init__(self, dry_run: bool = False):
        super().__init__(name="StyleAcceptAgent", model="qwen-turbo", dry_run=dry_run)

    def get_system_prompt(self) -> str:
        return """你是一个代码风格和验收专家，负责审查代码的可读性和规范性。

审查要点：
1. 代码风格：
   - 命名规范（变量、函数、类命名）
   - 缩进和格式一致性
   - 注释质量和完整性
   - 函数/方法长度合理性
   - 代码重复（DRY原则）

2. 验收检查：
   - 综合规则引擎和Agent A的发现
   - 确认是否有遗漏
   - 判断修改影响范围

输出格式（JSON）：
{
  "findings": [
    {
      "severity": "error|warning|info",
      "category": "style",
      "file_path": "...",
      "line": 88,
      "message": "简短描述问题",
      "suggestion": "修复建议"
    }
  ],
  "acceptance_summary": "验收总结，包括与Agent A发现的关联分析"
}
"""

    def review(self, state: ReviewState) -> list[Finding]:
        """执行风格和验收审查（与 Agent A 并行）"""
        logger.info(f"[{self.name}] 开始审查 {len(state.target_files)} 个文件")

        findings = []

        # 获取 Skill 上下文
        skill_context = self._build_skill_context(category="style")

        files_to_scan = state.filtered_files if state.filtered_files else state.target_files
        for file_path, content in files_to_scan.items():
            try:
                user_prompt = self._build_review_prompt(
                    file_path, content, state.rule_findings,
                    state.dependency_graph, skill_context,
                )
                result = self.call_llm(
                    system_prompt=self.get_system_prompt(),
                    user_prompt=user_prompt,
                )

                parsed = self.parse_response(result.get("content", "{}"))
                findings.extend(
                    self.to_findings(
                        parsed.get("findings", []), file_path,
                        agent_source="agent_b",
                        default_category="style",
                        default_severity="info",
                    )
                )

            except Exception as e:
                logger.error(f"[{self.name}] 审查 {file_path} 失败: {e}")
                continue

        logger.info(f"[{self.name}] 审查完成，发现 {len(findings)} 个问题")
        return findings

    def _build_review_prompt(
        self, file_path: str, content: str,
        rule_findings: list[Finding], dependency_graph: dict,
        skill_context: str = "",
    ) -> str:
        """构建审查提示词（含规则引擎发现 + 依赖上下文 + Skill）"""
        prompt_parts = [f"请审查以下文件的代码风格: {file_path}\n"]
        prompt_parts.append(f"```\n{content}\n```\n")

        # Skill 上下文
        if skill_context:
            prompt_parts.append(skill_context)

        if rule_findings:
            prompt_parts.append("--- 规则引擎已发现问题 ---")
            for f in rule_findings:
                prompt_parts.append(f"  - [{f.file_path}:{f.line}] {f.message}")

        # 依赖关系（使用基类方法）
        dep_ctx = self._build_dependency_context(file_path, dependency_graph)
        if dep_ctx:
            prompt_parts.append(f"\n{dep_ctx}")

        return "\n".join(prompt_parts)

