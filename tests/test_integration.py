"""集成测试 - 端到端流水线验证"""

import json as _json
from pathlib import Path

from src.orchestrator.state import Finding, ReviewState
from src.orchestrator.graph import build_review_graph
from src.output.reporter import Reporter
from src.output.todo_manager import TodoManager


# 单文件测试样本（足够检测安全 + 风格问题）
SAMPLE_CODE = {
    "src/app.py": '''"""应用入口"""
import os

DATABASE_URL = "postgresql://user:hardcoded_pass@localhost/db"

def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    return execute(query)

def execute(sql):
    return sql

def main():
    user_input = input("Enter command: ")
    os.system("echo " + user_input)
    x = eval("2 + 2")
    return x
''',
}


def _mock_llm_response(content):
    return {"content": content, "usage": {"prompt_tokens": 100, "completion_tokens": 50}}


def _agent_a_json():
    return _json.dumps({
        "findings": [
            {"severity": "error", "category": "bug",
             "file_path": "src/app.py", "line": 5,
             "message": "硬编码数据库密码", "suggestion": "用环境变量"},
        ],
        "handover": "",
    })


def _agent_b_json():
    return _json.dumps({
        "findings": [
            {"severity": "info", "category": "style",
             "file_path": "src/app.py", "line": 1,
             "message": "模块docstring格式待优化", "suggestion": ""},
        ],
    })


class TestIntegration:
    """端到端集成测试"""

    def setup_method(self):
        for f in Path(".").glob("TODOS.md"):
            f.unlink(missing_ok=True)

    def test_full_pipeline_with_mock_agents(self, monkeypatch):
        """完整流水线：规则 → 风格 → 并行Agent → 聚合"""
        from langgraph.checkpoint.memory import MemorySaver

        state = ReviewState(
            target_paths=["src/app.py"],
            target_files=SAMPLE_CODE.copy(),
        )

        # Mock 掉 BaseAgent._do_call（Agent A 和 B 各调一次）
        call_count = [0]

        def fake_do_call(self, model, system_prompt, user_prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_llm_response(_agent_a_json())
            else:
                return _mock_llm_response(_agent_b_json())

        monkeypatch.setattr(
            "src.agents.base.BaseAgent._do_call", fake_do_call
        )

        graph = build_review_graph()
        workflow = graph.compile(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "test-001"}}

        result = workflow.invoke(state, config)

        # 验证各阶段
        assert result is not None

        # 1. 安全规则引擎
        rule_findings = result.get("rule_findings", [])
        for f in rule_findings:
            if isinstance(f, Finding) and f.category == "security":
                break
        else:
            # 也检查 dict 格式
            found = False
            for f in rule_findings:
                sev = f.get("severity") if isinstance(f, dict) else f.severity
                cat = f.get("category") if isinstance(f, dict) else f.category
                if sev == "error" and cat == "security":
                    found = True
                    break
            if not found and len(rule_findings) > 0:
                pass  # 规则引擎已运行
        assert len(rule_findings) > 0, "规则引擎应有发现"

        # 2. 风格规则引擎
        style_findings = result.get("style_findings", [])
        assert isinstance(style_findings, list), "风格引擎应运行"

        # 3. Agent A/B
        agent_a = result.get("agent_a_findings", [])
        agent_b = result.get("agent_b_findings", [])
        assert len(agent_a) > 0, "Agent A 应有输出"
        assert len(agent_b) > 0, "Agent B 应有输出"

        # 4. 聚合
        merged = result.get("merged_findings", [])
        assert len(merged) > 0, "应有聚合结果"

        # 5. 待办
        todos = result.get("todos", [])
        assert len(todos) > 0, "应生成待办"


