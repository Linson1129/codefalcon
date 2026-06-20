"""汇总仲裁器 - 去重合并、优先级排序、冲突检测"""

import logging
import os
from collections import defaultdict
from pathlib import Path

from src.orchestrator.state import Finding, ReviewState

logger = logging.getLogger(__name__)


class Aggregator:
    """审查结果汇总器

    职责：
    - 合并规则引擎、Agent A、Agent B 的发现
    - 按 file:line 去重
    - 按严重程度和类别排序
    - 检测Agent间意见冲突
    - 生成待确认问题列表
    """

    SEVERITY_PRIORITY = {"error": 3, "warning": 2, "info": 1}
    CATEGORY_PRIORITY = {"security": 5, "bug": 4, "performance": 3, "style": 2}

    def aggregate(self, state: ReviewState) -> ReviewState:
        """汇总所有审查发现"""
        logger.info("[Aggregator] 开始汇总审查结果")

        all_findings = (
            state.rule_findings + state.style_findings
            + state.agent_a_findings + state.agent_b_findings
        )
        logger.info(
            f"[Aggregator] 原始发现: 安全规则={len(state.rule_findings)}, "
            f"风格规则={len(state.style_findings)}, "
            f"AgentA={len(state.agent_a_findings)}, AgentB={len(state.agent_b_findings)}"
        )

        # 去重
        state.merged_findings = self._deduplicate(all_findings)
        logger.info(f"[Aggregator] 去重后: {len(state.merged_findings)} 个问题")

        # 优先级排序
        state.merged_findings = self._prioritize(state.merged_findings)

        # 检测冲突
        conflicts = self._detect_conflicts(all_findings)
        state.pending_questions = [
            {
                "type": "conflict",
                "file": c["file"],
                "line": c["line"],
                "question": f"多个Agent对 {c['file']}:{c['line']} 有不同意见: {c['opinions']}",
                "options": c["suggestions"],
            }
            for c in conflicts
        ]

        # 生成待办事项
        state.todos = self._generate_todos(state.merged_findings)

        return state

    def resolve_interrupts(self, state: ReviewState) -> ReviewState:
        """处理人机回环的交互结果"""
        for question in state.pending_questions:
            q_id = f"{question['file']}:{question['line']}"
            if q_id in state.user_decisions:
                question["decision"] = state.user_decisions[q_id]
                logger.info(f"[Aggregator] 用户决策: {q_id} -> {question['decision']}")
        state.pending_questions = []
        return state

    def _deduplicate(self, findings: list[Finding]) -> list[Finding]:
        """按 标准化路径:行号:类别 去重，保留严重程度最高的"""
        grouped = defaultdict(list)
        for f in findings:
            key = f"{self._normpath(f.file_path)}:{f.line}:{f.category}"
            grouped[key].append(f)

        result = []
        for key, group in grouped.items():
            # 保留同一位置+类别中严重程度最高的
            best = max(group, key=lambda x: self.SEVERITY_PRIORITY.get(x.severity, 0))
            if len(group) > 1:
                sources = {s for s in (f.agent_source for f in group) if s}
                if sources:
                    best.message += f" (由 {', '.join(sources)} 共同确认)"
            result.append(best)

        return result

    def _normpath(self, file_path: str) -> str:
        """标准化路径为绝对路径，消除相对/绝对路径差异"""
        return os.path.abspath(file_path)

    def _prioritize(self, findings: list[Finding]) -> list[Finding]:
        """按严重程度和类别排序"""
        return sorted(
            findings,
            key=lambda f: (
                self.CATEGORY_PRIORITY.get(f.category, 0),
                self.SEVERITY_PRIORITY.get(f.severity, 0),
            ),
            reverse=True,
        )

    def _detect_conflicts(self, findings: list[Finding]) -> list[dict]:
        """检测同一位置不同Agent有不同意见的情况"""
        grouped = defaultdict(list)
        for f in findings:
            if f.agent_source == "rules":
                continue  # 规则引擎的结果是确定的，不参与冲突检测
            key = f"{self._normpath(f.file_path)}:{f.line}"
            grouped[key].append(f)

        conflicts = []
        for key, group in grouped.items():
            # 只有两个以上非 rules 来源才可能冲突
            if len(group) < 2:
                continue
            severities = set(f.severity for f in group)
            categories = set(f.category for f in group)
            if len(severities) > 1 or len(categories) > 1:
                conflicts.append({
                    "file": group[0].file_path,
                    "line": group[0].line,
                    "opinions": [f"{f.agent_source}: {f.severity}/{f.category} - {f.message[:60]}" for f in group],
                    "suggestions": [f.suggestion for f in group if f.suggestion],
                })

        return conflicts

    def _generate_todos(self, findings: list[Finding]) -> list[dict]:
        """生成待办事项（ID由TodoManager统一分配）"""
        return [
            {
                "file": f.file_path,
                "line": f.line,
                "severity": f.severity,
                "category": f.category,
                "message": f.message,
                "suggestion": f.suggestion,
            }
            for f in findings
        ]
