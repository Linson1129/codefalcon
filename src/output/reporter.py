"""报告生成器 - 生成JSON和Markdown双格式审查报告

输出结构:
  reviews/
    ├── 2026-06-20/           ← 按日期分文件夹
    │   ├── 150000.json       ← 单次审查JSON
    │   └── 150000.md         ← 单次审查Markdown
    ├── archive/              ← 压缩后归档处
    │   └── 2026-06-20/
    └── summaries/            ← 每5次压缩摘要
        └── 2026-06-20-HHmmss-summary.json
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from src.orchestrator.state import Finding, ReviewState
from src.review.prioritizer import Prioritizer

logger = logging.getLogger(__name__)

COMPRESS_EVERY = 5  # 每N次审查触发一次压缩


class Reporter:
    """审查报告生成器
    """

    def __init__(self, output_dir: str = "reviews"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._counter_file = self.output_dir / ".review_count"

    def generate(self, state):
        """生成审查报告（接受 dict 或 ReviewState）"""
        state = self._normalize_state(state)
        now = datetime.now()
        today_dir = self.output_dir / now.strftime("%Y-%m-%d")
        today_dir.mkdir(parents=True, exist_ok=True)

        time_str = now.strftime("%H%M%S")

        # 生成JSON
        json_path = today_dir / f"{time_str}.json"
        json_data = self._build_json_report(state, now)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        logger.info(f"[Reporter] JSON报告已保存: {json_path}")

        # 生成Markdown
        md_path = today_dir / f"{time_str}.md"
        md_content = self._build_markdown_report(state, now)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        logger.info(f"[Reporter] Markdown报告已保存: {md_path}")

        # 更新待办事项
        from src.output.todo_manager import TodoManager
        todo_mgr = TodoManager()
        todo_mgr.append_todos(state.todos)

        # 计数 + 触发压缩
        count = self._increment_count()
        if count % COMPRESS_EVERY == 0:
            self._compress_recent()

        return state

    # ---- 内部方法 ----

    def _normalize_state(self, state):
        """将 dict 转换为 ReviewState"""
        if isinstance(state, ReviewState):
            return state
        findings = [
            f if isinstance(f, Finding) else Finding(**f)
            for f in state.get("merged_findings", [])
        ]
        return ReviewState(
            target_paths=state.get("target_paths", []),
            target_files=state.get("target_files", {}),
            merged_findings=findings,
            todos=state.get("todos", []),
            token_usage=state.get("token_usage", {}),
        )

    def _build_json_report(self, state: ReviewState, now: datetime) -> dict:
        prioritizer = Prioritizer()
        summary = prioritizer.get_summary(state.merged_findings)
        from src.utils.cost_tracker import CostTracker
        cost_summary = CostTracker().get_summary()
        return {
            "meta": {
                "timestamp": now.isoformat(),
                "version": "0.1.0",
                "files_reviewed": list(state.target_files.keys()),
            },
            "cost": {
                "estimated_usd": cost_summary["estimated_cost_usd"],
                "total_tokens": cost_summary["total_tokens"],
                "input_tokens": cost_summary["total_input_tokens"],
                "output_tokens": cost_summary["total_output_tokens"],
                "by_agent": cost_summary["by_agent"],
            },
            "summary": summary,
            "findings": [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "file": f.file_path,
                    "line": f.line,
                    "message": f.message,
                    "suggestion": f.suggestion,
                    "source": f.agent_source,
                }
                for f in state.merged_findings
            ],
        }

    def _build_markdown_report(self, state: ReviewState, now: datetime) -> str:
        prioritizer = Prioritizer()
        summary = prioritizer.get_summary(state.merged_findings)
        lines = [
            f"# 🔍 CodeFalcon 审查报告",
            f"",
            f"**审查时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**审查文件数**: {len(state.target_files)}",
            f"",
            f"## 📊 摘要",
            f"",
            f"| 类别 | error | warning | info | 合计 |",
            f"|------|-------|---------|------|------|",
        ]
        for cat in ["security", "bug", "performance", "style"]:
            cat_count = summary["by_category"].get(cat, 0)
            err = sum(1 for f in state.merged_findings if f.category == cat and f.severity == "error")
            warn = sum(1 for f in state.merged_findings if f.category == cat and f.severity == "warning")
            info = sum(1 for f in state.merged_findings if f.category == cat and f.severity == "info")
            lines.append(f"| {cat} | {err} | {warn} | {info} | {cat_count} |")
        lines.extend([
            f"| **总计** | {summary['by_severity']['error']} | "
            f"{summary['by_severity']['warning']} | "
            f"{summary['by_severity']['info']} | "
            f"{summary['total']} |",
            f"",
            f"## 📋 问题详情",
            f"",
        ])
        if not state.merged_findings:
            lines.append("✅ 未发现问题！代码质量良好。")
        else:
            for i, f in enumerate(state.merged_findings, 1):
                emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(f.severity, "⚪")
                lines.append(f"### {i}. {emoji} [{f.severity.upper()}] [{f.category}] {f.file_path}:{f.line}")
                lines.append(f"")
                lines.append(f"**问题**: {f.message}")
                if f.suggestion:
                    lines.append(f"**建议**: {f.suggestion}")
                lines.append(f"**来源**: {f.agent_source}")
                lines.append(f"")
        from src.utils.cost_tracker import CostTracker
        cost_summary = CostTracker().get_summary()
        if cost_summary["total_tokens"] > 0:
            lines.append(f"## 💰 Token消耗")
            lines.append(f"")
            lines.append(f"- **总Token**: {cost_summary['total_tokens']} (入{cost_summary['total_input_tokens']} + 出{cost_summary['total_output_tokens']})")
            lines.append(f"- **预估费用**: ${cost_summary['estimated_cost_usd']:.6f}")
            for agent, info in cost_summary.get("by_agent", {}).items():
                lines.append(f"- {agent}: {info['tokens']} tokens ({info['calls']}次调用)")
            lines.append(f"")
        lines.append(f"---")
        lines.append(f"*由 CodeFalcon v0.1.0 生成*")
        return '\n'.join(lines)

    # ---- 审查计数 ----

    def _read_count(self) -> int:
        """读取当前审查次数"""
        if self._counter_file.exists():
            return int(self._counter_file.read_text().strip())
        return 0

    def _increment_count(self) -> int:
        """递增并返回审查次数"""
        count = self._read_count() + 1
        self._counter_file.write_text(str(count))
        return count

    # ---- 压缩机制 ----

    def _compress_recent(self):
        """每 N 次审查后，压缩之前的报告（保留本次）"""
        logger.info(f"[Reporter] 触发压缩（每{COMPRESS_EVERY}次）...")

        # 搜集 N+1 个最近报告，排除最新的（本次刚生成的）
        all_recent = self._collect_recent_reports(COMPRESS_EVERY + 1)
        if len(all_recent) <= 1:
            logger.warning("[Reporter] 无可压缩报告")
            return

        # 最新的一个保留不动，其余参与压缩
        recent = all_recent[1:]  # 排除最新的
        if not recent:
            return

        # 合并去重
        merged = self._merge_findings(recent)
        logger.info(f"[Reporter] 压缩后: {len(recent)}次审查 → {len(merged)}条唯一发现问题")

        # 生成压缩摘要
        self._write_compression_summary(recent, merged)

        # 归档原始报告
        self._archive_reports(recent)

        logger.info("[Reporter] 压缩完成")

    def _collect_recent_reports(self, n: int) -> list[dict]:
        """搜集最近 N 个 JSON 报告"""
        reports = []
        # 按日期文件夹倒序收集
        date_dirs = sorted(
            [d for d in self.output_dir.iterdir() if d.is_dir() and d.name != "archive" and d.name != "summaries"],
            reverse=True,
        )
        for date_dir in date_dirs:
            json_files = sorted(date_dir.glob("*.json"), reverse=True)
            for jf in json_files:
                try:
                    data = json.loads(jf.read_text(encoding="utf-8"))
                    data["_path"] = str(jf)
                    data["_md_path"] = str(jf.with_suffix(".md"))
                    reports.append(data)
                    if len(reports) >= n:
                        return reports
                except (json.JSONDecodeError, KeyError):
                    continue
        return reports

    def _merge_findings(self, reports: list[dict]) -> list[dict]:
        """合并多个报告的发现，去重"""
        seen = set()
        merged = []
        for r in reports:
            for f in r.get("findings", []):
                key = f"{f.get('file')}:{f.get('line')}:{f.get('category')}"
                if key not in seen:
                    seen.add(key)
                    merged.append(f)
        return merged

    def _write_compression_summary(self, reports: list[dict], merged: list[dict]):
        """生成压缩摘要"""
        now = datetime.now()
        summaries_dir = self.output_dir / "summaries"
        summaries_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "compressed_at": now.isoformat(),
            "report_count": len(reports),
            "unique_findings": len(merged),
            "findings": merged,
            "source_reports": [r["_path"] for r in reports],
        }
        json_path = summaries_dir / f"{now.strftime('%Y-%m-%d-%H%M%S')}-summary.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info(f"[Reporter] 压缩摘要已保存: {json_path}")

    def _archive_reports(self, reports: list[dict]):
        """将原始报告移动到 archive 目录"""
        archive_dir = self.output_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        for r in reports:
            src_json = Path(r["_path"])
            src_md = Path(r.get("_md_path", ""))
            # 按原始日期放入 archive 子目录
            dest_dir = archive_dir / src_json.parent.name
            dest_dir.mkdir(parents=True, exist_ok=True)

            if src_json.exists():
                shutil.move(str(src_json), str(dest_dir / src_json.name))
            if src_md.exists():
                shutil.move(str(src_md), str(dest_dir / src_md.name))
