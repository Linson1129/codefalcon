# CodeFalcon

> 猎鹰般俯视你的代码，然后揪出问题
一个多Agent代码审查系统项目 —— 面向Vibe Coding时代的AI代码审计Agent

## 定位

在AI生成代码日益普及的背景下，开发者面临的核心挑战从"怎么写代码"转变为"怎么判断AI写的代码是否可靠"。CodeFalcon通过多Agent协作，在代码生成后自动审计安全、性能、跨文件一致性问题，成为人机协作开发中的安全网。

## 架构

```
代码提交 → 上下文收集 → 并行审查（规则引擎 + Agent A + Agent B）→ 汇总仲裁 → 人机回环 → 输出报告
```

- **规则引擎**：确定性安全检查（硬编码密钥、注入检测），0 Token成本
- **Agent A**：Bug检测 + 性能分析，DeepSeek-V3驱动
- **Agent B**：风格检查 + 验收，Qwen驱动
- **汇总仲裁**：去重合并、优先级排序、冲突检测
- **人机回环**：复杂问题交互式确认

详见 [ARCHITECTURE.md](./ARCHITECTURE.md)

## 快速开始

### 环境要求
- Python 3.11+
- DeepSeek API Key（主力模型）
- Qwen API Key（可选，用于降级）

### 安装

```bash
git clone <repo-url>
cd codefalcon
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

### 使用

```bash
# 审查单个文件
codefalcon review ./src/auth.py

# 审查整个目录
codefalcon review ./src/

# 查看待办事项
codefalcon status

# 标记完成
codefalcon done TODO-001
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Agent编排 | LangGraph |
| LLM（主力） | DeepSeek-V3 |
| LLM（降级） | Qwen-Turbo |
| 代码分析 | Python AST |
| CLI | Click |
| 配置管理 | python-dotenv |
| 测试 | pytest |

## 目录结构

```
codefalcon/
├── src/
│   ├── orchestrator/   # LangGraph编排引擎
│   ├── agents/         # Agent定义（Bug+性能 / 风格+验收）
│   ├── rules/          # 规则引擎（安全检查）
│   ├── tools/          # Agent工具（代码搜索、AST分析、依赖分析）
│   ├── context/        # 上下文收集与索引
│   ├── review/         # 汇总仲裁与优先级排序
│   ├── output/         # 报告生成与待办管理
│   └── utils/          # 配置、日志、成本追踪
├── tests/              # 单元测试
├── reviews/            # 审查报告输出
└── ARCHITECTURE.md     # 架构设计文档
```

## License

MIT
