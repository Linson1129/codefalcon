"""CodeFalcon CLI入口"""

import json as _json
import sys
import click
from pathlib import Path

from src.utils.logger import setup_logger
from src.utils.cost_tracker import CostTracker
from src.orchestrator.state import ReviewState
from src.output.reporter import Reporter
from src.output.agent_bridge import AgentBridge


def _get_field(finding, field, default=""):
    """兼容 dict 和 Finding 对象的字段访问"""
    if isinstance(finding, dict):
        return finding.get(field, default)
    return getattr(finding, field, default)


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """CodeFalcon - 多Agent协作的智能代码审查系统"""
    setup_logger()


@cli.command()
@click.argument("target", nargs=-1, type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True, help="详细输出")
@click.option("--json", "-j", "json_output", is_flag=True, help="输出纯 JSON 到 stdout（供 Agent 编程调用）")
@click.option(
    "--agent-output", "-a",
    type=click.Choice(["codebuddy", "cursor", "universal", "file"]),
    default=None,
    help="生成面向 AI 编码 Agent 的修复 Prompt（codebuddy/cursor/universal/file）",
)
@click.option(
    "--mode", "-m",
    type=click.Choice(["full", "diff"]),
    default="full",
    help="审查模式: full=全量扫描, diff=仅审查 git 变更文件 (默认 full)",
)
@click.option(
    "--base", "-b",
    default="main",
    help="diff 模式的基准分支 (默认 main)",
)
@click.option(
    "--dry-run", is_flag=True,
    help="空跑模式：走完整 DAG 但不调真实 LLM，用于测试流水线",
)
def review(target, verbose, json_output, agent_output, mode, base, dry_run):
    """审查指定的文件或目录

    \b
    示例：
      codefalcon review src/                    # 全量审查
      codefalcon review . --mode diff            # 增量审查（vs main）
      codefalcon review src/ --dry-run           # 空跑测试
      codefalcon review . --mode diff --base develop  # 对比 develop 分支
    """
    if not target:
        click.echo("请指定要审查的文件或目录", err=True)
        sys.exit(1)

    # json 模式下人类可读输出走 stderr
    out = sys.stderr if json_output else sys.stdout

    click.echo("CodeFalcon v0.1.0 — 开始审查...", file=out) if not json_output else None
    click.echo("", file=out) if not json_output else click.echo("[CodeFalcon] 开始审查...", file=out)

    # === 任务1：读取目标文件（全量 or 增量） ===
    target_files = {}
    changed_files = []

    if mode == "diff":
        from src.tools.diff_analyzer import DiffAnalyzer
        analyzer = DiffAnalyzer(project_root=".")

        if not DiffAnalyzer.is_git_repo("."):
            click.echo("⚠️ 当前目录不是 git 仓库，回退到全量模式", file=out)
            mode = "full"
        else:
            changed_files = analyzer.get_changed_files(base_branch=base)
            if not changed_files:
                click.echo("✅ 无 .py 文件变更，无需审查", file=out)
                return
            click.echo(
                f"📌 Diff 模式 (基准: {base}) — 变更文件: {len(changed_files)} 个",
                file=out,
            )
            for t in target:
                t_path = Path(t)
                for rel_path in changed_files:
                    abs_path = Path(rel_path)
                    # 检查变更文件是否在用户指定的目标范围内
                    if str(abs_path).startswith(str(t_path)) or t_path.is_file() and str(abs_path) == str(t_path):
                        if abs_path.is_file() and abs_path.suffix == ".py":
                            try:
                                target_files[str(rel_path)] = abs_path.read_text(encoding="utf-8")
                            except Exception:
                                pass

    if mode == "full" or not target_files:
        for t in target:
            t_path = Path(t)
            if t_path.is_file() and t_path.suffix == ".py":
                target_files[str(t_path)] = t_path.read_text(encoding="utf-8")
            elif t_path.is_dir():
                for py_file in t_path.rglob("*.py"):
                    if py_file.is_file():
                        target_files[str(py_file)] = py_file.read_text(encoding="utf-8")

    if not target_files:
        click.echo("未找到任何 .py 文件", err=True)
        sys.exit(1)

    if dry_run:
        click.echo("🧪 Dry-Run 模式 — 走完整 DAG 但不调真实 LLM", file=out)

    click.echo(
        f"找到 {len(target_files)} 个 Python 文件{' (dry-run)' if dry_run else ''}",
        file=out,
    )

    # === 任务2：重置成本追踪 + 创建 ReviewState ===
    CostTracker().reset()
    state = ReviewState(
        target_paths=list(target),
        target_files=target_files,
        diff_mode=(mode == "diff"),
        changed_files=changed_files,
        base_branch=base,
        dry_run=dry_run,
    )

    # === 任务3：执行审查流程 ===
    from src.orchestrator.graph import create_review_workflow
    workflow = create_review_workflow()
    config = {"configurable": {"thread_id": "review-001"}}

    click.echo("正在审查...", file=out)
    final_state = workflow.invoke(state, config)

    # === 任务4：输出结果 ===
    merged_findings = final_state.get("merged_findings", [])
    agent_errors = final_state.get("agent_errors", {})

    if not json_output:
        click.echo(f"\n审查完成！发现 {len(merged_findings)} 个问题：\n")
        for finding in merged_findings:
            sev = _get_field(finding, "severity", "info")
            emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(sev, "⚪")
            file_path = _get_field(finding, "file_path")
            line_num = _get_field(finding, "line", "?")
            msg = _get_field(finding, "message")
            click.echo(f"  {emoji} [{sev}] {file_path}:{line_num} - {msg}")

        # P4: 展示 Agent 异常
        if agent_errors:
            click.echo(f"\n⚠️ 审查异常 ({len(agent_errors)} 个 Agent 失败):")
            for agent_name, errors in agent_errors.items():
                click.echo(f"  ❌ {agent_name}: {errors[0]}")
    else:
        click.echo(f"[CodeFalcon] 审查完成，发现 {len(merged_findings)} 个问题", file=out)
        if agent_errors:
            click.echo(f"[CodeFalcon] ⚠️ {len(agent_errors)} 个 Agent 失败", file=out)

    # === 任务5：生成报告（内部自动更新待办事项）===
    reporter_obj = Reporter()
    reporter_obj.generate(final_state)
    click.echo(f"\n待办事项已更新: TODOS.md", file=out)
    click.echo(f"报告已保存到 reviews/ 目录", file=out)

    # === 任务6：显示成本统计 ===
    cost = CostTracker().get_summary()
    if dry_run:
        click.echo(f"\n💰 本次审查成本: $0 (Dry-Run 模式)", file=out)
    elif cost["estimated_cost_usd"] > 0:
        click.echo(f"\n💰 本次审查成本: ${cost['estimated_cost_usd']:.6f}", file=out)
        click.echo(
            f"   Token: {cost['total_input_tokens']}入"
            f" + {cost['total_output_tokens']}出"
            f" = {cost['total_tokens']}总计",
            file=out,
        )
    else:
        click.echo(f"\n💰 本次审查成本: $0 (由规则引擎完成，无需LLM调用)", file=out)

    # === 任务7：生成 Agent Prompt（如指定 --agent-output） ===
    if agent_output:
        bridge = AgentBridge()
        mode_name = "universal" if agent_output == "file" else agent_output
        prompt = bridge.build_from_state(final_state, mode=mode_name)
        output_mode = "file" if agent_output == "file" else "both"
        dest = bridge.emit(prompt, output=output_mode)
        click.echo(f"\n🤖 Agent Prompt 已生成: {dest}", file=out)
        click.echo(f"   可将此内容发送给 AI 编码 Agent 自动修复问题", file=out)

    # === 任务8：JSON 输出模式（如指定 --json） ===
    if json_output:
        _emit_json_result(merged_findings, cost, target_files)


