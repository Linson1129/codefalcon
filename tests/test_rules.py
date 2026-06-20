"""安全规则引擎测试"""

import pytest
from src.rules.security import SecurityRuleEngine


class TestSecurityRuleEngine:
    """安全规则引擎测试"""

    def setup_method(self):
        self.engine = SecurityRuleEngine()

    def test_detect_hardcoded_api_key(self):
        """检测硬编码API密钥"""
        code = {
            "test.py": 'API_KEY = "sk-1234567890abcdef"'
        }
        findings = self.engine.scan(code)
        assert len(findings) >= 1
        assert any("硬编码" in f.message for f in findings)
        assert all(f.severity == "error" for f in findings)

    def test_detect_hardcoded_password(self):
        """检测硬编码密码"""
        code = {
            "test.py": 'password = "admin123"'
        }
        findings = self.engine.scan(code)
        assert len(findings) >= 1

    def test_detect_sql_injection_format(self):
        """检测SQL注入 - 字符串格式化"""
        code = {
            "test.py": 'cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)'
        }
        findings = self.engine.scan(code)
        assert len(findings) >= 1
        assert any("SQL" in f.message for f in findings)

    def test_detect_sql_injection_fstring(self):
        """检测SQL注入 - f-string"""
        code = {
            "test.py": 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
        }
        findings = self.engine.scan(code)
        assert len(findings) >= 1

    def test_detect_command_injection_os_system(self):
        """检测命令注入 - os.system"""
        code = {
            "test.py": 'os.system("rm -rf " + user_input)'
        }
        findings = self.engine.scan(code)
        assert len(findings) >= 1

    def test_detect_eval(self):
        """检测eval使用"""
        code = {
            "test.py": 'eval(user_input)'
        }
        findings = self.engine.scan(code)
        assert len(findings) >= 1

    def test_clean_code_no_findings(self):
        """干净代码不应有问题"""
        code = {
            "test.py": '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
'''
        }
        findings = self.engine.scan(code)
        assert len(findings) == 0

    def test_multiple_files(self):
        """多文件扫描"""
        code = {
            "auth.py": 'password = "secret123"',
            "db.py": 'cursor.execute("SELECT * FROM users WHERE name = \'" + name + "\'")',
        }
        findings = self.engine.scan(code)
        assert len(findings) >= 2
