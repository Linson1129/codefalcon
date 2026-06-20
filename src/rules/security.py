"""安全规则引擎 - 硬编码密钥、SQL注入、命令注入检测"""

import re
import logging

from src.orchestrator.state import Finding

logger = logging.getLogger(__name__)


class SecurityRuleEngine:
    """基于规则的安全检查引擎（0 Token成本）

    检测项：
    - 硬编码密钥/密码/Token
    - SQL注入风险（字符串拼接）
    - 命令注入风险
    - 危险函数调用
    """

    # 硬编码密钥模式
    HARDCODED_SECRET_PATTERNS = [
        (r'(?i)(api[_-]?key|api[_-]?secret|access[_-]?token)\s*[:=]\s*["\'][\w\-]{8,}["\']', "硬编码API密钥"),
        (r'(?i)(password|passwd|pwd)\s*[:=]\s*["\'][^"\']+["\']', "硬编码密码"),
        (r'(?i)(secret[_-]?key|private[_-]?key)\s*[:=]\s*["\'][^"\']+["\']', "硬编码密钥"),
        (r'(?i)(token|auth[_-]?token)\s*[:=]\s*["\'][\w\-.]{8,}["\']', "硬编码Token"),
    ]

    # SQL注入风险模式
    SQL_INJECTION_PATTERNS = [
        (r'(?i)(execute|cursor\.execute)\s*\(\s*["\'].*\%s.*["\']', "SQL字符串格式化（%s）"),
        (r'(?i)(execute|cursor\.execute)\s*\(\s*["\'].*\{\}.*["\']', "SQL字符串格式化（{}）"),
        (r'(?i)(execute|cursor\.execute)\s*\(\s*f["\']', "SQL f-string拼接"),
        (r'(?i)\.execute\s*\(\s*["\'].*\+.*\+.*["\']', "SQL字符串拼接（+）"),
        (r'(?i)\.execute\s*\(\s*["\'].*\.format\(', "SQL .format() 拼接"),
    ]

    # 命令注入风险模式
    COMMAND_INJECTION_PATTERNS = [
        (r'os\.system\s*\(', "使用 os.system()（存在注入风险，建议用 subprocess）"),
        (r'os\.popen\s*\(', "使用 os.popen()（存在注入风险）"),
        (r'(?i)eval\s*\(', "使用 eval() 函数"),
        (r'(?i)exec\s*\(', "使用 exec() 函数"),
        (r'subprocess\.(call|run|Popen)\s*\(\s*[^,)]*\bshell\s*=\s*True', "subprocess 使用 shell=True"),
    ]

    def scan(self, target_files: dict[str, str]) -> list[Finding]:
        """扫描所有目标文件

        Args:
            target_files: {文件路径: 文件内容} 的字典

        Returns:
            发现的问题列表
        """
        all_findings = []

        for file_path, content in target_files.items():
            findings = []
            findings.extend(self._check_hardcoded_secrets(file_path, content))
            findings.extend(self._check_sql_injection(file_path, content))
            findings.extend(self._check_command_injection(file_path, content))
            all_findings.extend(findings)

        logger.info(f"[规则引擎] 扫描完成，发现 {len(all_findings)} 个问题")
        return all_findings

    def _check_hardcoded_secrets(self, file_path: str, content: str) -> list[Finding]:
        """检测硬编码密钥"""
        findings = []
        for pattern, description in self.HARDCODED_SECRET_PATTERNS:
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count('\n') + 1
                findings.append(Finding(
                    severity="error",
                    category="security",
                    file_path=file_path,
                    line=line_num,
                    message=f"{description}",
                    suggestion="请使用环境变量或密钥管理服务存储敏感信息",
                    agent_source="rules",
                ))
        return findings

    def _check_sql_injection(self, file_path: str, content: str) -> list[Finding]:
        """检测SQL注入风险"""
        findings = []
        for pattern, description in self.SQL_INJECTION_PATTERNS:
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count('\n') + 1
                findings.append(Finding(
                    severity="error",
                    category="security",
                    file_path=file_path,
                    line=line_num,
                    message=f"SQL注入风险: {description}",
                    suggestion="请使用参数化查询（如 ? 占位符）防止SQL注入",
                    agent_source="rules",
                ))
        return findings

    def _check_command_injection(self, file_path: str, content: str) -> list[Finding]:
        """检测命令注入风险"""
        findings = []
        for pattern, description in self.COMMAND_INJECTION_PATTERNS:
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count('\n') + 1
                findings.append(Finding(
                    severity="warning",
                    category="security",
                    file_path=file_path,
                    line=line_num,
                    message=description,
                    suggestion="请使用 subprocess.run() 并设置 shell=False，参数用列表传递",
                    agent_source="rules",
                ))
        return findings