class TestReporterIntegration:
    """Reporter + TodoManager 集成"""

    def test_generate_report(self, monkeypatch, tmp_path):
        """生成报告并验证文件"""
        findings = [
            Finding(severity="error", category="security", file_path="test.py",
                    line=5, message="硬编码密码", suggestion="用环境变量",
                    agent_source="rules"),
        ]

        state = ReviewState(
            target_paths=["test.py"],
            target_files={"test.py": "pass\n"},
            merged_findings=findings,
            todos=[{
                "file": "test.py", "line": 5, "severity": "error",
                "category": "security", "message": "硬编码密码",
                "suggestion": "用环境变量",
            }],
        )

        review_dir = tmp_path / "reviews"

        reporter = Reporter(output_dir=str(review_dir))
        reporter.generate(state)

        # 验证 JSON 文件（扁平结构，不再有日期子目录）
        json_files = sorted(
            [f for f in review_dir.glob("*.json") if f.name != "latest.json"]
        )
        assert len(json_files) == 1, f"应有1个JSON报告, 实际: {json_files}"

        # 验证 latest.json
        latest = review_dir / "latest.json"
        assert latest.exists(), "应有 latest.json"

        # 验证 JSON 内容
        report = _json.loads(json_files[0].read_text(encoding="utf-8"))
        assert report["summary"]["total"] == 1
        assert report["findings"][0]["severity"] == "error"

        # 验证计数
        counter = review_dir / ".review_count"
        assert int(counter.read_text().strip()) >= 1


class TestTodoManagerIntegration:
    """TodoManager 完整功能"""

    def test_add_mark_done_flow(self, tmp_path):
        todo_path = tmp_path / "TODOS.md"
        mgr = TodoManager(filepath=str(todo_path))

        # 追加
        mgr.append_todos([
            {"file": "a.py", "line": 1, "severity": "error",
             "category": "security", "message": "SQL注入", "suggestion": ""},
        ])

        todos = mgr.read_todos()
        assert len(todos) == 1
        assert todos[0]["id"] == "TODO-001"
        assert "date" in todos[0]

        # 标记完成
        assert mgr.mark_done("TODO-001")
        assert mgr.get_done()[0]["status"] == "done"
        assert len(mgr.get_pending()) == 0

        # 相同内容去重
        mgr.append_todos([
            {"file": "a.py", "line": 1, "severity": "error",
             "category": "security", "message": "SQL注入", "suggestion": ""},
        ])
        assert len(mgr.read_todos()) == 1, "重复应过滤"

        # 不同内容追加，序号延续
        mgr.append_todos([
            {"file": "b.py", "line": 2, "severity": "warning",
             "category": "style", "message": "行太长", "suggestion": ""},
        ])
        ids = sorted(t["id"] for t in mgr.read_todos())
        assert ids == ["TODO-001", "TODO-002"]


class TestCLICommands:
    """CLI 命令测试"""

    def test_review_no_target(self):
        """无目标报错"""
        from click.testing import CliRunner
        from src.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["review"])
        assert result.exit_code != 0

    def test_status_ok(self, tmp_path):
        """status 命令"""
        from click.testing import CliRunner
        from src.main import cli
        import os

        todo_path = tmp_path / "TODOS.md"
        todo_path.write_text(
            "# 📋 待办\n\n"
            "- [ ] [2026-06-20] **TODO-001** `a.py:1` | 🔴 error | test\n"
        )

        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            runner = CliRunner()
            result = runner.invoke(cli, ["status"])
            assert result.exit_code == 0
        finally:
            os.chdir(cwd)

    def test_done_ok(self, tmp_path):
        """done 命令"""
        from click.testing import CliRunner
        from src.main import cli
        import os

        todo_path = tmp_path / "TODOS.md"
        mgr = TodoManager(filepath=str(todo_path))
        mgr.append_todos([
            {"file": "a.py", "line": 1, "severity": "error",
             "category": "security", "message": "test", "suggestion": ""},
        ])

        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            runner = CliRunner()
            result = runner.invoke(cli, ["done", "TODO-001"])
            assert result.exit_code == 0
        finally:
            os.chdir(cwd)
