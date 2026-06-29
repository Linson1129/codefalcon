"""增量 Diff 分析器 — 使用 git diff 识别变更文件及依赖链

支持两种模式：
1. diff mode: 仅审查 git diff 变更的文件
2. full mode (默认): 全量审查所有目标文件
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DiffAnalyzer:
    """基于 git diff 的增量分析器"""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()

    def get_changed_files(
        self,
        base_branch: str = "main",
        include_untracked: bool = True,
    ) -> list[str]:
        """获取自 base_branch 以来的变更文件列表

        Args:
            base_branch: 对比的基准分支，默认 main
            include_untracked: 是否包含未跟踪的新文件

        Returns:
            变更的 .py 文件相对路径列表
        """
        changed = set()

        # 1) 已跟踪文件的 diff
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_branch, "HEAD"],
                capture_output=True, text=True,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.endswith(".py"):
                        changed.add(line)
        except FileNotFoundError:
            logger.warning("[DiffAnalyzer] git 命令不可用，回退到全量模式")
            return []

        # 2) 工作区未暂存的变更
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True, text=True,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.endswith(".py"):
                        changed.add(line)
        except Exception:
            pass

        # 3) 未跟踪的新 .py 文件
        if include_untracked:
            try:
                result = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    capture_output=True, text=True,
                    cwd=str(self.project_root),
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if line.endswith(".py"):
                            changed.add(line)
            except Exception:
                pass

        return sorted(changed)

    def get_changed_files_since(
        self,
        since_ref: str = "HEAD~1",
    ) -> list[str]:
        """获取自某次提交以来的变更（diff 模式常用）

        Args:
            since_ref: 起点引用，如 HEAD~1, origin/main
        """
        # 先试 merge-base
        changed = set()
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{since_ref}..."],
                capture_output=True, text=True,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.endswith(".py"):
                        changed.add(line)
        except Exception:
            pass

        # 工作区变更
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True, text=True,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.endswith(".py"):
                        changed.add(line)
        except Exception:
            pass

        return sorted(changed)

    def read_changed_files(
        self,
        base_branch: str = "main",
    ) -> dict[str, str]:
        """读取变更文件的内容

        Returns:
            {file_path: content} 字典
        """
        changed = self.get_changed_files(base_branch)
        if not changed:
            return {}

        files = {}
        for rel_path in changed:
            abs_path = self.project_root / rel_path
            if abs_path.is_file():
                try:
                    files[rel_path] = abs_path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"[DiffAnalyzer] 读取文件失败 {rel_path}: {e}")
        return files

    @staticmethod
    def is_git_repo(root: str = ".") -> bool:
        """检查当前目录是否是 git 仓库"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True, text=True,
                cwd=root,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
