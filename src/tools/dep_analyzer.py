"""依赖分析工具 - 跨文件依赖关系分析"""

import ast
import logging
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


class DependencyAnalyzer:
    """跨文件依赖关系分析器

    能力：
    - 分析项目文件间的import依赖
    - 分析函数/类的被调用关系
    - 检测修改的潜在影响范围
    """

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self._file_imports: dict[str, list[str]] = {}
        self._function_defs: dict[str, str] = {}  # func_name -> file_path

    def analyze_project(self) -> dict:
        """分析整个项目的依赖关系

        Returns:
            {
                "import_graph": {file: [imported_files]},
                "function_map": {func_name: file_path},
                "dependents": {file: [files_that_depend_on_it]},
            }
        """
        self._scan_all_files()

        dependents = defaultdict(list)
        for file_path, imports in self._file_imports.items():
            for imp in imports:
                if imp in self._file_imports:
                    dependents[imp].append(file_path)

        return {
            "import_graph": dict(self._file_imports),
            "function_map": dict(self._function_defs),
            "dependents": dict(dependents),
        }

    def get_impacted_files(self, changed_file: str) -> list[str]:
        """获取修改某个文件可能影响的其他文件"""
        dep_info = self.analyze_project()
        return dep_info.get("dependents", {}).get(changed_file, [])

    def _scan_all_files(self):
        """扫描项目中的所有Python文件"""
        self._file_imports = {}
        self._function_defs = {}

        for py_file in self.project_root.rglob("*.py"):
            if 'tests' in str(py_file) or '__pycache__' in str(py_file):
                continue
            rel_path = str(py_file.relative_to(self.project_root))
            try:
                with open(py_file, 'r') as f:
                    content = f.read()
                tree = ast.parse(content)

                # 提取import依赖
                imports = self._extract_imports(tree, rel_path)
                self._file_imports[rel_path] = imports

                # 提取函数定义
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        key = f"{rel_path}:{node.name}"
                        self._function_defs[key] = rel_path

            except (SyntaxError, UnicodeDecodeError):
                continue

    def _extract_imports(self, tree: ast.AST, current_file: str) -> list[str]:
        """提取文件中的import依赖（返回文件路径格式）"""
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(self._module_to_path(alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(self._module_to_path(node.module))

        return imports

    @staticmethod
    def _module_to_path(module_name: str) -> str:
        """将模块名转换为相对文件路径

        例如: src.utils.config → src/utils/config.py
               os → os.py
        """
        # 如果已经是 .py 路径格式，直接返回
        if module_name.endswith(".py"):
            return module_name
        return module_name.replace(".", "/") + ".py"
