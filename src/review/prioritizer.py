"""问题优先级排序器 - 独立的优先级计算逻辑"""

from typing import Any, Union

from src.orchestrator.state import Finding


def _f(finding, field: str, default: Any = None) -> Any:
    """兼容 dict 和 Finding 对象的字段访问"""
    if isinstance(finding, dict):
        return finding.get(field, default)
    return getattr(finding, field, default)


class Prioritizer:
    """问题优先级计算

    排序规则：
    1. 类别优先：security > bug > performance > style
    2. 严重程度：error > warning > info
    3. 同一优先级按行号排序
    """

    CATEGORY_WEIGHT = {
        "security": 100,
        "bug": 80,
        "performance": 60,
        "style": 40,
    }

    SEVERITY_WEIGHT = {
        "error": 30,
        "warning": 20,
        "info": 10,
    }

    def sort(self, findings):
        """排序（兼容 list[Finding] 和 list[dict]）"""
        return sorted(
            findings,
            key=lambda f: (
                self.CATEGORY_WEIGHT.get(_f(f, "category", ""), 0)
                + self.SEVERITY_WEIGHT.get(_f(f, "severity", ""), 0)
            ),
            reverse=True,
        )

    def get_summary(self, findings) -> dict:
        """生成问题摘要统计（兼容 list[Finding] 和 list[dict]）"""
        summary = {
            "total": len(findings),
            "by_severity": {"error": 0, "warning": 0, "info": 0},
            "by_category": {"security": 0, "bug": 0, "performance": 0, "style": 0},
        }
        for f in findings:
            sev = _f(f, "severity", "")
            cat = _f(f, "category", "")
            if sev in summary["by_severity"]:
                summary["by_severity"][sev] += 1
            if cat in summary["by_category"]:
                summary["by_category"][cat] += 1
        return summary
