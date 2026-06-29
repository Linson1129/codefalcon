"""Agent D - OpenSpec 规范驱动审查（借鉴 OpenSpec 理念）"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from .base import BaseAgent
from src.orchestrator.state import Finding, ReviewState

logger = logging.getLogger(__name__)


class SpecCheckAgent(BaseAgent):
    """Agent D: 规范驱动审查，检查代码是否符合项目规范文档

    核心理念（借鉴 OpenSpec）：
    - 先有规范（spec.md / design.md），再写代码
    - 审查时读取项目规范文档
    - 检查代码实现是否符合规范描述
    - 发现"规范与实现不一致"的问题
    """

    SPEC_FILES = [
        "spec.md", "SPEC.md", "specs.md", "SPECS.md",
        "design.md", "DESIGN.md",
        "proposal.md", "PROPOSAL.md",
        "openspec.md", "OPENSP.md",
    ]

    def __init__(self, dry_run: bool = False):
        super().__init__(name="SpecCheckAgent", model="qwen-turbo", dry_run=dry_run)

    def get_system_prompt(self) -> str:
        return """你是一个规范驱动的代码审查专家，负责检查代码实现是否符合项目规范文档。

审查要点：
1. 规范对齐：
   - 代码实现的功能是否与 spec.md / design.md 描述一致
   - 接口签名是否与规范定义一致
   - 数据结构是否与规范定义一致
   - 错误处理是否符合规范要求

2. 规范完整性：
   - 是否有规范文档但代码未实现的部分
   - 代码是否实现了规范中未描述的功能（范围蔓延）
   - 规范中的边界条件和异常情况是否正确处理

3. 规范质量：
   - 规范本身是否足够清晰和可测试
   - 是否有歧义或不一致的地方

输出格式（JSON）：
{
  "findings": [
    {
      "severity": "error|warning|info",
      "category": "spec",
      "file_path": "...",
      "line": 88,
      "message": "简短描述问题",
      "suggestion": "修复建议（引用规范中的具体章节）"
    }
  ],
  "spec_compliance_summary": "规范符合性总结：哪些部分符合，哪些不符合"
}
"""

    def find_spec_files(self, project_root: str = ".") -> list[str]:
        """查找项目中的规范文档"""
        spec_files = []
        root = Path(project_root)
        for spec_name in self.SPEC_FILES:
            found = list(root.rglob(spec_name))
            spec_files.extend([str(f) for f in found])
        return spec_files

    def load_spec_content(self, project_root: str = ".") -> str:
        """加载所有规范文档内容"""
        spec_files = self.find_spec_files(project_root)
        if not spec_files:
            logger.info("[SpecCheckAgent] 未找到规范文档")
            return ""

        parts = ["=== 项目规范文档 ===\n"]
        for spec_file in spec_files:
            try:
                content = Path(spec_file).read_text(encoding="utf-8")
                parts.append(f"\n--- {spec_file} ---\n{content}\n")
            except Exception as e:
                logger.warning(f"[SpecCheckAgent] 读取 {spec_file} 失败: {e}")

        return "\n".join(parts)

    def review(self, state: ReviewState) -> list[Finding]:
        """执行规范驱动审查"""
        logger.info(f"[{self.name}] 开始规范驱动审查")

        # 查找项目根目录（从 target_paths 推断）
        project_root = self._infer_project_root(state.target_paths)
        spec_content = self.load_spec_content(project_root)

        if not spec_content:
            logger.info(f"[{self.name}] 未找到规范文档，跳过规范审查")
            return []

        findings = []

        files_to_scan = state.filtered_files if state.filtered_files else state.target_files
        for file_path, content in files_to_scan.items():
            try:
                user_prompt = self._build_review_prompt(
                    file_path, content, spec_content,
                )
                result = self.call_llm(
                    system_prompt=self.get_system_prompt(),
                    user_prompt=user_prompt,
                )

                parsed = self.parse_response(
                    result.get("content", "{}"),
                    default_extra="",
                )
                findings.extend(
                    self.to_findings(
                        parsed.get("findings", []), file_path,
                        agent_source="agent_d",
                        default_category="spec",
                        default_severity="info",
                    )
                )

                # 保存规范总结到 metadata
                summary = parsed.get("spec_compliance_summary", "")
                if summary and findings:
                    findings[-1].metadata["spec_compliance_summary"] = summary

            except Exception as e:
                logger.error(f"[{self.name}] 审查 {file_path} 失败: {e}")
                continue

        logger.info(f"[{self.name}] 规范审查完成，发现 {len(findings)} 个问题")
        return findings

    def _infer_project_root(self, target_paths: list[str]) -> str:
        """从 target_paths 推断项目根目录"""
        if not target_paths:
            return "."
        first_path = Path(target_paths[0])
        # 向上查找包含规范文档的目录
        for parent in [first_path] + list(first_path.parents):
            for spec_name in self.SPEC_FILES:
                if (parent / spec_name).exists():
                    return str(parent)
        # 默认使用第一个路径的父目录
        return str(first_path.parent) if first_path.is_file() else str(first_path)

    def _build_review_prompt(
        self,
        file_path: str,
        content: str,
        spec_content: str,
    ) -> str:
        """构建规范审查提示词"""
        prompt_parts = [
            f"请检查以下代码是否符合项目规范:\n",
            f"文件: {file_path}\n",
            f"```\n{content}\n```\n",
            "\n--- 项目规范文档 ---\n",
            spec_content[:4000],  # 限制长度，避免超 token
        ]

        prompt_parts.append(
            "\n请仔细对比代码实现与规范描述，找出不符合的地方。"
            "如果规范文档不存在或不完整，请标注为 info 级别的发现。"
        )
        return "\n".join(prompt_parts)


