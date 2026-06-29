# CodeFalcon 上下文快照

> 🤖 **给 AI 助手看的文件** —— 切换到本工作空间时，先读这个文件即可瞬间对齐上下文。
>
> 📅 最后更新：2026-06-24
> 📦 项目版本：v0.1.0 (MVP完成，4 Agent并行化)

---

## 一、这是什么项目？

**CodeFalcon**（猎鹰代码审查）—— 面向 Vibe Coding 时代的多 Agent 协作智能代码审查系统。

核心要解决的问题：AI 生成的代码越来越多，开发者需要自动化的"代码安全网"来判断 AI 写的代码是否可靠。

### 一句话定位

> 猎鹰般精准的多 Agent 代码审查系统 —— 规则引擎 + 并行 Agent + 汇总仲裁 + 人机回环

---

## 二、当前进度

| 模块 | 状态 | 说明 |
|------|------|------|
| `src/orchestrator/` | ✅ 完成 | 10节点DAG、状态流转、条件路由、**真正LangGraph并行** |
| `src/agents/` | ✅ 实现完成 | Agent A(DeepSeek) + B(Qwen) + C(DeepSeek) + D(Qwen) |
| `src/rules/` | ✅ 实现完成 | SecurityRuleEngine(8规则) + StyleRuleEngine(2规则) |
| `src/tools/` | ✅ 完成 | ASTAnalyzer、DepAnalyzer、CommentPoisoningDetector |
| `src/context/` | ✅ 完成 | Collector + Spec加载，依赖分析结果注入Agent提示词 |
| `src/review/` | ✅ 实现完成 | Aggregator(去重+排序+冲突检测) + Prioritizer |
| `src/output/` | ✅ 实现完成 | Reporter(按日期分文件夹+5次压缩) + TodoManager |
| `src/skills/` | ✅ 完成 | Skill加载器 + Skill执行器（规则型+LLM型） |
| `src/output/` | ✅ 实现完成 | Reporter + TodoManager + AgentBridge + MCPServer |
| `src/main.py` | ✅ CLI完成 | `review`/`status`/`done`/`export`/`serve` 五命令全实现 |
| `tests/` | ✅ **30/30 全部通过** | 安全8 + 风格7 + AST5 + 仲裁4 + 集成6 |

---

## 三、测试清单（30个 ✅ 全部通过）

### test_rules.py — 8个
1. `test_detect_hardcoded_api_key` — 检测 `sk-xxx` 格式密钥
2. `test_detect_hardcoded_password` — 检测 `password = "xxx"`
3. `test_detect_sql_injection_format` — 检测 `%s` 格式化SQL
4. `test_detect_sql_injection_fstring` — 检测 f-string SQL
5. `test_detect_command_injection_os_system` — 检测 `os.system()` 拼接
6. `test_detect_eval` — 检测 `eval()` 调用
7. `test_clean_code_no_findings` — 干净代码返回0发现
8. `test_multiple_files` — 多文件扫描

### test_style.py — 7个
1. `test_line_length_ok` — 行长度合规
2. `test_line_length_exceeded` — 行长度超限
3. `test_line_length_boundary` — 边界值测试
4. `test_trailing_whitespace_space` — 空格结尾
5. `test_trailing_whitespace_tab` — Tab结尾
6. `test_clean_code_no_findings` — 干净代码
7. `test_multiple_files` — 多文件

### test_tools.py — 5个
1. `test_extract_function_definitions` — AST提取函数定义
2. `test_extract_class_definitions` — AST提取类定义+方法
3. `test_build_call_graph` — 构建调用关系图
4. `test_empty_code` — 空代码边界
5. `test_syntax_error_handling` — 语法错误容错

### test_review.py — 4个
1. `test_deduplicate_same_line` — 同行去重取最高严重度
2. `test_priority_sorting` — 优先级排序(security>style, error>info)
3. `test_empty_findings` — 空发现边界
4. `test_conflict_detection` — Agent间冲突产生 pending_questions

### test_integration.py — 6个
1. `test_full_pipeline_with_mock_agents` — Mock Agent完整流水线
2. `test_generate_report` — 报告生成
3. `test_add_mark_done_flow` — Todo添加/标记完成流程
4. `test_review_no_target` — 无目标路径CLI
5. `test_status_ok` — 状态查询CLI
6. `test_done_ok` — 标记完成CLI

---

## 四、架构关键决策

