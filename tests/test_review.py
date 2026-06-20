"""汇总仲裁器测试"""

import pytest
from src.review.aggregator import Aggregator
from src.orchestrator.state import Finding, ReviewState


class TestAggregator:
    """汇总仲裁器测试"""

    def setup_method(self):
        self.aggregator = Aggregator()

    def test_deduplicate_same_line(self):
        """同一行同行同类别的多个发现应去重，不同类别应保留"""
        state = ReviewState()
        state.rule_findings = [
            Finding(severity="error", category="security",
                    file_path="test.py", line=10,
                    message="SQL注入", agent_source="rules")
        ]
        state.agent_a_findings = [
            Finding(severity="warning", category="bug",
                    file_path="test.py", line=10,
                    message="SQL拼接问题", agent_source="agent_a")
        ]
        state.agent_b_findings = []

        state = self.aggregator.aggregate(state)
        # 同一行但不同类别（security vs bug）应各保留一条
        assert len(state.merged_findings) == 2

    def test_priority_sorting(self):
        """应优先排序"""
        state = ReviewState()
        state.rule_findings = [
            Finding(severity="info", category="style",
                    file_path="test.py", line=30,
                    message="风格问题", agent_source="rules")
        ]
        state.agent_a_findings = [
            Finding(severity="error", category="security",
                    file_path="test.py", line=10,
                    message="安全漏洞", agent_source="agent_a")
        ]
        state.agent_b_findings = []

        state = self.aggregator.aggregate(state)
        # security > style, error > info
        assert state.merged_findings[0].category == "security"
        assert state.merged_findings[0].severity == "error"

    def test_empty_findings(self):
        """无发现时应正常处理"""
        state = ReviewState()
        state = self.aggregator.aggregate(state)
        assert state.merged_findings == []
        assert state.todos == []

    def test_conflict_detection(self):
        """不同Agent对同一位置有不同意见应产生冲突"""
        state = ReviewState()
        state.agent_a_findings = [
            Finding(severity="error", category="bug",
                    file_path="test.py", line=15,
                    message="严重Bug", suggestion="立即修复",
                    agent_source="agent_a")
        ]
        state.agent_b_findings = [
            Finding(severity="info", category="style",
                    file_path="test.py", line=15,
                    message="风格问题", suggestion="可忽略",
                    agent_source="agent_b")
        ]
        state.rule_findings = []

        state = self.aggregator.aggregate(state)
        # 同位置不同严重程度应产生冲突
        assert len(state.pending_questions) >= 1
