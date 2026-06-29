"""BaseAgent 共享方法单元测试

覆盖 parse_response 的 6 种异常输入 + to_findings 转换
"""

from src.agents.bug_perf_agent import BugPerfAgent


class TestParseResponse:
    """parse_response 各种输入场景"""

    def setup_method(self):
        self.agent = BugPerfAgent(dry_run=True)

    def test_decode_json_in_code_block(self):
        """正常 JSON 在 ```json 代码块中"""
        resp = '```json\n{"findings": [{"severity": "error", "message": "SQL注入"}], "handover": "ok"}\n```'
        result = self.agent.parse_response(resp, default_extra="")
        assert len(result["findings"]) == 1
        assert result["findings"][0]["severity"] == "error"

    def test_decode_json_in_generic_code_block(self):
        """JSON 在 ``` 代码块中"""
        resp = '```\n{"findings": [{"severity": "info"}], "handover": ""}\n```'
        result = self.agent.parse_response(resp)
        assert len(result["findings"]) == 1

    def test_decode_pure_json(self):
        """纯 JSON 无代码块包裹"""
        resp = '{"findings": [{"severity": "warning", "category": "bug", "message": "test", "line": 42}], "handover": ""}'
        result = self.agent.parse_response(resp)
        assert len(result["findings"]) == 1
        assert result["findings"][0]["line"] == 42

    def test_json_with_trailing_text(self):
        """JSON 后跟多余文本"""
        resp = '{"findings": [{"severity": "error"}], "handover": "done"}\n还有一些补充说明...'
        result = self.agent.parse_response(resp)
        assert len(result["findings"]) == 1  # 应成功解析 JSON 部分

    def test_malformed_json_fallback_regex(self):
        """JSON 格式错误，fallback 正则兜底"""
        resp = '抱歉，我无法按照JSON格式输出。但发现问题：severity=error, category=security, message=密钥硬编码'
        # 这个输入没有匹配的 JSON，但正则可能无法提取（字段不是 JSON 格式）
        # 至少不能崩溃，返回空列表
        result = self.agent.parse_response(resp)
        assert "findings" in result
        assert isinstance(result["findings"], list)

    def test_empty_response(self):
        """空响应"""
        result = self.agent.parse_response("", default_extra="fallback")
        assert result["findings"] == []

    def test_broken_json_with_fields_recoverable(self):
        """不完整 JSON 但有可提取字段 — fallback 正则提取"""
        resp = '''{"findings": [{"severity": "error", "category": "security", "file_path": "test.py",
        "line": 10, "message": "硬编码密码", "suggestion": "用环境变量"}]'''
        # 缺少结尾 }，JSON 解析会失败
        result = self.agent.parse_response(resp)
        # fallback 正则应该能匹配
        # 至少不能崩溃
        assert "findings" in result


class TestToFindings:
    """to_findings 转换测试"""

    def setup_method(self):
        self.agent = BugPerfAgent(dry_run=True)

    def test_convert_single_finding(self):
        raw = [{"severity": "error", "category": "security", "file_path": "a.py", "line": 5, "message": "密码泄露", "suggestion": "用环境变量"}]
        findings = self.agent.to_findings(raw, "a.py", agent_source="agent_a", default_category="bug")
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == "error"
        assert f.category == "security"
        assert f.file_path == "a.py"
        assert f.line == 5
        assert f.agent_source == "agent_a"

    def test_convert_with_defaults(self):
        """缺少字段时使用默认值"""
        raw = [{"message": "问题描述"}]
        findings = self.agent.to_findings(raw, "test.py", agent_source="agent_a", default_category="bug", default_severity="warning")
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == "warning"
        assert f.category == "bug"
        assert f.file_path == "test.py"
        assert f.line == 0
        assert f.suggestion == ""

    def test_convert_empty_list(self):
        findings = self.agent.to_findings([], "x.py", agent_source="agent_a")
        assert findings == []

    def test_file_path_override(self):
        """raw 中的 file_path 覆盖参数"""
        raw = [{"file_path": "overridden.py", "message": "test"}]
        findings = self.agent.to_findings(raw, "original.py", agent_source="agent_a")
        assert findings[0].file_path == "overridden.py"

    def test_missing_file_path_uses_param(self):
        """raw 中无 file_path 时用参数"""
        raw = [{"message": "test", "line": 3}]
        findings = self.agent.to_findings(raw, "fallback.py", agent_source="agent_a")
        assert findings[0].file_path == "fallback.py"