@cli.command()
def status():
    """查看待办事项状态"""
    try:
        with open("TODOS.md", 'r', encoding="utf-8") as f:
            click.echo(f.read())
    except FileNotFoundError:
        click.echo("暂无待办事项。")


@cli.command()
@click.argument("todo_id")
def done(todo_id):
    """标记待办事项为完成"""
    from src.output.todo_manager import TodoManager
    mgr = TodoManager()
    if mgr.mark_done(todo_id):
        click.echo(f"✅ {todo_id} 已标记为完成")
    else:
        click.echo(f"❌ 未找到待处理的 {todo_id}", err=True)


@cli.command()
@click.argument("report_path", type=click.Path(exists=True))
@click.option(
    "--format", "-f", "fmt",
    type=click.Choice(["codebuddy", "cursor", "universal", "md"]),
    default="codebuddy",
    help="输出格式: codebuddy/cursor/universal/md",
)
@click.option(
    "--output", "-o",
    type=click.Choice(["stdout", "file", "both"]),
    default="both",
    help="输出方式",
)
def export(report_path, fmt, output):
    """从历史审查报告导出 Agent Prompt 或 Markdown

    REPORT_PATH: 历史 JSON 报告路径（如 reviews/latest.json）
    """
    # Markdown 格式：直接从 JSON 生成
    if fmt == "md":
        import json
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
        from src.orchestrator.state import ReviewState, Finding
        findings = []
        for f in data.get("findings", []):
            findings.append(Finding(
                severity=f.get("severity", "info"),
                category=f.get("category", "unknown"),
                file_path=f.get("file_path", f.get("file", "")),
                line=f.get("line", 0),
                message=f.get("message", ""),
                suggestion=f.get("suggestion", ""),
                agent_source=f.get("agent_source", f.get("source", "")),
            ))
        state = ReviewState(
            target_files={fp: "" for fp in data.get("meta", {}).get("files_reviewed", [])},
            merged_findings=findings,
        )
        md_content = Reporter.build_markdown(state)
        md_path = Path(report_path).with_suffix(".md")
        md_path.write_text(md_content, encoding="utf-8")
        click.echo(f"📄 Markdown 报告已生成: {md_path}")
        return

    bridge = AgentBridge()
    prompt = bridge.build_from_report(report_path, mode=fmt)

    if prompt is None:
        click.echo("❌ 无法读取报告文件", err=True)
        sys.exit(1)

    dest = bridge.emit(prompt, output=output)
    click.echo(f"\n🤖 Agent Prompt 已导出: {dest}")


