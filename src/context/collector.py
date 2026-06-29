"""上下文收集器 - 收集代码审查所需的上下文信息"""

import logging
from pathlib import Path

from src.orchestrator.state import ReviewState
from src.tools.ast_analyzer import ASTAnalyzer
from src.tools.dep_analyzer import DependencyAnalyzer

logger = logging.getLogger(__name__)


class ContextCollector:
    """审查上下文收集器

    负责：
    - 读取目标文件内容
    - 收集相关代码段
    - 构建调用图和依赖关系

    设计原则：所有 collect_* 方法返回新数据而非就地修改 state，
    由调用方（DAG 节点）负责赋值，符合 LangGraph Reducer 函数式范式。
    """

    def collect(self, state: ReviewState) -> ReviewState:
        """收集审查所需的所有上下文（综合入口）

        注意：当前版本保留原地修改方式以保证向后兼容。
        新代码应优先使用下面的独立方法。
        """
        logger.info(f"[ContextCollector] 收集 {len(state.target_paths)} 个路径的上下文")

        # 读取目标文件
        target_files = self.collect_files(state.target_paths)

        # 收集相关代码段
        related_code = self.collect_related_code(target_files)

        # 分析依赖关系
        dependency_graph = self.collect_dependencies(target_files)

        # 写回 state
        state.target_files = target_files
        state.related_code = related_code
        state.dependency_graph = dependency_graph

        logger.info(f"[ContextCollector] 读取了 {len(target_files)} 个文件")
        return state

    # ---- 独立的纯函数收集方法 ----

    def collect_files(self, target_paths: list[str]) -> dict[str, str]:
        """读取目标文件内容（纯函数，返回新 dict）"""
        files = {}
        for path_str in target_paths:
            path = Path(path_str).resolve()
            if path.is_file():
                try:
                    with open(path, 'r') as f:
                        files[str(path)] = f.read()
                except Exception as e:
                    logger.error(f"读取文件失败 {path}: {e}")
            elif path.is_dir():
                for py_file in path.rglob("*.py"):
                    try:
                        with open(py_file, 'r') as f:
                            files[str(py_file)] = f.read()
                    except Exception as e:
                        logger.error(f"读取文件失败 {py_file}: {e}")
        return files

    def collect_related_code(
        self, target_files: dict[str, str]
    ) -> dict[str, list[str]]:
        """收集与目标文件相关的代码段（纯函数）"""
        related = {}
        ast_analyzer = ASTAnalyzer()

        for file_path, content in target_files.items():
            related[file_path] = []

            # 提取调用关系作为上下文
            call_graph = ast_analyzer.build_call_graph(content)
            for func_name, callees in call_graph.items():
                for callee in callees:
                    related[file_path].append(f"函数 '{func_name}' 调用了 '{callee}'")

        return related

    def collect_dependencies(
        self, target_files: dict[str, str]
    ) -> dict:
        """分析依赖关系（纯函数）"""
        dep_analyzer = DependencyAnalyzer()
        dependency_graph = dep_analyzer.analyze_project()

        for file_path in target_files:
            impacted = dep_analyzer.get_impacted_files(file_path)
            if impacted:
                logger.info(f"[ContextCollector] {file_path} 可能影响: {impacted}")

        return dependency_graph
