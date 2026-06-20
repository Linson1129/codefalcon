"""待办事项管理器 - 读写TODOS.md，人机共享

TODOS.md 格式：
  # 📋 CodeFalcon 待办事项
  > 最后更新: 2026-06-20 15:30:00

  ## 🔴 待处理 (3)
  - [ ] [2026-06-20] **TODO-001** `file.py:10` | 🔴 error | SQL注入漏洞
    - 💡 改用参数化查询

  ## ✅ 已完成 (1)
  - [x] [2026-06-19] **TODO-000** `old.py:5` | 🔴 error | 已修复的问题
"""

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TODOS_FILE = "TODOS.md"

# 解析每一行的正则
TODO_LINE_RE = re.compile(
    r'- \[(.)\] \[(\d{4}-\d{2}-\d{2})\] \*\*(TODO-\d+)\*\* '
    r'`(.+?):(\d+)` \| (.+?) \| (.+)'
)


class TodoManager:
    """待办事项管理器"""

    def __init__(self, filepath: str = TODOS_FILE):
        self.filepath = Path(filepath)
        self._next_seq_cache = None

    # ---- 读取 ----

    def read_todos(self) -> list[dict]:
        """读取当前所有待办事项"""
        if not self.filepath.exists():
            return []
        content = self.filepath.read_text(encoding="utf-8")
        todos = []
        for m in TODO_LINE_RE.finditer(content):
            checked, date_str, todo_id, file, line, severity_raw, message = m.groups()
            # 剥离 emoji 前缀，只保留 "error" / "warning" / "info"
            severity = severity_raw.strip()
            for sev_key in ("error", "warning", "info"):
                if sev_key in severity:
                    severity = sev_key
                    break
            todos.append({
                "id": todo_id,
                "date": date_str,
                "file": file,
                "line": int(line),
                "severity": severity,
                "message": message.strip(),
                "status": "done" if checked.lower() == "x" else "pending",
            })
        return todos

    def get_pending(self) -> list[dict]:
        """获取待处理的待办"""
        return [t for t in self.read_todos() if t["status"] == "pending"]

    def get_done(self) -> list[dict]:
        """获取已完成的待办"""
        return [t for t in self.read_todos() if t["status"] == "done"]

    # ---- 序号管理 ----

    def _get_max_seq(self) -> int:
        """获取当前最大TODO序号"""
        todos = self.read_todos()
        if not todos:
            return 0
        nums = []
        for t in todos:
            try:
                nums.append(int(t["id"].replace("TODO-", "")))
            except (ValueError, AttributeError):
                continue
        return max(nums) if nums else 0

    def _next_seq(self) -> int:
        return self._get_max_seq() + 1

    # ---- 标记完成 ----

    def mark_done(self, todo_id: str) -> bool:
        """将指定 TODO 标记为已完成"""
        todos = self.read_todos()
        found = False
        for t in todos:
            if t["id"] == todo_id and t["status"] == "pending":
                t["status"] = "done"
                found = True
                break

        if not found:
            logger.warning(f"[TodoManager] 未找到待处理的 {todo_id}")
            return False

        logger.info(f"[TodoManager] {todo_id} → 已完成")

        # 重新写入分区格式
        done = [t for t in todos if t["status"] == "done"]
        pending = [t for t in todos if t["status"] == "pending"]

        lines = [
            "# 📋 CodeFalcon 待办事项",
            "",
            f"> 最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        lines.append(f"## 🔴 待处理 ({len(pending)})")
        lines.append("")
        for t in pending:
            emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(t["severity"], "⚪")
            lines.append(
                f"- [ ] [{t['date']}] **{t['id']}** "
                f"`{t['file']}:{t['line']}` | {emoji} {t['severity']} | {t['message']}"
            )
            if t.get("suggestion"):
                lines.append(f"  - 💡 {t['suggestion']}")

        lines.append("")
        if done:
            lines.append(f"## ✅ 已完成 ({len(done)})")
            lines.append("")
            for t in done:
                emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(t["severity"], "⚪")
                lines.append(
                    f"- [x] [{t['date']}] **{t['id']}** "
                    f"`{t['file']}:{t['line']}` | {emoji} {t['severity']} | {t['message']}"
                )
                if t.get("suggestion"):
                    lines.append(f"  - 💡 {t['suggestion']}")
            lines.append("")

        self.filepath.write_text('\n'.join(lines) + '\n', encoding="utf-8")
        return True

    # ---- 写入 ----

    def append_todos(self, new_todos: list[dict]):
        """追加新待办（自动分配全局序号 + 日期标注 + 内容去重）"""
        existing = self.read_todos()
        # 内容去重：file:line:message
        existing_keys = {
            f"{t['file']}:{t['line']}:{t['message']}" for t in existing
        }

        today = datetime.now().strftime("%Y-%m-%d")
        next_num = self._next_seq()

        to_append = []
        for todo in new_todos:
            key = f"{todo.get('file', '')}:{todo.get('line', 0)}:{todo.get('message', '')}"
            if key in existing_keys:
                continue
            existing_keys.add(key)
            todo["_seq"] = next_num
            todo["_date"] = today
            to_append.append(todo)
            next_num += 1

        if not to_append:
            logger.info("[TodoManager] 无新增待办事项")
            return

        # 分离 pending 和 done 区块写入
        self._write_organized(existing, to_append)

        logger.info(f"[TodoManager] 新增 {len(to_append)} 条待办事项，当前共 {next_num - 1} 条")

    def _write_organized(self, existing: list[dict], new_items: list[dict]):
        """按 pending/done 分区写入，新项加到 pending 区"""
        done = [t for t in existing if t["status"] == "done"]
        pending_existing = [t for t in existing if t["status"] == "pending"]

        lines = [
            "# 📋 CodeFalcon 待办事项",
            "",
            f"> 最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # 新增的自动归入 pending 区
        new_pending = []
        for t in new_items:
            new_pending.append({
                "id": f"TODO-{t['_seq']:03d}",
                "date": t["_date"],
                "file": t.get("file", ""),
                "line": t.get("line", 0),
                "severity": t.get("severity", "info"),
                "message": t.get("message", ""),
                "suggestion": t.get("suggestion", ""),
                "status": "pending",
            })

        all_pending = pending_existing + new_pending

        # 🔴 待处理
        lines.append(f"## 🔴 待处理 ({len(all_pending)})")
        lines.append("")
        for t in all_pending:
            emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(t["severity"], "⚪")
            lines.append(
                f"- [ ] [{t['date']}] **{t['id']}** "
                f"`{t['file']}:{t['line']}` | {emoji} {t['severity']} | {t['message']}"
            )
            if t.get("suggestion"):
                lines.append(f"  - 💡 {t['suggestion']}")

        lines.append("")

        # ✅ 已完成
        if done:
            lines.append(f"## ✅ 已完成 ({len(done)})")
            lines.append("")
            for t in done:
                emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(t["severity"], "⚪")
                lines.append(
                    f"- [x] [{t['date']}] **{t['id']}** "
                    f"`{t['file']}:{t['line']}` | {emoji} {t['severity']} | {t['message']}"
                )
                if t.get("suggestion"):
                    lines.append(f"  - 💡 {t['suggestion']}")
            lines.append("")

        self.filepath.write_text('\n'.join(lines) + '\n', encoding="utf-8")
