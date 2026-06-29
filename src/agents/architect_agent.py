"""Agent C - 架构审查（借鉴 GStack 多角色理念）"""

import json
import logging
from typing import Any

from .base import BaseAgent
from src.orchestrator.state import Finding, ReviewState

logger = logging.getLogger(__name__)


class ArchitectAgent(BaseAgent):
    """Agent C: 负责架构设计和代码质量审查

    核心能力（借鉴 GStack 的 /review 多角色理念）：
    - SOLID 原则检查
    - 设计模式合理性
    - 模块耦合度分析
    - 代码复用和 DRY 原则
    - 接口设计审查
    """

    def __init__(self, dry_run: bool = False):
        super().__init__(name="ArchitectAgent", model="deepseek-chat", dry_run=dry_run)

    def get_system_prompt(self) -> str:
        return """你是一个资深软件架构师，专注于代码架构设计和工程质量审查。

审查要点：
1. 架构设计：
   - SOLID 原则遵守情况
   - 设计模式使用是否合理
   - 抽象层次是否恰当
   - 接口设计是否清晰

2. 代码质量：
   - DRY 原则（重复代码）
   - 单一职责（类/函数是否只做一件事）
   - 模块耦合度和内聚度
   - 是否有过度设计或设计不足

3. 可维护性：
   - 代码是否易于理解和修改
   - 是否有充分的类型注解
   - 错误处理策略是否合理
   - 是否有充分的文档和注释

4. 扩展性：
   - 新增功能是否容易（对扩展开放）
   - 修改现有功能是否安全（对修改封闭）
   - 配置和代码是否分离

输出格式（JSON）：
{
  "findings": [
    {
      "severity": "error|warning|info",
      "category": "architecture",
      "file_path": "...",
      "line": 88,
      "message": "简短描述问题",
      "suggestion": "修复建议"
    }
  ],
  "architecture_summary": "架构审查总结，包括整体设计评价和关键改进建议"
}
"""

    def review(self, state: ReviewState) -> list[Finding]:
        """执行架构审查"""
        logger.info(f"[{self.name}] 开始架构审查 {len(state.target_files)} 个文件")

        findings = []

        # 获取 Skill 上下文（使用基类方法）
        skill_context = self._build_skill_context(category="architecture")

        files_to_scan = state.filtered_files if state.filtered_files else state.target_files
        for file_path, content in files_to_scan.items():
            try:
                user_prompt = self._build_review_prompt(
                    file_path, content, skill_context,
                    state.dependency_graph,
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
                        agent_source="agent_c",
                        default_category="architecture",
                        default_severity="warning",
                    )
                )

                # 保存架构总结到 metadata
                summary = parsed.get("architecture_summary", "")
                if summary and findings:
                    findings[-1].metadata["architecture_summary"] = summary

            except Exception as e:
                logger.error(f"[{self.name}] 审查 {file_path} 失败: {e}")
                continue

        logger.info(f"[{self.name}] 架构审查完成，发现 {len(findings)} 个问题")
        return findings

    def _build_review_prompt(
        self,
        file_path: str,
        content: str,
        skill_context: str,
        dependency_graph: dict,
    ) -> str:
        """构建架构审查提示词"""
        prompt_parts = [f"请对以下文件进行架构审查: {file_path}\n"]
        prompt_parts.append(f"```\n{content}\n```\n")

        # Skill 上下文
        if skill_context:
            prompt_parts.append(skill_context)

        # 依赖关系分析（使用基类方法）
        dep_ctx = self._build_dependency_context(file_path, dependency_graph)
        if dep_ctx:
            prompt_parts.append(f"\n--- 模块依赖关系 ---\n{dep_ctx}")
            prompt_parts.append("请从架构角度分析模块耦合度是否合理。")

        return "\n".join(prompt_parts)
