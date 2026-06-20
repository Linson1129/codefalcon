"""代码库搜索工具 - Agent主动搜索相关代码"""

import ast
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CodeSearcher:
    """代码搜索工具 - 供Agent在代码库中搜索相关代码段

    能力：
    - 搜索函数定义
    - 搜索函数的所有调用者
    - 搜索类/变量引用
    - 按关键字搜索
    """

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()

    def find_function_definition(self, func_name: str) -> Optional[dict]:
        """查找函数定义"""
        for py_file in self.project_root.rglob("*.py"):
            if 'tests' in str(py_file) or '__pycache__' in str(py_file):
                continue
            try:
                with open(py_file, 'r') as f:
                    content = f.read()
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name == func_name:
                            return {
                                "file": str(py_file.relative_to(self.project_root)),
                                "line": node.lineno,
                                "name": node.name,
                                "args": [arg.arg for arg in node.args.args],
                            }
            except (SyntaxError, UnicodeDecodeError):
                continue
        return None

    def find_callers(self, func_name: str) -> list[dict]:
        """查找所有调用指定函数的位置"""
        callers = []
        for py_file in self.project_root.rglob("*.py"):
            if 'tests' in str(py_file) or '__pycache__' in str(py_file):
                continue
            try:
                with open(py_file, 'r') as f:
                    content = f.read()
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        called_name = self._get_call_name(node)
                        if called_name == func_name:
                            callers.append({
                                "file": str(py_file.relative_to(self.project_root)),
                                "line": node.lineno,
                                "context": self._get_line_context(content, node.lineno),
                            })
            except (SyntaxError, UnicodeDecodeError):
                continue
        return callers

    def search_by_keyword(self, keyword: str, max_results: int = 10) -> list[dict]:
        """按关键字搜索代码"""
        results = []
        for py_file in self.project_root.rglob("*.py"):
            if 'tests' in str(py_file) or '__pycache__' in str(py_file):
                continue
            try:
                with open(py_file, 'r') as f:
                    lines = f.readlines()
                for i, line in enumerate(lines, 1):
                    if keyword.lower() in line.lower():
                        results.append({
                            "file": str(py_file.relative_to(self.project_root)),
                            "line": i,
                            "content": line.strip(),
                        })
                        if len(results) >= max_results:
                            return results
            except (UnicodeDecodeError, IOError):
                continue
        return results

    def _get_call_name(self, node: ast.Call) -> str:
        """提取调用表达式中的函数名"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    def _get_line_context(self, content: str, line_num: int, context_lines: int = 2) -> str:
        """获取指定行及其上下文"""
        lines = content.split('\n')
        start = max(0, line_num - context_lines - 1)
        end = min(len(lines), line_num + context_lines)
        return '\n'.join(lines[start:end])
