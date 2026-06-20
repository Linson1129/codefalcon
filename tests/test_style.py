"""风格规则引擎测试"""

import pytest
from src.rules.style import StyleRuleEngine
from src.orchestrator.state import Finding


class TestStyleRuleEngine:
    """风格规则引擎测试"""

    def setup_method(self):
        self.engine = StyleRuleEngine()

    def test_line_length_ok(self):
        """行长度在限制内应无发现"""
        content = "short line\n" * 10
        findings = self.engine.scan({"test.py": content})
        assert len(findings) == 0

    def test_line_length_exceeded(self):
        """超长行应被检测"""
        long_line = "x" * 121  # 超过120
        content = long_line + "\n"
        findings = self.engine.scan({"test.py": content})
        assert len(findings) >= 1
        f = findings[0]
        assert f.severity == "info"
        assert f.category == "style"
        assert f.line == 1

    def test_line_length_boundary(self):
        """120字符不应触发，121字符应触发"""
        ok = "x" * 120 + "\n"
        too_long = "y" * 121 + "\n"
        findings = self.engine.scan({"test.py": ok + too_long})
        assert len(findings) == 1
        assert findings[0].line == 2

    def test_trailing_whitespace_space(self):
        """行尾空格应被检测"""
        content = "hello   \nworld\n"
        findings = self.engine.scan({"test.py": content})
        assert len(findings) == 1
        assert findings[0].line == 1
        assert "空格" in findings[0].message

    def test_trailing_whitespace_tab(self):
        """行尾制表符应被检测"""
        content = "hello\t\nworld\n"
        findings = self.engine.scan({"test.py": content})
        assert len(findings) == 1
        assert findings[0].line == 1

    def test_clean_code_no_findings(self):
        """干净的代码应无发现"""
        content = (
            "def hello():\n"
            "    return 'world'\n"
            "    # 这一行不到120字符\n"
            "\n"
            "class Foo:\n"
            "    pass\n"
        )
        findings = self.engine.scan({"test.py": content})
        assert len(findings) == 0

    def test_multiple_files(self):
        """多文件扫描"""
        files = {
            "a.py": "x" * 121 + "\n",
            "b.py": "short\n",
        }
        findings = self.engine.scan(files)
        assert len(findings) == 1
        assert findings[0].file_path == "a.py"
