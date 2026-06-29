"""Skill 执行器 - 执行规则型或 LLM 型 Skill"""

import logging
import re
from typing import Optional

from src.skills.skill_loader import Skill, SkillLoader
from src.orchestrator.state import Finding

logger = logging.getLogger(__name__)


class SkillExecutor:
    """Skill 执行器 - 根据 Skill 类型分发执行"""

    def __init__(self, skills_dir: str = "skills"):
        self.loader = SkillLoader(skills_dir)
        self.skills: dict[str, Skill] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self.skills = self.loader.load_all()
            self._loaded = True

    def execute_all(
        self,
        file_path: str,
        content: str,
        category_filter: Optional[str] = None,
    ) -> list[Finding]:
        """执行所有 Skill，返回发现列表"""
        self._ensure_loaded()

        findings = []
        for name, skill in self.skills.items():
            if category_filter and skill.category != category_filter:
                continue
            try:
                skill_findings = self.execute(skill, file_path, content)
                findings.extend(skill_findings)
            except Exception as e:
                logger.error(f"[SkillExecutor] Skill {name} 执行失败: {e}")

        return findings

    def execute(self, skill: Skill, file_path: str, content: str) -> list[Finding]:
        """执行单个 Skill

        执行优先级：
        1. 规则型 pattern → 正则匹配
        2. line_count_threshold → 行数统计检查（0 Token）
        3. llm_prompt → LLM 型（仅 prompt 注入，由 Agent 负责）
        """
        if skill.pattern:
            return self._execute_rule_skill(skill, file_path, content)
        elif skill.line_count_threshold is not None:
            return self._execute_line_count_skill(skill, file_path, content)
        elif skill.llm_prompt:
            # LLM 型 Skill 由调用方在 Agent 内执行（需要 LLM 上下文）
            logger.debug(f"[SkillExecutor] LLM型 Skill {skill.name} 跳过（需 Agent 调用）")
            return []
        else:
            logger.warning(f"[SkillExecutor] Skill {skill.name} 既无 pattern 也无 llm_prompt")
            return []

    def _execute_rule_skill(
        self, skill: Skill, file_path: str, content: str,
    ) -> list[Finding]:
        """执行规则型 Skill（正则匹配）"""
        findings = []
        if not skill.pattern:
            return findings

        try:
            regex = re.compile(skill.pattern)
        except re.error as e:
            logger.error(f"[SkillExecutor] Skill {skill.name} 正则编译失败: {e}")
            return findings

        for match in regex.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            suggestion = ""
            if skill.suggestion_template:
                suggestion = skill.suggestion_template.format(
                    match=match.group(),
                    group0=match.group(0) if match.groups() else "",
                )
            findings.append(Finding(
                severity=skill.severity,
                category=skill.category,
                file_path=file_path,
                line=line_num,
                message=f"[{skill.name}] {skill.description}",
                suggestion=suggestion,
                agent_source=f"skill:{skill.name}",
            ))

        return findings

    def _execute_line_count_skill(
        self, skill: Skill, file_path: str, content: str,
    ) -> list[Finding]:
        """执行行数阈值 Skill（0 Token 确定性检查）

        当前仅用于 function_length 类 Skill，
        统计 def/class 之间的行数，对超长函数/方法产生 finding。
        """
        findings = []
        threshold = skill.line_count_threshold
        if not threshold:
            return findings

        lines = content.split('\n')
        # 简化版：统计每个以 def 开头的函数体行数
        # 方法：找每个 def 开头行，到下一个同缩进级别的 def/class/@ 为止的行数
        in_function = False
        func_start = 0
        func_first_indent = 0

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            current_indent = len(line) - len(line.lstrip())

            if stripped.startswith(('def ', 'class ', '@')):
                # 结束上一个函数（如果有）
                if in_function and current_indent <= func_first_indent:
                    func_lines = i - func_start
                    if func_lines > threshold:
                        findings.append(Finding(
                            severity=skill.severity,
                            category=skill.category,
                            file_path=file_path,
                            line=func_start,
                            message=f"[{skill.name}] 函数/方法过长（{func_lines} 行，阈值 {threshold} 行）",
                            suggestion=skill.suggestion_template or f"建议拆分为多个小函数（每个不超过 {threshold} 行）",
                            agent_source=f"skill:{skill.name}",
                        ))
                    in_function = False

                # 开始新函数
                if stripped.startswith(('def ',)):
                    in_function = True
                    func_start = i
                    func_first_indent = current_indent

        # 文件末尾的最后一个函数
        if in_function:
            func_lines = len(lines) - func_start + 1
            if func_lines > threshold:
                findings.append(Finding(
                    severity=skill.severity,
                    category=skill.category,
                    file_path=file_path,
                    line=func_start,
                    message=f"[{skill.name}] 函数/方法过长（{func_lines} 行，阈值 {threshold} 行）",
                    suggestion=skill.suggestion_template or f"建议拆分为多个小函数（每个不超过 {threshold} 行）",
                    agent_source=f"skill:{skill.name}",
                ))

        return findings

    def get_llm_prompts(self, category: Optional[str] = None) -> dict[str, str]:
        """获取所有 LLM 型 Skill 的 Prompt（供 Agent 使用）"""
        self._ensure_loaded()
        return {
            name: skill.llm_prompt
            for name, skill in self.skills.items()
            if skill.llm_prompt and (not category or skill.category == category)
        }

    def build_skill_context_for_agent(self, category: Optional[str] = None) -> str:
        """为 Agent 构建 Skill 上下文（注入 Prompt）"""
        prompts = self.get_llm_prompts(category)
        if not prompts:
            return ""

        parts = ["--- 已启用的审查技能（Skills）---"]
        for name, prompt in prompts.items():
            parts.append(f"\n[Skill: {name}]\n{prompt}")
        parts.append("\n--- 请在审查时参考以上技能要求 ---\n")
        return "\n".join(parts)
