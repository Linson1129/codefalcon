"""CodeFalcon CLI入口"""

import sys
import click
from pathlib import Path

from src.utils.logger import setup_logger
from src.utils.cost_tracker import CostTracker
from src.orchestrator.state import ReviewState
from src.output.reporter import Reporter


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
def review(target, verbose):
    """审查指定的文件或目录"""
    if not target:
        click.echo("请指定要审查的文件或目录", err=True)
        sys.exit(1)

    click.echo("CodeFalcon v0.1.0 — 开始审查...")
    click.echo("")

    # === 任务1：读取所有目标文件 ===
    target_files = {}
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

    click.echo(f"找到 {len(target_files)} 个 Python 文件")

    # === 任务2：重置成本追踪 + 创建 ReviewState ===
    CostTracker().reset()
    state = ReviewState(
        target_paths=list(target),
        target_files=target_files,
    )

    # === 任务3：执行审查流程 ===
    from src.orchestrator.graph import create_review_workflow
    workflow = create_review_workflow()
    config = {"configurable": {"thread_id": "review-001"}}

    click.echo("正在审查...")
    final_state = workflow.invoke(state, config)

    # === 任务4：输出结果 ===
    # final_state 是 dict，merged_findings 是 list[dict]
    merged_findings = final_state.get("merged_findings", [])
    click.echo(f"\n审查完成！发现 {len(merged_findings)} 个问题：\n")
    for finding in merged_findings:
        sev = _get_field(finding, "severity", "info")
        emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(sev, "⚪")
        file_path = _get_field(finding, "file_path")
        line_num = _get_field(finding, "line", "?")
        msg = _get_field(finding, "message")
        click.echo(f"  {emoji} [{sev}] {file_path}:{line_num} - {msg}")

    # === 任务5：生成报告（内部自动更新待办事项）===
    reporter_obj = Reporter()
    reporter_obj.generate(final_state)
    click.echo(f"\n待办事项已更新: TODOS.md")
    click.echo(f"报告已保存到 reviews/ 目录")

    # === 任务6：显示成本统计 ===
    cost = CostTracker().get_summary()
    if cost["estimated_cost_usd"] > 0:
        click.echo(f"\n💰 本次审查成本: ${cost['estimated_cost_usd']:.6f}")
        click.echo(
            f"   Token: {cost['total_input_tokens']}入"
            f" + {cost['total_output_tokens']}出"
            f" = {cost['total_tokens']}总计"
        )
    else:
        click.echo(f"\n💰 本次审查成本: $0 (由规则引擎完成，无需LLM调用)")


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


if __name__ == "__main__":
    cli()
