"""LangGraph StateGraph 编排 - 真正的并行 SubAgent 实现

核心设计：
- 每个 Agent 是独立的 Graph 节点
- 从 skill_engine 扇出（fan-out），LangGraph 自动并行执行 4 个 Agent
- 所有 Agent 完成后，汇聚到 aggregate 节点
- 使用 LangGraph 的 State 合并机制收集各 Agent 的 findings
"""

from typing import Literal

from langgraph.graph import StateGraph, END

from .state import ReviewState


# ========== 节点函数：注释投毒检测 ==========

def poisoning_detect_node(state: ReviewState) -> dict:
    """注释投毒检测节点 - 检测并过滤恶意注释"""
    from src.tools.comment_poisoning_detector import CommentPoisoningDetector

    if not state.poisoning_detection_enabled:
        return {
            "filtered_files": dict(state.target_files),
            "current_stage": "poisoning_checked",
        }

    detector = CommentPoisoningDetector(enabled=True, strict_mode=False)
    filtered_files = {}
    all_alerts = []

    for file_path, content in state.target_files.items():
        alerts = detector.detect_in_file(file_path, content)
        filtered_content, line_alerts = detector.detect_and_filter(file_path, content)

        if alerts:
            all_alerts.extend(alerts)
            for alert in alerts:
                finding_dict = detector.generate_finding_from_alert(alert)
                from .state import Finding
                finding = Finding(**finding_dict)
                state.rule_findings.append(finding)

        filtered_files[file_path] = filtered_content

    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"[PoisoningDetect] 完成，发现 {len(all_alerts)} 处投毒注释，已自动中和"
    )

    return {
        "filtered_files": filtered_files,
        "current_stage": "poisoning_checked",
    }


# ========== 节点函数：上下文收集 ==========

def context_collection_node(state: ReviewState) -> dict:
    """上下文收集节点（升级版：同时读取 OpenSpec 规范）"""
    import logging
    logger = logging.getLogger(__name__)

    from src.context.collector import ContextCollector

    collector = ContextCollector()
    state = collector.collect(state)

    # 读取 OpenSpec 规范文档
    spec_content = ""
    try:
        from src.agents.spec_check_agent import SpecCheckAgent
        spec_agent = SpecCheckAgent()
        root = "."
        if state.target_paths:
            from pathlib import Path
            p = Path(state.target_paths[0])
            root = str(p.parent if p.is_file() else p)
        spec_content = spec_agent.load_spec_content(root)
        if spec_content:
            logger.info(f"[Context] 已加载规范文档 ({len(spec_content)} 字符)")
    except Exception as e:
        logger.warning(f"[Context] 加载规范文档失败: {e}")

    return {
        "target_files": state.target_files,
        "filtered_files": state.filtered_files,
        "related_code": state.related_code,
        "dependency_graph": state.dependency_graph,
        "spec_content": spec_content,
        "current_stage": "context_collected",
    }


# ========== 节点函数：规则引擎 ==========

def rule_engine_node(state: ReviewState) -> dict:
    """规则引擎节点 - 使用过滤后的代码"""
    from src.rules.security import SecurityRuleEngine

    engine = SecurityRuleEngine()
    files_to_scan = state.filtered_files or state.target_files
    findings = engine.scan(files_to_scan)

    return {
        "rule_findings": state.rule_findings + findings,
        "current_stage": "rules_completed",
    }


def style_engine_node(state: ReviewState) -> dict:
    """风格规则引擎节点"""
    from src.rules.style import StyleRuleEngine

    engine = StyleRuleEngine()
    files_to_scan = state.filtered_files or state.target_files
    findings = engine.scan(files_to_scan)

    return {
        "style_findings": findings,
        "current_stage": "style_completed",
    }


# ========== 节点函数：Skill 系统 ==========

