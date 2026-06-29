# CodeFalcon

<div align="center">

**猎鹰般精准的多 Agent 智能代码审查系统**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-72%20passed-brightgreen.svg)](./tests/)
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

- **4 Agent 并行审查**：LangGraph 原生扇出/汇聚，Bug+性能、风格+验收、架构、规范四维度同时执行
- **0 成本过滤 80%**：规则引擎确定性检查密钥泄露、注入攻击、投毒检测、代码风格，不消耗 Token
- **三级成本路由**：规则引擎 $0 → 轻量模型 → 主力模型，按复杂度分配合适模型
- **Skill 插件系统**：YAML 定义审查技能，支持规则型（正则）+ LLM 型（Prompt 注入）双模式
- **智能汇总仲裁**：自动去重合并、优先级排序、冲突检测
- **人机回环**：多 Agent 意见冲突时弹出交互式确认
- **MCP Server**：支持 stdio/HTTP-SSE 双模式，编码 Agent 可通过 MCP 协议直接调用
- **Agent Bridge**：审查结果转 CodeBuddy/Cursor/Universal 三种格式的修复 Prompt
- **成本追踪**：全局单例跨 Agent 累计 Token 消耗和费用
- **TODO 管理**：全局编号 + 日期标签 + 智能去重 + done/clean 命令
- **滚动归档**：保留最新 N 次报告，自动淘汰旧报告

## 架构

```
代码输入
  │
  ▼
注释投毒检测 ──── 检测并中和恶意注释
  │
  ▼
上下文收集 ──── AST 解析 + 依赖图 + 调用关系 + 规范文档加载
  │
  ▼
规则引擎 ──── 安全检查（0 Token：密钥、注入、eval）
  │
  ▼
风格检查 ──── 代码风格（0 Token：行长度、尾随空格、缩进、空行、文件末尾换行）
  │
  ▼
Skill 引擎 ──── YAML 定义的审查技能（规则型 + LLM 型）
  │
  ▼
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Agent A       │ Agent B      │ Agent C      │ Agent D      │
│ Bug + 性能    │ 风格 + 验收   │ 架构审查     │ 规范审查     │
│ 主力模型      │ 轻量模型     │ 主力模型     │ 轻量模型     │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┘
       │              │              │              │
       └──────────────┴──────────────┴──────────────┘
                            │
                            ▼
                   汇总仲裁 ──── 去重 → 排序 → 冲突检测
                            │
                            ▼
                   人机回环 ──── 有冲突? → 交互确认
                            │
                            ▼
                   输出报告 ──── JSON + Markdown + TODO 列表
                            │
                            ▼
                   Agent Bridge ──── CodeBuddy/Cursor/Universal Prompt
```

## 快速开始

### 环境要求

- Python 3.11+
- 高成本大模型 API Key（如 DeepSeek、OpenAI 等，用于复杂推理任务）
- 低成本大模型 API Key（如 Qwen、GLM 等，用于风格检查等轻量任务，可选）

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
# 主力模型（复杂推理：Bug检测、性能分析、架构审查）
HIGH_COST_LLM_API_KEY=sk-your-key-here
HIGH_COST_LLM_BASE_URL=https://api.deepseek.com

# 辅助模型（轻量任务：风格检查、规范审查，可选）
LOW_COST_LLM_API_KEY=your-key-here
LOW_COST_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 使用

