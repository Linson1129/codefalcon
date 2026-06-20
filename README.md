# CodeFalcon

<div align="center">

**猎鹰般精准的多 Agent 智能代码审查系统**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-30%20passed-brightgreen.svg)](./tests/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

*为 Vibe Coding 时代打造的 AI 代码审计安全网*

</div>

---

## 痛点

AI 代码生成工具让"写代码"变得前所未有的快，但核心挑战悄然转移：**怎么判断 AI 写的代码是否可靠？**

- Copilot 生成了 SQL 语句，有没有注入风险？
- Cursor 改了三文件，变量名是否交叉一致？
- ChatGPT 写了重试逻辑，边界条件处理正确吗？

CodeFalcon 在代码生成后自动介入，由多 Agent 协作审计安全、性能、一致性——成为人机协作开发中的最后一道防线。

## 亮点

- **0 成本过滤 80%**：规则引擎确定性检查密钥泄露、注入攻击，不消耗 Token
- **双 Agent 分工**：Agent A（DeepSeek-V3）负责 Bug + 性能，Agent B（Qwen）负责风格 + 验收
- **并行审查**：ThreadPoolExecutor 并行调度，比串行快 2 倍
- **智能汇总**：自动去重合并、优先级排序、冲突检测
- **人机回环**：多 Agent 意见冲突时弹出交互式确认
- **成本追踪**：每轮审查可见 Token 消耗和费用
- **TODO 管理**：全局编号 + 日期标签 + 内容去重 + done 命令
- **自动压缩**：每 5 次审查自动归档汇总，目录永不会爆炸

## 架构

```
代码输入
  │
  ▼
上下文收集 ── AST 解析 + 依赖图 + 调用关系
  │
  ▼
规则引擎 ──── 安全检查（0 Token：密钥、注入、eval）
  │
  ▼
风格检查 ──── 代码风格（0 Token：行长度、尾随空格）
  │
  ▼
┌──────────────┐
│ Agent A       │  并行  │  Agent B        │
│ Bug + 性能    │ ◄────► │  风格 + 验收     │
│ DeepSeek-V3  │        │  Qwen-Turbo     │
└──────┬───────┘        └──────┬──────────┘
       │                       │
       └───────────┬───────────┘
                   ▼
             汇总仲裁 ──── 去重 → 排序 → 冲突检测
                   │
                   ▼
             人机回环 ──── 有冲突? → 交互确认 → 重新决议
                   │
                   ▼
             输出报告 ──── JSON + Markdown + TODO列表
```

## 快速开始

### 环境要求

- Python 3.11+
- DeepSeek API Key（主力模型，必须）
- Qwen API Key（可选，用于降级审查）

### 安装

```bash
git clone https://github.com/Linson1129/codefalcon.git
cd codefalcon
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

```env
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
QWEN_API_KEY=your-qwen-key-here       # 可选
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 使用

```bash
# 审查单个文件
codefalcon review src/main.py

# 审查整个目录
codefalcon review src/

# 审查多个文件
codefalcon review src/main.py src/agents/base.py

# 查看待办事项
codefalcon status

# 标记完成
codefalcon done TODO-005

# 清理历史待办
codefalcon clean
```

输出示例：

```
CodeFalcon 审查完成

审查了 3 个文件
发现 12 个问题: 3 错误, 6 警告, 3 建议
新增 8 条待办事项
检测到 1 处冲突需要人工确认

报告:
  JSON:   reviews/2026-06-20/153223.json
  Markdown: reviews/2026-06-20/153223.md

本次审查成本: $0.000843
  Token: 842入 + 156出 = 998总计
```

### Docker

```bash
docker build -t codefalcon .
docker run --rm -v $(pwd)/.env:/app/.env codefalcon review src/
```

## 项目结构

```
codefalcon/
├── src/
│   ├── orchestrator/   # LangGraph StateGraph DAG 编排
│   │   ├── graph.py    #   节点定义 + 路由逻辑
│   │   ├── state.py    #   ReviewState 状态 Schema
│   │   └── router.py   #   模型分级路由
│   ├── agents/         # LLM Agent 实现
│   │   ├── base.py     #   Agent 基类（重试、工具调用）
│   │   ├── bug_perf_agent.py    # Agent A：Bug + 性能 (DeepSeek-V3)
│   │   └── style_accept_agent.py # Agent B：风格 + 验收 (Qwen)
│   ├── rules/          # 确定性规则引擎（0 Token 成本）
│   │   ├── security.py #   安全检查（密钥、密码、SQL注入、命令注入、eval）
│   │   └── style.py    #   风格检查（行长度、尾随空格）
│   ├── tools/          # Agent 可调用的代码分析工具
│   │   ├── ast_analyzer.py   # AST 解析（函数/类提取、调用图）
│   │   ├── code_search.py    # 代码搜索（定义查找、调用者分析）
│   │   └── dep_analyzer.py   # 依赖分析（import 提取、影响分析）
│   ├── context/        # 上下文收集与索引
│   │   ├── collector.py #   文件读取 + 关联代码收集
│   │   └── indexer.py   #   符号索引 + 调用关系图
│   ├── review/         # 汇总仲裁
│   │   ├── aggregator.py   # 去重合并 + 冲突检测 + TODO 生成
│   │   └── prioritizer.py  # 严重度排序 + 统计摘要
│   ├── output/         # 报告输出
│   │   ├── reporter.py     # JSON + Markdown 报告 + 压缩归档
│   │   └── todo_manager.py # TODOS.md 管理（编号 + 去重 + 清理）
│   └── utils/          # 基础设施
│       ├── config.py       # 配置管理（dotenv + LRU 单例）
│       ├── cost_tracker.py # Token 消耗追踪（单例模式）
│       └── logger.py       # 日志配置
├── tests/              # 30 个单元测试
│   ├── test_rules.py       # 安全规则引擎 (8)
│   ├── test_tools.py       # AST 分析器 (5)
│   ├── test_review.py      # 汇总仲裁器 (4)
│   ├── test_style.py       # 风格规则引擎 (7)
│   └── test_integration.py # 集成测试 (6)
├── reviews/            # 审查报告输出（gitignore）
│   └── YYYY-MM-DD/     #   按日期分文件夹
├── Dockerfile
├── ARCHITECTURE.md     # 架构设计文档
├── CONTEXT.md          # 开发进度与上下文
└── TODOS.md            # 待办事项清单
```

## 技术栈

| 分类 | 技术选型 | 选型理由 |
|------|---------|---------|
| Agent 编排 | LangGraph StateGraph | 有向无环图，状态传递清晰，支持中断恢复 |
| 主力 LLM | DeepSeek-V3 | 性能强、成本低、中文友好 |
| 降级 LLM | Qwen-Turbo | 轻量快速，适合风格检查等简单任务 |
| 规则引擎 | 纯 Python AST + Regex | 确定性规则 0 Token 成本，毫秒级响应 |
| 并行调度 | ThreadPoolExecutor | Agent A/B 并行执行，避免 LangGraph 状态冲突 |
| CLI 框架 | Click | 轻量、装饰器风格、自动生成 help |
| 配置管理 | python-dotenv + LRU 单例 | 环境变量 + 缓存复用 |
| 成本追踪 | 全局单例 | 跨 Agent 共享累计消耗 |
| 测试框架 | pytest | 标准 Python 测试框架 |

## 测试

```bash
pytest                  # 运行全部测试
pytest -v               # 详细输出
pytest tests/test_rules.py   # 指定模块
```

```
tests/test_rules.py ........    (8 passed)
tests/test_tools.py .....       (5 passed)
tests/test_review.py ....       (4 passed)
tests/test_style.py .......     (7 passed)
tests/test_integration.py .... (6 passed)
========================= 30 passed in 0.45s =========================
```

## License

MIT
