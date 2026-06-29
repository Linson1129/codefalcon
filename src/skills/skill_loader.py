"""Skill 加载器 - 从 YAML 文件加载审查技能定义"""

import logging
import os
import yaml
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Skill:
    """单个审查技能的定义"""

    def __init__(
        self,
        name: str,
        description: str,
        category: str,
        severity: str,
        pattern: Optional[str] = None,
        llm_prompt: Optional[str] = None,
        suggestion_template: Optional[str] = None,
        enabled: bool = True,
        line_count_threshold: Optional[int] = None,
    ):
        self.name = name
        self.description = description
        self.category = category  # "security" | "bug" | "performance" | "style" | "architecture" | "spec"
        self.severity = severity  # "error" | "warning" | "info"
        self.pattern = pattern  # 正则表达式（规则型技能 / LLM 型 fallback）
        self.llm_prompt = llm_prompt  # LLM Prompt（LLM型技能）
        self.suggestion_template = suggestion_template
        self.enabled = enabled
        self.line_count_threshold = line_count_threshold  # 行数阈值（如 function_length Skill）

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "severity": self.severity,
            "pattern": self.pattern,
            "llm_prompt": self.llm_prompt,
            "suggestion_template": self.suggestion_template,
            "enabled": self.enabled,
            "line_count_threshold": self.line_count_threshold,
        }

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "Skill":
        """从 YAML 文件加载 Skill"""
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(
            name=data.get("name", os.path.basename(yaml_path).replace(".yaml", "")),
            description=data.get("description", ""),
            category=data.get("category", "style"),
            severity=data.get("severity", "info"),
            pattern=data.get("pattern"),
            llm_prompt=data.get("llm_prompt"),
            suggestion_template=data.get("suggestion_template"),
            enabled=data.get("enabled", True),
            line_count_threshold=data.get("line_count_threshold"),
        )

    def to_yaml(self, yaml_path: str) -> None:
        """保存 Skill 到 YAML 文件"""
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True, sort_keys=False)


class SkillLoader:
    """Skill 加载器 - 扫描 skills/ 目录，加载所有 YAML 定义的技能"""

    def __init__(self, skills_dir: str = "skills"):
        """
        Args:
            skills_dir: Skill 定义文件所在目录（相对于项目根或绝对路径）
        """
        self.skills_dir = Path(skills_dir)
        self._cache: dict[str, Skill] = {}

    def load_all(self) -> dict[str, Skill]:
        """加载所有 Skill"""
        skills = {}
        if not self.skills_dir.exists():
            logger.warning(f"[SkillLoader] 目录不存在: {self.skills_dir}")
            return skills

        for yaml_file in self.skills_dir.rglob("*.yaml"):
            try:
                skill = Skill.from_yaml(str(yaml_file))
                if skill.enabled:
                    skills[skill.name] = skill
                    logger.info(f"[SkillLoader] 已加载 Skill: {skill.name} ({skill.category})")
            except Exception as e:
                logger.error(f"[SkillLoader] 加载失败 {yaml_file}: {e}")

        self._cache = skills
        logger.info(f"[SkillLoader] 共加载 {len(skills)} 个 Skill")
        return skills

    def load_by_category(self, category: str) -> dict[str, Skill]:
        """按类别加载 Skill"""
        all_skills = self.load_all()
        return {
            name: skill for name, skill in all_skills.items()
            if skill.category == category
        }

    def get(self, name: str) -> Optional[Skill]:
        """获取指定名称的 Skill"""
        if not self._cache:
            self.load_all()
        return self._cache.get(name)

    def reload(self) -> dict[str, Skill]:
        """重新加载（清除缓存）"""
        self._cache = {}
        return self.load_all()
