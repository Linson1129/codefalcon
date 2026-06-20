"""审查状态定义 - LangGraph StateGraph 的状态 Schema"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Finding:
    """单条审查发现"""
    severity: str          # "error" | "warning" | "info"
    category: str          # "security" | "bug" | "performance" | "style"
    file_path: str
    line: int
    message: str
    suggestion: str = ""
    agent_source: str = ""  # "rules" | "agent_a" | "agent_b"


@dataclass
class ReviewState:
    """审查流程的完整状态"""
    # 输入
    target_paths: list[str] = field(default_factory=list)
    target_files: dict[str, str] = field(default_factory=dict)  # filepath -> content

    # 上下文
    diff_context: dict[str, Any] = field(default_factory=dict)
    related_code: dict[str, list[str]] = field(default_factory=dict)
    dependency_graph: dict[str, Any] = field(default_factory=dict)  # 依赖分析结果

    # 审查结果
    rule_findings: list[Finding] = field(default_factory=list)
    style_findings: list[Finding] = field(default_factory=list)
    agent_a_findings: list[Finding] = field(default_factory=list)
    agent_b_findings: list[Finding] = field(default_factory=list)

    # 聚合结果
    merged_findings: list[Finding] = field(default_factory=list)
    todos: list[dict[str, Any]] = field(default_factory=list)

    # 人机回环
    pending_questions: list[dict[str, Any]] = field(default_factory=list)
    user_decisions: dict[str, str] = field(default_factory=dict)

    # 成本追踪
    token_usage: dict[str, int] = field(default_factory=dict)

    # 流程控制
    current_stage: str = "init"
    error: Optional[str] = None
