"""Skill 执行器单元测试"""

import tempfile
from pathlib import Path

from src.skills.skill_executor import SkillExecutor
from src.skills.skill_loader import Skill, SkillLoader


SAMPLE_SKILL_YAML = """
name: test_no_hardcode
description: 检测硬编码密钥
category: security
severity: error
pattern: '(?i)(api_key|secret_key)\\s*=\\s*\"[^\"]{20,}\"'
suggestion_template: 请将 {match} 移到环境变量中
"""

SAMPLE_LLM_SKILL_YAML = """
name: test_llm_skill
description: LLM型Skill示例
category: bug
severity: warning
llm_prompt: |
  请在审查时检查以下内容：
  1. 是否正确处理了异常
"""

CODE_WITH_SECRET = '''import os
API_KEY = "sk-proj-1234567890abcdef"
SECRET_KEY = "my-very-long-secret-key-that-should-not-be-here"
x = 1
'''

CODE_CLEAN = '''def hello():
    """Say hello"""
    return "Hello, World!"
'''


class TestSkillExecutor:
    """规则型 Skill 执行测试"""

    def test_execute_rule_skill(self, tmp_path):
        """规则型 Skill 正确匹配"""
        # 创建临时 skills 目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "test_skill.yaml").write_text(SAMPLE_SKILL_YAML, encoding="utf-8")

        executor = SkillExecutor(skills_dir=str(skills_dir))
        findings = executor.execute_all("test.py", CODE_WITH_SECRET)

        assert len(findings) >= 1
        # 验证发现结构
        for f in findings:
            assert f.severity == "error"
            assert f.category == "security"
            assert f.file_path == "test.py"
            assert f.line > 0
            assert "[test_no_hardcode]" in f.message
            assert "skill:test_no_hardcode" in f.agent_source

    def test_execute_on_clean_code(self, tmp_path):
        """干净代码无发现"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test_skill.yaml").write_text(SAMPLE_SKILL_YAML, encoding="utf-8")

        executor = SkillExecutor(skills_dir=str(skills_dir))
        findings = executor.execute_all("clean.py", CODE_CLEAN)
        assert len(findings) == 0

    def test_category_filter(self, tmp_path):
        """category_filter 过滤有效"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test_skill.yaml").write_text(SAMPLE_SKILL_YAML, encoding="utf-8")

        executor = SkillExecutor(skills_dir=str(skills_dir))
        # 过滤非 security 类别
        findings = executor.execute_all("test.py", CODE_WITH_SECRET, category_filter="style")
        assert len(findings) == 0  # security skill 被过滤

    def test_get_llm_prompts(self, tmp_path):
        """get_llm_prompts 返回 LLM 型 Skill 的 prompt"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "llm_skill.yaml").write_text(SAMPLE_LLM_SKILL_YAML, encoding="utf-8")
        (skills_dir / "test_skill.yaml").write_text(SAMPLE_SKILL_YAML, encoding="utf-8")

        executor = SkillExecutor(skills_dir=str(skills_dir))
        prompts = executor.get_llm_prompts()
        assert "test_llm_skill" in prompts
        assert "test_no_hardcode" not in prompts  # 规则型不在此列

    def test_build_skill_context_for_agent(self, tmp_path):
        """build_skill_context_for_agent 拼接上下文"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "llm_skill.yaml").write_text(SAMPLE_LLM_SKILL_YAML, encoding="utf-8")

        executor = SkillExecutor(skills_dir=str(skills_dir))
        context = executor.build_skill_context_for_agent(category="bug")
        assert "test_llm_skill" in context
        assert "已启用的审查技能" in context

    def test_execute_llm_skill_skipped(self, tmp_path):
        """LLM 型 Skill 在 execute 时被跳过"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "llm_skill.yaml").write_text(SAMPLE_LLM_SKILL_YAML, encoding="utf-8")

        executor = SkillExecutor(skills_dir=str(skills_dir))
        skill = Skill(
            name="test_llm_skill",
            description="LLM skill",
            category="bug",
            severity="warning",
            llm_prompt="test prompt",
            pattern=None,
        )
        findings = executor.execute(skill, "test.py", CODE_CLEAN)
        assert findings == []  # LLM 型被跳过