### 为什么用 LangGraph 而不是 CrewAI/AutoGen？

CodeFalcon 是**多阶段流水线**，不是自由对话：
- 明确的状态流转（ReviewState dataclass）
- 条件路由（遇复杂问题→人机回环）
- **真正的并行节点**（4个Agent扇出，LangGraph自动调度）
- 内置 Human-in-the-loop（interrupt 机制）

### Agent 通信模式：metadata 传递（避免并行节点副作用）

并行Agent节点不直接修改共享 state（会导致 race condition）。
- Agent A 的交接文档存入 `Finding.metadata["handover"]`
- Agent C/D 的总结也存入各自 `Finding.metadata`
- 汇总阶段从 metadata 中读取

### 三级成本控制路由

| 层级 | 用什么 | 成本 | 场景 |
|------|--------|------|------|
| L1 规则引擎 | 正则/AST | $0 | 硬编码密钥、SQL注入、尾随空格、投毒检测 |
| L2 廉价模型 | Qwen-Turbo | ~$0.00005/1K tokens | 风格检查、规范审查 |
| L3 标准模型 | DeepSeek-V3 | ~$0.00014/1K tokens | Bug检测、性能分析、架构审查 |

### 技术栈速查

```
LangGraph (编排) + LangChain (LLM抽象)
Click (CLI) + Pydantic (数据模型) + python-dotenv (配置)
Python AST (代码分析) + pytest (测试)
OpenAI SDK (DeepSeek/Qwen 兼容接口)
```

---

## 五、DAG 流程（8个节点）

```
poisoning_detect
       ↓
context_collection (含Spec加载)
       ↓
rule_engine (安全规则)
       ↓
style_engine (风格规则)
       ↓
skill_engine (规则型Skill执行)
       ↓↓↓↓
   [并行扇出]
   agent_a  agent_b  agent_c  agent_d
   (Bug+Perf)(Style+Accept)(Architecture)(SpecCheck)
       ↓↓↓↓
       aggregate (去重+排序+冲突检测)
           ↓
       {有冲突?}
        /      \
  human_interrupt  generate_output
        \      /
       generate_output (JSON报告)
           ↓
         END
```

---

## 六、目录速查

```
codefalcon/
├── src/
│   ├── main.py                  ← CLI入口（review/status/done/export/serve）
│   ├── orchestrator/
│   │   ├── state.py             ← ReviewState + Finding 数据模型
│   │   └── graph.py             ← StateGraph定义(8节点DAG，真正并行)
│   ├── agents/
│   │   ├── base.py              ← Agent基类(LLM调用+重试降级+成本追踪)
│   │   ├── bug_perf_agent.py    ← Agent A (Bug+性能, DeepSeek)
│   │   ├── style_accept_agent.py ← Agent B (风格+验收, Qwen)
│   │   ├── architect_agent.py   ← Agent C (架构审查, DeepSeek)
│   │   └── spec_check_agent.py  ← Agent D (规范驱动审查, Qwen)
│   ├── rules/
│   │   ├── security.py          ← 安全规则引擎(5规则)
│   │   └── style.py             ← 风格规则引擎(行长度+尾随空格)
│   ├── tools/
│   │   ├── ast_analyzer.py      ← AST分析
│   │   ├── dep_analyzer.py      ← 依赖分析
│   │   └── comment_poisoning_detector.py ← 注释投毒检测
│   ├── context/
│   │   └── collector.py         ← 上下文收集+Spec加载
│   ├── skills/
│   │   ├── skill_loader.py      ← Skill加载器(YAML)
│   │   └── skill_executor.py    ← Skill执行器(规则型+LLM型)
│   ├── review/
│   │   ├── aggregator.py        ← 汇总仲裁(去重+排序+冲突检测)
│   │   └── prioritizer.py       ← 优先级排序
│   ├── output/
│   │   ├── reporter.py          ← 报告生成(JSON+Markdown+压缩归档)
│   │   ├── todo_manager.py      ← 待办管理
│   │   ├── agent_bridge.py      ← Agent Prompt 生成器
│   │   └── mcp_server.py        ← MCP Server (Agent工具调用)
│   └── utils/
│       ├── config.py            ← 配置管理(DeepSeek+Qwen)
│       ├── cost_tracker.py      ← Token成本追踪(全局单例)
│       └── logger.py            ← 日志
├── tests/
│   ├── test_rules.py            ← 安全规则测试(8个)
│   ├── test_style.py            ← 风格规则测试(7个)
│   ├── test_tools.py            ← AST分析器测试(5个)
│   ├── test_review.py           ← 汇总仲裁器测试(4个)
│   ├── test_integration.py      ← 集成测试(6个)
│   └── fixtures/
│       ├── sample_buggy.py      ← 有Bug测试样本
│       └── sample_clean.py      ← 干净代码测试样本
├── skills/                      ← YAML规则型Skill定义
│   └── security/
│       └── sql_injection.yaml
├── spec.md                      ← CodeFalcon 项目规范（Agent D对照）
├── .codefalcon/                 ← Agent Prompt 输出目录
├── reviews/                     ← 审查报告输出目录
├── CONTEXT.md                   ← 📍 你正在读的文件
├── ARCHITECTURE.md             ← 详细架构设计文档
├── README.md                    ← 项目README
├── pyproject.toml              ← 项目配置+CLI入口注册
├── requirements.txt             ← Python依赖
├── .env.example                 ← 环境变量模板
└── TODOS.md                    ← 待办清单
```

