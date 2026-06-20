"""代码索引构建器 - 构建函数调用图索引（MVP用AST实现）"""

import ast
import logging
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


class CodeIndexer:
    """代码索引构建器

    MVP阶段：基于AST构建函数调用图索引
    预留接口：未来可接入FAISS做语义检索
    """

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.index: dict[str, dict] = {}  # 内存索引

    def build_index(self) -> dict:
        """构建代码索引

        Returns:
            {
                "functions": {func_name: {"file": "...", "line": 1, "callers": [...], "callees": [...]}},
                "classes": {class_name: {"file": "...", "line": 1, "methods": [...]}},
                "symbols": {symbol_name: [(file, line), ...]}
            }
        """
        logger.info("[Indexer] 开始构建代码索引")

        functions = {}
        classes = {}
        symbols = defaultdict(list)  # symbol_name -> [(file, line)]

        for py_file in self.project_root.rglob("*.py"):
            if 'tests' in str(py_file) or '__pycache__' in str(py_file):
                continue
            rel_path = str(py_file.relative_to(self.project_root))

            try:
                with open(py_file, 'r') as f:
                    content = f.read()
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        functions[node.name] = {
                            "file": rel_path,
                            "line": node.lineno,
                            "callers": [],
                            "callees": [],
                        }
                        symbols[node.name].append((rel_path, node.lineno))

                    elif isinstance(node, ast.ClassDef):
                        methods = [
                            item.name
                            for item in node.body
                            if isinstance(item, ast.FunctionDef)
                        ]
                        classes[node.name] = {
                            "file": rel_path,
                            "line": node.lineno,
                            "methods": methods,
                        }
                        symbols[node.name].append((rel_path, node.lineno))

            except (SyntaxError, UnicodeDecodeError):
                continue

        # 构建调用者关系
        for py_file in self.project_root.rglob("*.py"):
            if 'tests' in str(py_file) or '__pycache__' in str(py_file):
                continue
            try:
                with open(py_file, 'r') as f:
                    content = f.read()
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        callee = self._get_call_name(node)
                        if callee in functions:
                            # 找调用者所在的函数
                            caller = self._find_enclosing_function(node, tree)
                            if caller and caller in functions:
                                functions[callee]["callers"].append(caller)
                                functions[caller]["callees"].append(callee)

            except (SyntaxError, UnicodeDecodeError):
                continue

        self.index = {
            "functions": functions,
            "classes": classes,
            "symbols": dict(symbols),
        }

        logger.info(
            f"[Indexer] 索引构建完成: "
            f"{len(functions)} 个函数, {len(classes)} 个类, "
            f"{len(symbols)} 个符号"
        )
        return self.index

    def query_function(self, func_name: str) -> dict | None:
        """查询函数信息"""
        return self.index.get("functions", {}).get(func_name)

    def query_callers(self, func_name: str) -> list[str]:
        """查询函数的调用者"""
        func_info = self.query_function(func_name)
        return func_info.get("callers", []) if func_info else []

    def query_callees(self, func_name: str) -> list[str]:
        """查询函数调用了谁"""
        func_info = self.query_function(func_name)
        return func_info.get("callees", []) if func_info else []

    def _get_call_name(self, node: ast.Call) -> str:
        """提取调用表达式中的函数名"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    def _find_enclosing_function(self, target_node: ast.AST, tree: ast.AST) -> str | None:
        """查找包围目标节点的函数名"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for child in ast.walk(node):
                    if child is target_node:
                        return node.name
        return None
