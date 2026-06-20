"""LangGraph StateGraph 编排 - 审查流程的完整DAG定义"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import ReviewState


def build_review_graph() -> StateGraph:
    """构建审查流程的 StateGraph"""
    graph = StateGraph(ReviewState)

    # 注册节点
    graph.add_node("context_collection", context_collection_node)
    graph.add_node("rule_engine", rule_engine_node)
    graph.add_node("style_engine", style_engine_node)
    graph.add_node("agents", agents_node)  # 内部并行跑 Agent A + B
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("human_interrupt", human_interrupt_node)
    graph.add_node("generate_output", generate_output_node)

    # 设置入口
    graph.set_entry_point("context_collection")

    # 定义边（0成本规则引擎串行，Agent A/B 内部并行）
    graph.add_edge("context_collection", "rule_engine")
    graph.add_edge("rule_engine", "style_engine")
    graph.add_edge("style_engine", "agents")
    graph.add_edge("agents", "aggregate")

    # 聚合层条件路由
    graph.add_conditional_edges(
        "aggregate",
        route_after_aggregate,
        {
            "human_interrupt": "human_interrupt",
            "generate_output": "generate_output",
        }
    )

    graph.add_edge("human_interrupt", "generate_output")
    graph.add_edge("generate_output", END)

    return graph


def context_collection_node(state: ReviewState) -> ReviewState:
    """上下文收集节点"""
    from src.context.collector import ContextCollector
    collector = ContextCollector()
    state = collector.collect(state)
    state.current_stage = "context_collected"
    return state


def rule_engine_node(state: ReviewState) -> ReviewState:
    """规则引擎节点 - 确定性安全检查"""
    from src.rules.security import SecurityRuleEngine
    engine = SecurityRuleEngine()
    state.rule_findings = engine.scan(state.target_files)
    state.current_stage = "rules_completed"
    return state


def style_engine_node(state: ReviewState) -> ReviewState:
    """风格规则引擎节点 - 确定性风格检查"""
    from src.rules.style import StyleRuleEngine
    engine = StyleRuleEngine()
    state.style_findings = engine.scan(state.target_files)
    state.current_stage = "style_completed"
    return state


def agents_node(state: ReviewState) -> ReviewState:
    """Agent 节点 - 内部并行跑 Agent A 和 Agent B"""
    from src.agents.bug_perf_agent import BugPerfAgent
    from src.agents.style_accept_agent import StyleAcceptAgent

    def run_agent_a():
        agent = BugPerfAgent()
        return agent.review(state)

    def run_agent_b():
        agent = StyleAcceptAgent()
        return agent.review(state)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(run_agent_a)
        future_b = executor.submit(run_agent_b)

        # 每个 Agent 最多等 5 分钟
        state.agent_a_findings = future_a.result(timeout=300)
        state.agent_b_findings = future_b.result(timeout=300)

    state.current_stage = "agents_completed"
    return state


def aggregate_node(state: ReviewState) -> ReviewState:
    """汇总仲裁节点"""
    from src.review.aggregator import Aggregator
    aggregator = Aggregator()
    state = aggregator.aggregate(state)
    state.current_stage = "aggregated"
    return state


def human_interrupt_node(state: ReviewState) -> ReviewState:
    """人机回环节点"""
    from src.review.aggregator import Aggregator
    aggregator = Aggregator()
    state = aggregator.resolve_interrupts(state)
    state.current_stage = "human_interrupted"
    return state


def generate_output_node(state: ReviewState) -> ReviewState:
    """输出生成节点"""
    from src.output.reporter import Reporter
    reporter = Reporter()
    state = reporter.generate(state)
    state.current_stage = "completed"
    return state


def route_after_aggregate(state: ReviewState) -> Literal["human_interrupt", "generate_output"]:
    """条件路由：根据是否有待确认的问题决定下一步"""
    if state.pending_questions:
        return "human_interrupt"
    return "generate_output"


def create_review_workflow():
    """创建可执行的工作流（带记忆）"""
    memory = MemorySaver()
    graph = build_review_graph()
    return graph.compile(checkpointer=memory)