def skill_engine_node(state: ReviewState) -> dict:
    """Skill 系统节点 - 执行所有规则型 Skill"""
    from src.skills.skill_executor import SkillExecutor

    executor = SkillExecutor()
    files_to_scan = state.filtered_files or state.target_files

    all_skill_findings = []
    for file_path, content in files_to_scan.items():
        findings = executor.execute_all(
            file_path, content, category_filter=None
        )
        all_skill_findings.extend(findings)

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[SkillEngine] 完成，发现 {len(all_skill_findings)} 个问题")

    return {
        "skill_findings": all_skill_findings,
        "current_stage": "skills_completed",
    }


# ========== 并行 Agent 节点（真正的 LangGraph 并行） ==========
# 每个 Agent 是独立节点，LangGraph 自动并行执行

def _safe_agent_node(
    node_name: str,
    agent_cls,
    state: ReviewState,
    spec_content: str = "",
) -> dict:
    """统一的 Agent 节点执行器（带错误收集、dry_run 传递、Token 预算保护）

    包装了 try/except，失败时记录到 agent_errors 而非静默跳过。
    TokenBudgetExceeded 被单独捕获，标记为可预期的限流（非系统错误）。
    """
    import logging
    import traceback
    logger = logging.getLogger(__name__)

    agent_errors = dict(state.agent_errors)
    logger.info(f"[{node_name}] 开始并行审查{' (dry-run)' if state.dry_run else ''}")

    try:
        agent = agent_cls(dry_run=state.dry_run)
        if spec_content and hasattr(agent, "spec_content"):
            agent.spec_content = spec_content

        findings = agent.review(state)

        logger.info(f"[{node_name}] 完成，发现 {len(findings)} 个问题")
        return {
            f"agent_{node_name[-1].lower()}_findings": findings,
            "agent_errors": agent_errors,
        }
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        error_detail = f"[{node_name}] {error_msg}\n{traceback.format_exc()}"

        # Token 预算超限：降级为 warning（预期行为，非系统错误）
        if "TokenBudgetExceeded" in type(e).__name__:
            logger.warning(f"[{node_name}] Token 预算不足，跳过审查: {e}")
        else:
            logger.error(error_detail)

        # 收集错误
        agent_errors[node_name] = agent_errors.get(node_name, []) + [error_msg]

        return {
            f"agent_{node_name[-1].lower()}_findings": [],
            "agent_errors": agent_errors,
        }


def agent_a_node(state: ReviewState) -> dict:
    """Agent A 节点 - Bug + 性能分析（独立并行执行）"""
    from src.agents.bug_perf_agent import BugPerfAgent
    return _safe_agent_node("agent_a", BugPerfAgent, state)


def agent_b_node(state: ReviewState) -> dict:
    """Agent B 节点 - 风格检查 + 验收（独立并行执行）"""
    from src.agents.style_accept_agent import StyleAcceptAgent
    return _safe_agent_node("agent_b", StyleAcceptAgent, state)


def agent_c_node(state: ReviewState) -> dict:
    """Agent C 节点 - 架构审查（独立并行执行）"""
    from src.agents.architect_agent import ArchitectAgent
    return _safe_agent_node("agent_c", ArchitectAgent, state)


def agent_d_node(state: ReviewState) -> dict:
    """Agent D 节点 - 规范驱动审查（独立并行执行）"""
    from src.agents.spec_check_agent import SpecCheckAgent
    return _safe_agent_node("agent_d", SpecCheckAgent, state, spec_content=state.spec_content)


# ========== 节点函数：汇总仲裁 ==========

def aggregate_node(state: ReviewState) -> dict:
    """汇总仲裁节点（升级版：包含 Agent C/D 的发现）"""
    from src.review.aggregator import Aggregator
    aggregator = Aggregator()
    state = aggregator.aggregate(state)

    return {
        "merged_findings": state.merged_findings,
        "todos": state.todos,
        "pending_questions": state.pending_questions,
        "current_stage": "aggregated",
    }


def human_interrupt_node(state: ReviewState) -> dict:
    """人机回环节点"""
    from src.review.aggregator import Aggregator
    aggregator = Aggregator()
    state = aggregator.resolve_interrupts(state)

    return {
        "user_decisions": state.user_decisions,
        "current_stage": "human_interrupted",
    }


