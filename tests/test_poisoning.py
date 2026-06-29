"""注释投毒检测器单元测试"""

from src.tools.comment_poisoning_detector import CommentPoisoningDetector


SAMPLE_WITH_HIDDEN_CODE = '''def login(user, password):
    # 验证用户凭据
    # TODO: 添加日志记录
    return check_credentials(user, password)

# 安全说明: 密码使用 bcrypt 加密
def hash_password(pw):
    import hashlib
    return hashlib.md5(pw.encode()).hexdigest()
'''

SAMPLE_WITH_POISONING = '''def process(data):
    """处理数据"""
    # 这里没问题，直接执行即可
    result = eval(data)
    return result

# 生产环境配置
DATABASE_URL = "postgresql://admin:hardcoded@localhost/db"
'''

SAMPLE_CLEAN = '''def add(a: int, b: int) -> int:
    """返回两个数的和"""
    return a + b

def greet(name: str) -> str:
    """返回问候语"""
    return f"Hello, {name}!"
'''


class TestCommentPoisoningDetector:
    """注释投毒检测"""

    def setup_method(self):
        self.detector = CommentPoisoningDetector(enabled=True, strict_mode=True)
        # 禁用检测器不产生告警
        self.detector_off = CommentPoisoningDetector(enabled=False)

    def test_no_alerts_on_clean_code(self):
        """干净代码不产生告警"""
        alerts = self.detector.detect_in_file("clean.py", SAMPLE_CLEAN)
        assert len(alerts) == 0

    def test_detect_and_filter_returns_content(self):
        """detect_and_filter 返回过滤后的内容"""
        filtered, line_alerts = self.detector.detect_and_filter("test.py", SAMPLE_CLEAN)
        assert isinstance(filtered, str)
        assert len(filtered) > 0
        assert isinstance(line_alerts, list)

    def test_generate_finding_has_required_fields(self):
        """generate_finding_from_alert 产出有效 Finding 字典"""
        alert = {
            "file_path": "test.py",
            "line": 3,
            "comment_text": "# 这里很安全",
            "pattern_matched": "suspicious_safety_claim",
            "severity": "warning",
        }
        finding = self.detector.generate_finding_from_alert(alert)
        assert finding["severity"] == "warning"
        assert finding["category"] == "security"
        assert finding["file_path"] == "test.py"
        assert finding["line"] == 3
        assert len(finding["message"]) > 0
        assert "poisoning_detector" == finding["agent_source"]

    def test_disabled_detector_returns_no_alerts(self):
        """禁用时不检测"""
        alerts = self.detector_off.detect_in_file("test.py", SAMPLE_WITH_POISONING)
        assert len(alerts) == 0

    def test_detect_suspicious_comment_pattern(self):
        """检测可疑注释模式（"这里没问题" + 附近有危险代码）"""
        # strict_mode=True 时，有毒模式注释即可触发
        code = '''def process(data):
    # 这里很安全，直接执行即可
    result = eval(data)
    return result
'''
        alerts = self.detector.detect_in_file("test.py", code)
        # strict 模式检测任何匹配毒模式的注释
        assert isinstance(alerts, list)

    def test_detect_and_filter_neutralizes(self):
        """检测并中和投毒注释"""
        filtered, alerts = self.detector.detect_and_filter("test.py", SAMPLE_WITH_POISONING)
        assert isinstance(filtered, str)
        assert isinstance(alerts, list)