```bash
# 审查单个文件
codefalcon review src/main.py

# 审查整个目录（全量模式）
codefalcon review src/

# 增量审查（仅审查 vs main 的 git 变更文件）
codefalcon review . --mode diff

# Dry-Run 空跑测试（走完整 DAG，不调真实 LLM）
codefalcon review src/ --dry-run

# JSON 输出（供脚本 / Agent 消费）
codefalcon review src/ --json

# 同时生成 Agent 修复 Prompt
codefalcon review src/ --agent-output codebuddy

# 从历史报告导出 Prompt
codefalcon export reviews/latest.json -f cursor

# 启动 MCP Server（让编码 Agent 直接调用）
codefalcon serve                        # stdio 模式
codefalcon serve --http --port 8765     # HTTP/SSE 模式

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
│   ├── main.py              ← CLI 入口（review / status / done / export / clean / serve）
│   ├── orchestrator/        # LangGraph StateGraph DAG 编排
│   │   ├── graph.py         #   10 节点 DAG + 4 Agent 并行扇出
│   │   └── state.py         #   ReviewState 状态 Schema + Finding 数据模型
│   ├── agents/              # 4 个专用 LLM Agent
│   │   ├── base.py          #   Agent 基类（重试降级、成本追踪、Token 预算保护）
│   │   ├── bug_perf_agent.py        # Agent A: Bug + 性能 (主力模型)
│   │   ├── style_accept_agent.py    # Agent B: 风格 + 验收 (轻量模型)
│   │   ├── architect_agent.py       # Agent C: SOLID / 架构 (主力模型)
│   │   └── spec_check_agent.py      # Agent D: 规范驱动审查 (轻量模型)
│   ├── rules/               # 确定性规则引擎（0 Token）
│   │   ├── security.py      #   安全检查（密钥、SQL注入、命令注入、eval）
│   │   └── style.py         #   风格检查（行长度、尾随空格、空行、缩进、文件末尾换行）
│   ├── tools/               # 代码分析工具
│   │   ├── ast_analyzer.py           # AST 解析（函数/类提取、调用图）
│   │   ├── dep_analyzer.py           # 依赖分析（import 图、影响分析）
│   │   ├── diff_analyzer.py          # Git diff 增量分析
│   │   └── comment_poisoning_detector.py  # 注释投毒检测与中和
│   ├── context/             # 上下文收集
│   │   └── collector.py     #   文件读取 + 调用关系 + 依赖分析
│   ├── skills/              # Skill 插件系统
│   │   ├── skill_loader.py  #   YAML 加载 + Skill 对象模型
│   │   └── skill_executor.py #   执行器（规则型正则 + 行数阈值 + LLM 型）
│   ├── review/              # 汇总仲裁
│   │   ├── aggregator.py    #   去重合并 + 冲突检测 + TODO 生成
│   │   └── prioritizer.py   #   统一优先级排序器
│   ├── output/              # 输出层
│   │   ├── reporter.py      #   JSON 报告 + 滚动窗口归档
│   │   ├── todo_manager.py  #   TODOS.md 管理（全局编号 + 智能去重）
│   │   ├── agent_bridge.py  #   审查结果 → Agent Prompt 转换器
│   │   └── mcp_server.py    #   MCP Server（stdio + HTTP/SSE）
│   └── utils/               # 基础设施
│       ├── config.py        #   配置管理（dotenv + LRU 单例）
│       ├── cost_tracker.py  #   Token 消耗追踪（全局单例）
│       └── logger.py        #   日志配置
├── skills/                  # YAML 定义的审查技能（9 个）
│   ├── security/            #   安全（sql_injection, hardcoded_secret, command_injection）
│   ├── performance/         #   性能（n_plus_one, loop_repeated_computation）
│   ├── architecture/        #   架构（module_coupling, solid_principles）
│   └── style/               #   风格（function_length, naming_convention）
├── tests/                   # 72 个测试
│   ├── test_rules.py        #   安全规则引擎 (8)
│   ├── test_style.py        #   风格规则引擎 (7)
│   ├── test_tools.py        #   AST 分析器 (5)
│   ├── test_review.py       #   汇总仲裁器 (4)
│   ├── test_integration.py  #   集成测试 (6)
│   ├── test_e2e.py          #   端到端测试 (6)
│   ├── test_poisoning.py    #   投毒检测测试 (5)
│   ├── test_skill_executor.py   #   Skill 执行器 (6)
│   ├── test_dep_analyzer.py     #   依赖分析 (6)
│   └── test_base_agent.py       #   Agent 基类 (6)
├── .github/workflows/       # CI/CD
│   └── codefalcon-review.yml  # PR 自动审查
├── reviews/                 # 审查报告输出（gitignore）
├── Dockerfile
├── ARCHITECTURE.md          # 架构设计文档
├── CONTEXT.md               # 开发进度与上下文快照
├── spec.md                  # 项目规范定义
└── TODOS.md                 # 待办事项清单
```

## 技术栈

| 分类 | 技术选型 | 选型理由 |
|------|---------|---------|
| Agent 编排 | LangGraph StateGraph | 有向无环图，状态传递清晰，原生并行，支持中断恢复 |
| 主力 LLM | 高成本推理模型 | 高性能、多维度分析，兼容 OpenAI SDK |
| 降级 LLM | 低成本辅助模型 | 轻量快速，适合风格检查、规范审查等简单任务 |
| 规则引擎 | 纯 Python AST + Regex | 确定性规则 0 Token 成本，毫秒级响应 |
| 并行调度 | LangGraph 原生扇出 | 4 Agent 同时执行，自动汇聚，避免竞态 |
| Skill 系统 | YAML + 正则 + 行统计 | 声明式定义，规则型 0 Token + LLM 型 fallback |
| CLI 框架 | Click | 轻量、装饰器风格、自动生成 help |
| 配置管理 | python-dotenv + LRU 单例 | 环境变量 + 缓存复用 |
| 成本追踪 | 全局单例 | 跨 Agent 共享累计消耗 |
| MCP Server | mcp + starlette + uvicorn | 双模式：stdio（IDE Agent 集成）+ HTTP/SSE（远程调用）|
| 测试框架 | pytest | 标准 Python 测试框架 |

## 测试

```bash
pytest                  # 运行全部测试
pytest -v               # 详细输出
pytest tests/test_rules.py   # 指定模块
```

```
tests/test_rules.py ........                (8 passed)
tests/test_style.py .......                 (7 passed)
tests/test_tools.py .....                   (5 passed)
tests/test_review.py ....                   (4 passed)
tests/test_integration.py ......            (6 passed)
tests/test_e2e.py ......                    (6 passed)
tests/test_poisoning.py .....               (5 passed)
tests/test_skill_executor.py ......         (6 passed)
tests/test_dep_analyzer.py ......           (6 passed)
tests/test_base_agent.py ......             (6 passed)
======================================== 72 passed in 0.45s ================================
```

## License

MIT