def generate_output_node(state: ReviewState) -> dict:
    """输出生成节点"""
    from src.output.reporter import Reporter
    reporter = Reporter()
    state = reporter.generate(state)

    return {"current_stage": "completed"}


# ========== 条件路由 ==========

def route_after_aggregate(state: ReviewState) -> str:
    """条件路由：根据是否有待确认的问题决定下一步"""
    if state.pending_questions:
        return "human_interrupt"
    return "generate_output"


# ========== 构建真正的并行 DAG ==========

def build_review_graph() -> StateGraph:
    """构建审查流程的 StateGraph（真正的 LangGraph 并行）

    并行设计：
    - poisoning_detect → context_collection → rule_engine → style_engine
      → skill_engine
    - skill_engine 扇出到 4 个独立 Agent 节点（LangGraph 自动并行）
    - 4 个 Agent 全部完成后，汇聚到 aggregate
    - aggregate → (human_interrupt)? → generate_output → END
    """
    graph = StateGraph(ReviewState)

    # ---------- 注册所有节点 ----------
    graph.add_node("poisoning_detect", poisoning_detect_node)
    graph.add_node("context_collection", context_collection_node)
    graph.add_node("rule_engine", rule_engine_node)
    graph.add_node("style_engine", style_engine_node)
    graph.add_node("skill_engine", skill_engine_node)

    # 4 个 Agent 节点（独立注册，LangGraph 会自动并行）
    graph.add_node("agent_a", agent_a_node)
    graph.add_node("agent_b", agent_b_node)
    graph.add_node("agent_c", agent_c_node)
    graph.add_node("agent_d", agent_d_node)

    graph.add_node("aggregate", aggregate_node)
    graph.add_node("human_interrupt", human_interrupt_node)
    graph.add_node("generate_output", generate_output_node)

    # ---------- 串行边（前置阶段） ----------
    graph.set_entry_point("poisoning_detect")
    graph.add_edge("poisoning_detect", "context_collection")
    graph.add_edge("context_collection", "rule_engine")
    graph.add_edge("rule_engine", "style_engine")
    graph.add_edge("style_engine", "skill_engine")

    # ---------- 并行扇出（核心！） ----------
    # skill_engine 完成后，同时触发 4 个 Agent（LangGraph 自动并行）
    graph.add_edge("skill_engine", "agent_a")
    graph.add_edge("skill_engine", "agent_b")
    graph.add_edge("skill_engine", "agent_c")
    graph.add_edge("skill_engine", "agent_d")

    # ---------- 并行汇聚 ----------
    # 4 个 Agent 全部完成后，进入 aggregate
    # LangGraph 会自动等待所有前置节点完成
    graph.add_edge("agent_a", "aggregate")
    graph.add_edge("agent_b", "aggregate")
    graph.add_edge("agent_c", "aggregate")
    graph.add_edge("agent_d", "aggregate")

    # ---------- 后置阶段 ----------
    # aggregate 条件路由：有冲突 → human_interrupt；否则直接生成输出
    graph.add_conditional_edges(
        "aggregate",
        route_after_aggregate,
        {
            "human_interrupt": "human_interrupt",
            "generate_output": "generate_output",
        }
    )

    # human_interrupt 完成后生成报告
    graph.add_edge("human_interrupt", "generate_output")
    graph.add_edge("generate_output", END)

    return graph


def create_review_workflow():
    """创建可执行的并行工作流（带记忆）"""
    from langgraph.checkpoint.memory import MemorySaver

    memory = MemorySaver()
    graph = build_review_graph()
    return graph.compile(checkpointer=memory)


def visualize_graph(output_path: str = "review_graph.png") -> None:
    """可视化 DAG 结构（需要 graphviz）"""
    try:
        graph = build_review_graph()
        compiled = graph.compile()
        with open(output_path, "wb") as f:
            f.write(compiled.get_graph().draw_png())
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Graph] DAG 可视化已保存到 {output_path}")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"[Graph] 可视化失败（可能需要安装 graphviz）: {e}")
