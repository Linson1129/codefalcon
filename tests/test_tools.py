"""AST分析工具测试"""

import pytest
from src.tools.ast_analyzer import ASTAnalyzer


class TestASTAnalyzer:
    """AST分析器测试"""

    def setup_method(self):
        self.analyzer = ASTAnalyzer()

    def test_extract_function_definitions(self):
        """提取函数定义"""
        code = """
def hello():
    pass

def greet(name: str) -> str:
    return f"Hello, {name}"
"""
        result = self.analyzer.extract_definitions(code)
        assert len(result["functions"]) == 2
        assert result["functions"][0]["name"] == "hello"
        assert result["functions"][1]["name"] == "greet"

    def test_extract_class_definitions(self):
        """提取类定义"""
        code = """
class User:
    def __init__(self):
        pass
    def save(self):
        pass
"""
        result = self.analyzer.extract_definitions(code)
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "User"
        assert "save" in result["classes"][0]["methods"]

    def test_build_call_graph(self):
        """构建调用关系图"""
        code = """
def helper():
    pass

def process():
    helper()
    helper()

def main():
    process()
"""
        call_graph = self.analyzer.build_call_graph(code)
        assert "process" in call_graph
        assert "helper" in call_graph["process"]
        assert "main" in call_graph

    def test_empty_code(self):
        """空代码"""
        result = self.analyzer.extract_definitions("")
        assert result["functions"] == []
        assert result["classes"] == []

    def test_syntax_error_handling(self):
        """语法错误处理"""
        code = "def broken("
        result = self.analyzer.extract_definitions(code)
        # 应该返回空结果而不是抛异常
        assert isinstance(result, dict)
