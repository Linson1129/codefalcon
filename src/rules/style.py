"""基础风格规则引擎"""

import re
import logging

from src.orchestrator.state import Finding

logger = logging.getLogger(__name__)


class StyleRuleEngine:
    """基础代码风格规则检查（0 Token成本）

    检测项：
    - 行长度 (STY-001)
    - 尾随空格 (STY-002)
    - 文件末尾缺少换行符 (STY-003)
    - 连续多余空行 (STY-004)
    - 缩进混用 Tab 和空格 (STY-005)
    """

    MAX_LINE_LENGTH = 120
    MAX_CONSECUTIVE_BLANK_LINES = 3

    def scan(self, target_files: dict[str, str]) -> list[Finding]:
        """扫描所有目标文件的基础风格问题"""
        all_findings = []

        for file_path, content in target_files.items():
            findings = []
            findings.extend(self._check_line_length(file_path, content))
            findings.extend(self._check_trailing_whitespace(file_path, content))
            findings.extend(self._check_missing_newline_eof(file_path, content))
            findings.extend(self._check_consecutive_blank_lines(file_path, content))
            findings.extend(self._check_indentation_consistency(file_path, content))
            all_findings.extend(findings)

        logger.info(f"[风格规则引擎] 扫描完成，发现 {len(all_findings)} 个问题")
        return all_findings

    def _check_line_length(self, file_path: str, content: str) -> list[Finding]:
        """STY-001：检测行长度"""
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
        """STY-002：检测尾随空格"""
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

    def _check_missing_newline_eof(self, file_path: str, content: str) -> list[Finding]:
        """STY-003：检测文件末尾是否缺少换行符（POSIX 规范）"""
        if content and not content.endswith('\n'):
            line_count = content.count('\n') + 1
            return [Finding(
                severity="info",
                category="style",
                file_path=file_path,
                line=line_count,
                message="文件末尾缺少换行符",
                suggestion="在文件末尾添加一个空行（POSIX 规范要求）",
                agent_source="rules",
            )]
        return []

    def _check_consecutive_blank_lines(self, file_path: str, content: str) -> list[Finding]:
        """STY-004：检测连续多余空行（连续超过3个空行）"""
        findings = []
        lines = content.split('\n')
        blank_count = 0
        for i, line in enumerate(lines, 1):
            if line.strip() == '':
                blank_count += 1
            else:
                if blank_count > self.MAX_CONSECUTIVE_BLANK_LINES:
                    findings.append(Finding(
                        severity="info",
                        category="style",
                        file_path=file_path,
                        line=i - blank_count,
                        message=f"连续 {blank_count} 个空行（建议最多 {self.MAX_CONSECUTIVE_BLANK_LINES} 个）",
                        suggestion=f"将连续空行减少到 {self.MAX_CONSECUTIVE_BLANK_LINES} 个以内",
                        agent_source="rules",
                    ))
                blank_count = 0
        return findings

    def _check_indentation_consistency(self, file_path: str, content: str) -> list[Finding]:
        """STY-005：检测同一行内混用 Tab 和空格缩进"""
        findings = []
        for i, line in enumerate(content.split('\n'), 1):
            stripped = line.lstrip()
            if not stripped:
                continue  # 空行跳过
            leading = line[:len(line) - len(stripped)]
            has_tab = '\t' in leading
            has_space = ' ' in leading
            if has_tab and has_space:
                findings.append(Finding(
                    severity="warning",
                    category="style",
                    file_path=file_path,
                    line=i,
                    message="行首缩进混用了 Tab 和空格",
                    suggestion="统一使用空格缩进（推荐 4 空格），避免混用 Tab",
                    agent_source="rules",
                ))
        return findings
