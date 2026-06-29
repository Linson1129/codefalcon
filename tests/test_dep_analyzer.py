"""依赖分析器单元测试"""

from src.tools.dep_analyzer import DependencyAnalyzer


class TestModuleToPath:
    """模块名 → 文件路径转换"""

    def test_dotted_module_to_path(self):
        result = DependencyAnalyzer._module_to_path("src.utils.config")
        assert result == "src/utils/config.py"

    def test_single_module_to_path(self):
        result = DependencyAnalyzer._module_to_path("os")
        assert result == "os.py"

    def test_already_path_format(self):
        """已是 .py 路径格式，保持不变"""
        result = DependencyAnalyzer._module_to_path("src/utils/config.py")
        assert result == "src/utils/config.py"

    def test_nested_package(self):
        result = DependencyAnalyzer._module_to_path("a.b.c.d.e")
        assert result == "a/b/c/d/e.py"


class TestDependencyAnalyzer:
    """依赖分析器集成测试"""

    def test_analyze_project_returns_correct_structure(self):
        analyzer = DependencyAnalyzer(project_root=".")
        result = analyzer.analyze_project()
        assert "import_graph" in result
        assert "function_map" in result
        assert "dependents" in result
        assert isinstance(result["import_graph"], dict)
        assert isinstance(result["dependents"], dict)

    def test_import_graph_keys_are_file_paths(self):
        """import_graph 的 key 和 value 都应是文件路径（.py 结尾）"""
        analyzer = DependencyAnalyzer(project_root=".")
        result = analyzer.analyze_project()
        import_graph = result["import_graph"]
        for file_path, imports in import_graph.items():
            assert file_path.endswith(".py"), f"Key '{file_path}' 应以 .py 结尾"
            for imp in imports:
                assert imp.endswith(".py"), f"Import '{imp}' 应以 .py 结尾"

    def test_excludes_test_files(self):
        """排除 tests/ 目录"""
        analyzer = DependencyAnalyzer(project_root=".")
        result = analyzer.analyze_project()
        for path in result["import_graph"]:
            assert "tests" not in path, f"tests/ 目录应被排除: {path}"

    def test_self_files_present(self):
        """项目自身的源文件应出现在图中"""
        analyzer = DependencyAnalyzer(project_root=".")
        result = analyzer.analyze_project()
        # 至少应该有自己的主要模块
        all_files = list(result["import_graph"].keys())
        assert len(all_files) > 0, "应该有至少一个源文件"

    def test_get_impacted_files(self):
        """get_impacted_files 返回受影响的文件列表"""
        analyzer = DependencyAnalyzer(project_root=".")
        # 查找一个有 dependents 的文件
        result = analyzer.analyze_project()
        dependents = result["dependents"]
        if dependents:
            # 取第一个有依赖者的文件
            target = list(dependents.keys())[0]
            impacted = analyzer.get_impacted_files(target)
            assert isinstance(impacted, list)
