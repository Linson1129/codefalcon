"""报告生成器 - 精简版：仅存 JSON + 滚动窗口

设计原则:
  1. 只存 JSON（MD 按需通过 codefalcon export 生成）
  2. 滚动窗口：保留最新 MAX_WINDOW 个报告，旧的自动删除
  3. latest.json 永远指向最新一次审查
  4. 无 archive、summaries、压缩机制（冗余数据已被滚动窗口取代）

输出结构:
  reviews/
    ├── latest.json            ← 永远是最新一次审查
    ├── 2026-06-24-143000.json  ← 最近 MAX_WINDOW 个按时间戳命名
    ├── 2026-06-24-143500.json
    ├── ...
    └── .review_count
"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from src.orchestrator.state import Finding, ReviewState
from src.review.prioritizer import Prioritizer

logger = logging.getLogger(__name__)

MAX_WINDOW = 10  # 最多保留多少个历史报告


class Reporter:
    """审查报告生成器（精简版）"""

    def __init__(self, output_dir: str = "reviews"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._counter_file = self.output_dir / ".review_count"

    def generate(self, state) -> ReviewState:
        """生成审查报告——只存 JSON，自动淘汰旧文件"""
        state = self._normalize_state(state)
        now = datetime.now()
        filename = now.strftime("%Y-%m-%d-%H%M%S") + ".json"
        json_path = self.output_dir / filename

        # 写入 JSON
        json_data = self._build_json_report(state, now)
        json_path.write_text(
            json.dumps(json_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[Reporter] 报告已保存: {json_path}")

        # 更新 latest.json 符号链接
        self._update_latest(json_path)

        # 更新待办事项
        from src.output.todo_manager import TodoManager
        TodoManager().append_todos(state.todos)

        # 递增计数 + 淘汰旧文件
        self._increment_count()
        self._evict_old()

        return state

    # ---- 按需生成 Markdown ----

    @staticmethod
    def build_markdown(state) -> str:
        """从 state 生成 Markdown 报告（供 export 命令按需调用）"""
        state = Reporter._normalize_static(state)
        now = datetime.now()
        prioritizer = Prioritizer()
        summary = prioritizer.get_summary(state.merged_findings)

        def sev(f): return f.severity if not isinstance(f, dict) else f.get("severity", "info")
        def cat(f): return f.category if not isinstance(f, dict) else f.get("category", "unknown")
        def fp(f): return f.file_path if not isinstance(f, dict) else f.get("file_path", f.get("file", ""))
        def ln(f): return f.line if not isinstance(f, dict) else f.get("line", 0)
        def msg(f): return f.message if not isinstance(f, dict) else f.get("message", "")
        def sug(f): return f.suggestion if not isinstance(f, dict) else f.get("suggestion", "")
        def src(f): return f.agent_source if not isinstance(f, dict) else f.get("agent_source", f.get("source", ""))

        lines = [
            "# 🔍 CodeFalcon 审查报告",
            "",
            f"**审查时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**审查文件数**: {len(state.target_files)}",
            "",
            "## 📊 摘要",
            "",
            "| 类别 | error | warning | info | 合计 |",
            "|------|-------|---------|------|------|",
        ]
        categories = ["security", "bug", "performance", "style", "architecture", "spec"]
        merged = state.merged_findings
        for c in categories:
            err = sum(1 for f in merged if cat(f) == c and sev(f) == "error")
            warn = sum(1 for f in merged if cat(f) == c and sev(f) == "warning")
            info = sum(1 for f in merged if cat(f) == c and sev(f) == "info")
            total = err + warn + info
            if total > 0:
                lines.append(f"| {c} | {err} | {warn} | {info} | {total} |")

        err_total = sum(1 for f in merged if sev(f) == "error")
        warn_total = sum(1 for f in merged if sev(f) == "warning")
        info_total = sum(1 for f in merged if sev(f) == "info")
        lines.append(f"| **总计** | {err_total} | {warn_total} | {info_total} | {len(merged)} |")
        lines.extend(["", "## 📋 问题详情", ""])

        if not merged:
            lines.append("✅ 未发现问题！代码质量良好。")
        else:
            for i, f in enumerate(merged, 1):
                s = sev(f)
                emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(s, "⚪")
                lines.append(f"### {i}. {emoji} [{s.upper()}] [{cat(f)}] {fp(f)}:{ln(f)}")
                lines.extend(["", f"**问题**: {msg(f)}"])
                if sug(f):
                    lines.append(f"**建议**: {sug(f)}")
                lines.extend([f"**来源**: {src(f)}", ""])

        from src.utils.cost_tracker import CostTracker
        cost = CostTracker().get_summary()
        if cost["total_tokens"] > 0:
            lines.extend([
                "## 💰 Token消耗",
                "",
                f"- **总Token**: {cost['total_tokens']} (入{cost['total_input_tokens']} + 出{cost['total_output_tokens']})",
                f"- **预估费用**: ${cost['estimated_cost_usd']:.6f}",
            ])
            for agent, info in cost.get("by_agent", {}).items():
                lines.append(f"- {agent}: {info['tokens']} tokens ({info['calls']}次调用)")

        # P4: 展示 Agent 审查异常
        if hasattr(state, "agent_errors") and state.agent_errors:
            lines.extend(["", "## ⚠️ 审查异常", ""])
            for agent_name, errors in state.agent_errors.items():
                lines.append(f"- **{agent_name}**: {', '.join(errors)}")

        lines.extend(["", "---", "*由 CodeFalcon v0.1.0 生成*"])
        return "\n".join(lines)

    # ---- 内部 ----

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
            filtered_files=state.get("filtered_files", {}),
            related_code=state.get("related_code", {}),
            dependency_graph=state.get("dependency_graph", {}),
            spec_content=state.get("spec_content", ""),
            rule_findings=[],
            style_findings=[],
            skill_findings=[],
            agent_a_findings=[],
            agent_b_findings=[],
            agent_c_findings=[],
            agent_d_findings=[],
            merged_findings=findings,
            todos=state.get("todos", []),
            current_stage=state.get("current_stage", ""),
            poisoning_detection_enabled=state.get("poisoning_detection_enabled", True),
        )

    @classmethod
    def _normalize_static(cls, state):
        """静态版本的 normalize，供 build_markdown 使用"""
        return cls(".")._normalize_state(state)

    def _build_json_report(self, state: ReviewState, now: datetime) -> dict:
        prioritizer = Prioritizer()
        summary = prioritizer.get_summary(state.merged_findings)
        from src.utils.cost_tracker import CostTracker
        cost_summary = CostTracker().get_summary()

        report = {
            "meta": {
                "timestamp": now.isoformat(),
                "version": "0.1.0",
                "files_reviewed": list(state.target_files.keys()),
                "mode": "diff" if state.diff_mode else "full",
                "dry_run": state.dry_run,
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

        # P4: 附加 Agent 错误信息
        if state.agent_errors:
            report["agent_errors"] = state.agent_errors

        return report

    def _update_latest(self, json_path: Path):
        """更新 latest.json 指向最新报告"""
        latest = self.output_dir / "latest.json"
        shutil.copy2(str(json_path), str(latest))
        logger.info(f"[Reporter] latest.json 已更新")

    def _evict_old(self):
        """淘汰超过 MAX_WINDOW 个的旧报告"""
        json_files = sorted(
            [f for f in self.output_dir.glob("*.json") if f.name != "latest.json"],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for old in json_files[MAX_WINDOW:]:
            old.unlink(missing_ok=True)
            logger.info(f"[Reporter] 淘汰旧报告: {old}")

    # ---- 计数 ----

    def _read_count(self) -> int:
        if self._counter_file.exists():
            return int(self._counter_file.read_text().strip())
        return 0

    def _increment_count(self) -> int:
        count = self._read_count() + 1
        self._counter_file.write_text(str(count))
        return count


