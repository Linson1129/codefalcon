"""AST分析工具 - 解析Python代码结构"""

import ast
import logging

logger = logging.getLogger(__name__)


class ASTAnalyzer:
    """Python AST分析器

    提供：
    - 函数/类定义提取
    - 函数调用关系图构建
    - 变量作用域分析
    - import依赖分析
    """

    def extract_definitions(self, source_code: str) -> dict:
        """提取代码中的函数和类定义

        Returns:
            {
                "functions": [{"name": "...", "line": 1, "args": [...], "decorators": [...]}],
                "classes": [{"name": "...", "line": 1, "methods": [...]}],
                "imports": [{"module": "...", "names": [...], "line": 1}],
            }
        """
        result = {
            "functions": [],
            "classes": [],
            "imports": [],
        }

        try:
            tree = ast.parse(source_code)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    result["functions"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": [arg.arg for arg in node.args.args],
                        "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
                    })
                elif isinstance(node, ast.ClassDef):
                    methods = []
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            methods.append(item.name)
                    result["classes"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": methods,
                    })
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        result["imports"].append({
                            "module": alias.name,
                            "alias": alias.asname,
                            "line": node.lineno,
                        })
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        result["imports"].append({
                            "module": f"{module}.{alias.name}",
                            "alias": alias.asname,
                            "line": node.lineno,
                        })

        except SyntaxError as e:
            logger.warning(f"AST解析失败: {e}")

        return result

    def build_call_graph(self, source_code: str) -> dict[str, list[str]]:
        """构建函数调用关系图

        Returns:
            {函数名: [被调用的函数名列表]}
        """
        call_graph = {}
        try:
            tree = ast.parse(source_code)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_name = node.name
                    callees = []
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            callee_name = self._get_call_name(child)
                            if callee_name:
                                callees.append(callee_name)
                    call_graph[func_name] = list(set(callees))

        except SyntaxError as e:
            logger.warning(f"AST解析失败: {e}")

        return call_graph

    def _get_call_name(self, node: ast.Call) -> str:
        """提取调用表达式中的函数名"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    def _get_decorator_name(self, node) -> str:
        """提取装饰器名称"""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return "unknown"
