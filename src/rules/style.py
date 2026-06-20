"""基础风格规则引擎"""

import re
import logging

from src.orchestrator.state import Finding

logger = logging.getLogger(__name__)


class StyleRuleEngine:
    """基础代码风格规则检查（0 Token成本）

    检测项：
    - 行长度
    - 空行规范
    - 尾随空格
    """

    MAX_LINE_LENGTH = 120

    def scan(self, target_files: dict[str, str]) -> list[Finding]:
        """扫描所有目标文件的基础风格问题"""
        all_findings = []

        for file_path, content in target_files.items():
            findings = []
            findings.extend(self._check_line_length(file_path, content))
            findings.extend(self._check_trailing_whitespace(file_path, content))
            all_findings.extend(findings)

        logger.info(f"[风格规则引擎] 扫描完成，发现 {len(all_findings)} 个问题")
        return all_findings

    def _check_line_length(self, file_path: str, content: str) -> list[Finding]:
        """检测行长度"""
        findings = []
        for i, line in enumerate(content.split('\n'), 1):
            if len(line) > self.MAX_LINE_LENGTH:
                findings.append(Finding(
                    severity="info",
                    category="style",
                    file_path=file_path,
                    line=i,
                    message=f"行长度 {len(line)} 超过 {self.MAX_LINE_LENGTH} 字符限制",
                    suggestion="建议拆分为多行或缩短变量名",
                    agent_source="rules",
                ))
        return findings

    def _check_trailing_whitespace(self, file_path: str, content: str) -> list[Finding]:
        """检测尾随空格"""
        findings = []
        for i, line in enumerate(content.split('\n'), 1):
            if line.endswith(' ') or line.endswith('\t'):
                findings.append(Finding(
                    severity="info",
                    category="style",
                    file_path=file_path,
                    line=i,
                    message="行尾有多余空格",
                    suggestion="删除行尾空格",
                    agent_source="rules",
                ))
        return findings
