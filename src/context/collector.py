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
    """

    def collect(self, state: ReviewState) -> ReviewState:
        """收集审查所需的所有上下文"""
        logger.info(f"[ContextCollector] 收集 {len(state.target_paths)} 个路径的上下文")

        # 读取目标文件
        for path_str in state.target_paths:
            path = Path(path_str).resolve()
            if path.is_file():
                try:
                    with open(path, 'r') as f:
                        state.target_files[str(path)] = f.read()
                except Exception as e:
                    logger.error(f"读取文件失败 {path}: {e}")
            elif path.is_dir():
                for py_file in path.rglob("*.py"):
                    try:
                        with open(py_file, 'r') as f:
                            state.target_files[str(py_file)] = f.read()
                    except Exception as e:
                        logger.error(f"读取文件失败 {py_file}: {e}")

        logger.info(f"[ContextCollector] 读取了 {len(state.target_files)} 个文件")

        # 收集相关代码段
        state.related_code = self._collect_related_code(state)

        # 分析依赖关系
        dep_analyzer = DependencyAnalyzer()
        state.dependency_graph = dep_analyzer.analyze_project()
        for file_path in state.target_files:
            impacted = dep_analyzer.get_impacted_files(file_path)
            if impacted:
                logger.info(f"[ContextCollector] {file_path} 可能影响: {impacted}")

        return state

    def _collect_related_code(self, state: ReviewState) -> dict[str, list[str]]:
        """收集与目标文件相关的代码段"""
        related = {}
        ast_analyzer = ASTAnalyzer()

        for file_path, content in state.target_files.items():
            related[file_path] = []

            # 提取函数定义和调用关系
            defs = ast_analyzer.extract_definitions(content)
            call_graph = ast_analyzer.build_call_graph(content)

            # 记录调用关系作为上下文
            for func_name, callees in call_graph.items():
                for callee in callees:
                    related[file_path].append(f"函数 '{func_name}' 调用了 '{callee}'")

        return related
