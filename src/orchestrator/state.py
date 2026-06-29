"""审查状态定义 - LangGraph StateGraph 的状态 Schema"""

from dataclasses import dataclass, field
from typing import Any, Annotated


def _merge_dicts(a: dict, b: dict) -> dict:
    """LangGraph reducer：并行节点写入同一 dict key 时合并"""
    result = dict(a)
    for k, v in (b or {}).items():
        if k in result:
            result[k] = result[k] + v
        else:
            result[k] = v
    return result


@dataclass
class Finding:
    """单条审查发现"""
    severity: str          # "error" | "warning" | "info"
    category: str          # "security" | "bug" | "performance" | "style" | "architecture" | "spec"
    file_path: str
    line: int
    message: str
    suggestion: str = ""
    agent_source: str = ""  # "rules" | "agent_a" | "agent_b" | "agent_c" | "agent_d" | "skill:xxx" | "poisoning_detector"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "file_path": self.file_path,
            "line": self.line,
            "message": self.message,
            "suggestion": self.suggestion,
            "agent_source": self.agent_source,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(**d)


@dataclass
class ReviewState:
    """审查流程的完整状态"""
    # 输入
    target_paths: list[str] = field(default_factory=list)
    target_files: dict[str, str] = field(default_factory=dict)
    filtered_files: dict[str, str] = field(default_factory=dict)

    # 上下文
    related_code: dict[str, list[str]] = field(default_factory=dict)
    dependency_graph: dict[str, Any] = field(default_factory=dict)
    spec_content: str = ""

    # 审查结果 - 规则引擎
    rule_findings: list[Finding] = field(default_factory=list)
    style_findings: list[Finding] = field(default_factory=list)
    skill_findings: list[Finding] = field(default_factory=list)

    # 审查结果 - Agent LLM
    agent_a_findings: list[Finding] = field(default_factory=list)
    agent_b_findings: list[Finding] = field(default_factory=list)
    agent_c_findings: list[Finding] = field(default_factory=list)
    agent_d_findings: list[Finding] = field(default_factory=list)

    # 聚合结果
    merged_findings: list[Finding] = field(default_factory=list)
    todos: list[dict[str, Any]] = field(default_factory=list)

    # 人机回环
    pending_questions: list[dict[str, Any]] = field(default_factory=list)
    user_decisions: dict[str, str] = field(default_factory=dict)

    # 流程控制
    current_stage: str = "init"
    poisoning_detection_enabled: bool = True

    # P1: 增量 Diff 模式
    diff_mode: bool = False
    changed_files: list[str] = field(default_factory=list)
    base_branch: str = "main"

    # P3: Dry-Run 模式（不调真实 LLM，用 Mock 数据跑完整 DAG）
    dry_run: bool = False

    # P4: Agent 错误弹性 — 收集各 Agent 的失败信息（Annotated + reducer 支持并行写入）
    agent_errors: Annotated[dict[str, list[str]], _merge_dicts] = field(default_factory=dict)
