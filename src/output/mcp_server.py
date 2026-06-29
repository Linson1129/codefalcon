"""CodeFalcon MCP Server — 让编码 Agent 可以直接调用的代码审查工具

启动方式:
  codefalcon serve           # stdio 模式（默认，适合 CodeBuddy 等）
  codefalcon serve --http    # HTTP/SSE 模式（适合 Web 客户端）

编码 Agent 调用:
  → tool: review_code(paths=["src/main.py", "src/utils.py"])
  ← 返回: 结构化审查结果 (JSON)，同时输出文件到 reviews/ 和 .codefalcon/

用户全程可看到:
  1. Agent 调用 review_code 工具
  2. CodeFalcon 审查进度（stderr 输出）
  3. 审查结果（结构化 JSON 返回给 Agent）
  4. Agent 根据结果自动修复代码
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---- 核心审查函数（被 MCP 工具调用）----

def run_review(target_paths: list[str], project_root: str = ".") -> dict[str, Any]:
    """执行完整的审查流程，返回结构化结果

    Args:
        target_paths: 要审查的文件/目录路径列表
        project_root: 项目根目录

    Returns:
        {
            "status": "ok" | "error",
            "findings_count": int,
            "findings": [...],
            "cost": {...},
            "reports": {"json": "path", "md": "path"},
            "agent_prompt": "path",
            "summary_text": "..."
        }
    """
    from src.utils.cost_tracker import CostTracker
    from src.orchestrator.state import ReviewState
    from src.output.reporter import Reporter
    from src.output.agent_bridge import AgentBridge

    # 1. 收集文件
    target_files = {}
    root = Path(project_root)
    for t in target_paths:
        t_path = (root / t).resolve() if not Path(t).is_absolute() else Path(t)
        if not t_path.exists():
            logger.warning(f"路径不存在，跳过: {t_path}")
            continue
        if t_path.is_file() and t_path.suffix == ".py":
            target_files[str(t_path)] = t_path.read_text(encoding="utf-8")
        elif t_path.is_dir():
            for py_file in t_path.rglob("*.py"):
                if py_file.is_file():
                    target_files[str(py_file)] = py_file.read_text(encoding="utf-8")

    if not target_files:
        return {
            "status": "error",
            "error": "No Python files found",
            "findings_count": 0,
            "findings": [],
        }

    # 2. 重置成本 + 创建状态
    CostTracker().reset()
    state = ReviewState(
        target_paths=target_paths,
        target_files=target_files,
    )

    # 3. 执行审查 DAG
    from src.orchestrator.graph import create_review_workflow
    workflow = create_review_workflow()
    config = {"configurable": {"thread_id": "mcp-review"}}
    final_state = workflow.invoke(state, config)

    # 4. 生成报告
    reporter = Reporter()
    reporter.generate(final_state)

    # 5. 生成 Agent Prompt（通用格式）
    bridge = AgentBridge()
    prompt = bridge.build_from_state(final_state, mode="universal")
    dest = bridge.emit(prompt, output="file")

    # 6. 构建返回结果
    merged = final_state.get("merged_findings", [])
    cost = CostTracker().get_summary()

    findings_list = []
    for f in merged:
        if isinstance(f, dict):
            findings_list.append(f)
        else:
            findings_list.append({
                "severity": getattr(f, "severity", "info"),
                "category": getattr(f, "category", "unknown"),
                "file_path": getattr(f, "file_path", ""),
                "line": getattr(f, "line", 0),
                "message": getattr(f, "message", ""),
                "suggestion": getattr(f, "suggestion", ""),
                "agent_source": getattr(f, "agent_source", ""),
            })

    # 查找刚生成的报告路径（Reporter 扁平存储在 reviews/ 根目录）
    review_root = Path("reviews")
    json_reports = sorted(
        [f for f in review_root.glob("*.json") if f.name != ".review_count"],
        key=lambda f: f.stat().st_mtime, reverse=True,
    ) if review_root.exists() else []
    md_reports = sorted(
        review_root.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True,
    ) if review_root.exists() else []

    return {
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
        "reports": {
            "json": str(json_reports[0]) if json_reports else "",
            "md": str(md_reports[0]) if md_reports else "",
        },
        "agent_prompt_file": str(dest),
        "summary_text": _build_summary_text(findings_list),
    }


def _build_summary_text(findings: list[dict]) -> str:
    """生成人类可读摘要"""
    sev_counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        s = f.get("severity", "info")
        sev_counts[s] = sev_counts.get(s, 0) + 1

    return (
        f"审查完成：发现 {len(findings)} 个问题 "
        f"({sev_counts['error']} error, "
        f"{sev_counts['warning']} warning, "
        f"{sev_counts['info']} info)"
    )


# ---- MCP Server 定义 ----

def create_mcp_server() -> Any:
    """创建 CodeFalcon MCP Server"""
    from mcp.server import Server
    from mcp.types import Tool, TextContent

    server = Server("codefalcon-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="review_code",
                description=(
                    "对指定的 Python 代码文件或目录执行多 Agent 智能代码审查。"
                    "4 个并行 Agent 分别检查安全漏洞、Bug/性能、架构设计、规范符合性。"
                    "审查结果会自动保存到 reviews/ 和 .codefalcon/ 目录。"
                    "返回结构化 JSON 包含所有发现的问题、严重度、修复建议和成本统计。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要审查的文件或目录路径列表，如 ['src/', 'app.py']",
                        },
                        "project_root": {
                            "type": "string",
                            "description": "项目根目录，默认当前目录",
                            "default": ".",
                        },
                    },
                    "required": ["paths"],
                },
            ),
            Tool(
                name="get_review_status",
                description=(
                    "获取上次审查的待办事项状态和最近审查报告列表。"
                    "返回 TODOS.md 中的待办事项和最近的审查报告路径。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="get_review_report",
                description=(
                    "读取指定审查报告的内容。传入 JSON 或 Markdown 报告文件路径，"
                    "返回完整的审查结果用于分析。Agent 可以据此逐项修复代码问题。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "report_path": {
                            "type": "string",
                            "description": "报告文件路径，如 'reviews/2026-06-24/143217.json'",
                        },
                    },
                    "required": ["report_path"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "review_code":
            paths = arguments.get("paths", [])
            project_root = arguments.get("project_root", ".")
            result = run_review(paths, project_root)
            return [TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2),
            )]

        elif name == "get_review_status":
            from src.output.todo_manager import TodoManager
            mgr = TodoManager()
            pending = mgr.get_pending()
            done = mgr.get_done()

            # 找最近的报告
            reviews_dir = Path("reviews")
            recent_reports = []
            if reviews_dir.exists():
                date_dirs = sorted(
                    [d for d in reviews_dir.iterdir() if d.is_dir()],
                    reverse=True,
                )
                for dd in date_dirs[:3]:
                    json_files = sorted(dd.glob("*.json"), reverse=True)
                    recent_reports.extend([str(f) for f in json_files[:3]])

            status = {
                "pending_count": len(pending),
                "pending_todos": pending[:10],
                "done_count": len(done),
                "recent_reports": recent_reports[:5],
            }
            return [TextContent(
                type="text",
                text=json.dumps(status, ensure_ascii=False, indent=2),
            )]

        elif name == "get_review_report":
            report_path = arguments.get("report_path", "")
            p = Path(report_path)
            if not p.exists():
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": f"Report not found: {report_path}"}),
                )]
            content = p.read_text(encoding="utf-8")
            return [TextContent(
                type="text",
                text=content,
            )]

        else:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"}),
            )]

    return server


# ---- CLI 入口 ----

def serve_stdio():
    """以 stdio 模式启动 MCP Server"""
    import asyncio
    from mcp.server.stdio import stdio_server

    logging.basicConfig(level=logging.WARNING)

    async def main():
        server = create_mcp_server()
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(main())


def serve_http(host: str = "0.0.0.0", port: int = 8765):
    """以 HTTP/SSE 模式启动 MCP Server"""
    import asyncio
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route

    server = create_mcp_server()
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )

    async def health(request):
        from starlette.responses import JSONResponse
        return JSONResponse({"status": "ok", "service": "codefalcon-mcp"})

    app = Starlette(
        debug=False,
        routes=[
            Route("/health", health),
            Route("/sse", handle_sse),
        ],
    )

    import uvicorn
    uvicorn.run(app, host=host, port=port)