@cli.command()
def clean():
    """清理TODOS.md中的重复和低价值待办事项"""
    from src.output.todo_manager import TodoManager
    mgr = TodoManager()
    removed = mgr.cleanup(project_root=".")
    click.echo(f"🧹 已清理 {removed} 条待办事项")


@cli.command()
@click.option("--http", "use_http", is_flag=True, help="使用 HTTP/SSE 模式（默认 stdio）")
@click.option("--port", "-p", default=8765, help="HTTP 模式端口（默认 8765）")
def serve(use_http, port):
    """启动 CodeFalcon MCP Server

    编码 Agent（CodeBuddy、Cursor 等）可通过 MCP 协议直接调用 CodeFalcon 审查代码。

    启动后，在 Agent 的 MCP 配置中添加:
    {
        "codefalcon": {
            "command": "python", "args": ["-m", "src.main", "serve"]
        }
    }

    或 HTTP 模式:
    {
        "codefalcon": {
            "transport": "sse",
            "url": "http://localhost:8765/sse"
        }
    }
    """
    if use_http:
        from src.output.mcp_server import serve_http
        click.echo(f"🚀 CodeFalcon MCP Server (HTTP) 启动在 http://localhost:{port}")
        click.echo(f"   SSE 端点: http://localhost:{port}/sse")
        serve_http(port=port)
    else:
        from src.output.mcp_server import serve_stdio
        click.echo("🚀 CodeFalcon MCP Server (stdio) 启动中...", err=True)
        serve_stdio()


# ---- 辅助函数 ----

def _emit_json_result(merged_findings, cost, target_files):
    """输出纯 JSON 到 stdout（供 Agent 消费），进度信息走 stderr"""
    findings_list = []
    for f in merged_findings:
        if isinstance(f, dict):
            findings_list.append(f)
        else:
            findings_list.append({
                "severity": _get_field(f, "severity", "info"),
                "category": _get_field(f, "category", "unknown"),
                "file_path": _get_field(f, "file_path", ""),
                "line": _get_field(f, "line", 0),
                "message": _get_field(f, "message", ""),
                "suggestion": _get_field(f, "suggestion", ""),
                "agent_source": _get_field(f, "agent_source", ""),
            })

    result = {
        "status": "ok",
        "findings_count": len(findings_list),
        "findings": findings_list,
        "cost": {
            "estimated_usd": cost["estimated_cost_usd"],
            "total_tokens": cost["total_tokens"],
            "input_tokens": cost["total_input_tokens"],
            "output_tokens": cost["total_output_tokens"],
            "by_agent": cost.get("by_agent", {}),
        },
        "files_reviewed": list(target_files.keys()),
    }
    click.echo(_json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