---

## 七、待办清单（按优先级）

### 🔴 P0 — 核心流程打通 ✅ 已完成
- [x] 实现 Agent A `review()` 方法——接 DeepSeek API
- [x] 实现 Agent B `review()` 方法——接 Qwen API
- [x] 实现 Agent C `review()` 方法——架构审查
- [x] 实现 Agent D `review()` 方法——规范驱动审查
- [x] 实现 `review` 命令完整流水线（8节点DAG）
- [x] 真正LangGraph并行（4个Agent同时跑）

### 🟡 P1 — 完善输出层 ✅ 已完成
- [x] JSON + Markdown 双格式报告，按日期分文件夹
- [x] TODOS.md 全局序号 + 日期标注 + pending/done 分区
- [x] CLI `review`/`status`/`done` 三命令全实现
- [x] 每5次审查自动压缩归档

### 🟢 P2 — 扩展能力 ✅ 已完成
- [x] 风格规则引擎（行长度、尾随空格），接入DAG
- [x] CodeSearch + DepAnalyzer 工具接入Agent上下文
- [x] Token 成本统计（全局单例 + CLI显示 + 报告嵌入）
- [x] 集成测试 6个（含mock流水线、CLI命令）
- [x] 注释投毒检测（CommentPoisoningDetector）
- [x] Skill系统（规则型+YAML定义+执行器）
- [x] 规范驱动审查（OpenSpec Agent D）

### 🔵 P3 — 工程化
- [x] Dockerfile 完善
- [ ] CI/CD pipeline 配置（GitHub Actions）
- [ ] 生产级性能测试与优化
- [ ] Web UI 或 IDE 插件
- [ ] .env.example 去除真实API Key（安全风险）

---

## 八、快速启动命令

```bash
cd /Users/macbook/CodeBuddy/codefalcon

# 安装依赖
pip install -r requirements.txt

# 配置API Key
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY 和 QWEN_API_KEY

# 运行测试（30个全部应通过）
python -m pytest tests/ -v

# CLI使用
python -m src.main review ./tests/fixtures/sample_buggy.py
python -m src.main status
python -m src.main done 1

# 可视化DAG（需要graphviz）
python -c "from src.orchestrator.graph import visualize_graph; visualize_graph()"
```

---

## 九、已知问题及修复记录

### 已修复（2026-06-24审查）
1. ✅ 并行Agent节点返回 `current_stage` 导致 `InvalidUpdateError` → 并行节点不再返回 `current_stage`
2. ✅ `aggregator.py` 未合并 `agent_c/d_findings` → 已补全
3. ✅ Agent节点读取 `target_files` 而非 `filtered_files` → 改为优先用 `filtered_files`
4. ✅ 并行节点直接修改 `state.diff_context`（副作用）→ 改为存入 `Finding.metadata`
5. ✅ `comment_poisoning_detector.py` 多处语法错误（正则字符串、函数参数）→ 完全重写
6. ✅ `reporter.py` `_normalize_state` 缺失字段 → 已补全
7. ✅ `graph.py` DAG路由冲突 → 已修复条件路由逻辑
8. ✅ RAG 模块（LightRAG）整体移除 → 推理：本地向量数据库无共享价值，query/insert 调 LLM 成本高，Agent 自身 Prompt 已足够
