# CodeFalcon 项目规范

> 本文件是 CodeFalcon 的规范定义文档，供 SpecCheckAgent 在审查时对照检查实现是否符合规范。

---

## 1. 系统概述

CodeFalcon 是一个面向 Vibe Coding 时代的多 Agent 协作智能代码审查系统，定位为 AI 生成代码后的"最后一道质量防线"。

### 1.1 核心目标

- 在代码提交前自动审查 AI 生成的代码，检测安全漏洞、Bug、性能问题、风格问题和架构问题
- 通过多 Agent 并行协作和确定性规则引擎实现成本可控的高质量审查
- 支持人机回环：当多 Agent 意见冲突时，由人工决策

### 1.2 设计原则

- **规则+Agent 混合决策**：确定性检查 0 成本，复杂推理按需调用 LLM
- **多 Agent 并行协作**：维度独立则并行，有依赖则串行
- **分级成本控制**：规则引擎 → Qwen → DeepSeek 三级路由
- **人机协作回环**：Agent 判断不了的交给人工，人的决策反哺系统

---

## 2. CLI 接口规范

### 2.1 命令列表

| 命令 | 格式 | 功能 |
|------|------|------|
| `review` | `codefalcon review <path...>` | 审查指定文件或目录 |
| `status` | `codefalcon status` | 查看当前待办事项 |
| `done` | `codefalcon done <id>` | 标记指定待办为已完成 |
| `export` | `codefalcon export <report_path>` | 从历史报告导出 Agent Prompt 或 Markdown |
| `clean` | `codefalcon clean` | 清理 TODOS.md 中的重复和低价值待办 |
| `serve` | `codefalcon serve [--http] [--port]` | 启动 MCP Server（stdio 或 HTTP/SSE 模式） |

### 2.2 review 命令行为

- **输入**：至少一个文件或目录路径（必须）
- **无参数时**：应报错并提示用法，exit_code ≠ 0
- **仅审查 Python 文件**（`.py` 后缀）
- **输出**：控制台摘要 + JSON 报告 + Markdown 报告 + 更新 TODOS.md

### 2.3 status 命令行为

- 读取 `TODOS.md` 并展示待办列表
- 区分 pending 和 done 分区
- exit_code 应为 0

### 2.4 done 命令行为

- 接收一个 TODO ID（如 `TODO-001`）
- 将该待办从 pending 标记为 done
- ID 不存在时应给出提示
- exit_code 应为 0

---

## 3. 审查流水线规范

### 3.1 流水线阶段（严格顺序）

```
1. 注释投毒检测 (poisoning_detect)
2. 上下文收集 (context_collection) → 含规范文档加载
3. 规则引擎 (rule_engine) → 安全规则扫描
4. 风格引擎 (style_engine) → 风格规则扫描
5. Skill 引擎 (skill_engine) → 执行规则型 Skill
6. 4 Agent 并行审查 (agent_a/b/c/d 同时执行)
7. 汇总仲裁 (aggregate) → 去重、排序、冲突检测
8. 人机回环 (human_interrupt) → 有条件执行
9. 输出生成 (generate_output) → JSON 报告
```

### 3.2 并行执行约束

- Agent A/B/C/D 必须从同一节点扇出，LangGraph 自动并行调度
- 并行 Agent 不得直接修改共享 state（通过 Finding.metadata 传递信息）
- 所有 Agent 完成后才进入汇总阶段

### 3.3 优雅降级要求

- Qwen API 不可用时，Agent B/D 应降级但 A/C 继续工作
- 任何 Agent 失败不应阻塞其他 Agent 的执行

---

## 4. Agent 规范

### 4.1 各 Agent 职责

| Agent | 模型 | 职责 | 输出分类 |
|-------|------|------|---------|
| Agent A | DeepSeek | Bug 检测 + 性能分析 | bug, performance |
| Agent B | Qwen | 风格检查 + 验收 | style |
| Agent C | DeepSeek | SOLID 原则 / 架构审查 | architecture |
| Agent D | Qwen | 规范驱动审查（对照 spec.md） | spec |

### 4.2 Agent 输出格式

所有 Agent 必须返回 JSON，包含 `findings` 数组，每个 finding 包含：

```json
{
  "severity": "error|warning|info",
  "category": "...",
  "file_path": "...",
  "line": <int>,
  "message": "简短描述",
  "suggestion": "修复建议"
}
```

### 4.3 Agent A 审查要点

- 空指针/None 引用风险
- 变量未初始化或作用域错误
- 边界条件处理（空列表、零值、负数）
- 异常处理缺失或不完整
- 循环内的重复计算或数据库查询
- 资源泄漏风险

### 4.4 Agent B 审查要点

- 命名规范（snake_case 函数、CamelCase 类）
- 行长度不超过 120 字符
- 无尾随空格
- 函数/类有 docstring
- 验收标准：代码是否可直接合入

### 4.5 Agent C 审查要点

- 单一职责原则 (SRP)
- 开闭原则 (OCP)
- 依赖倒置原则 (DIP)
- 模块耦合度评估
- 内聚度评估

### 4.6 Agent D 审查要点

- 代码实现是否与 spec.md 描述一致
- 接口签名是否与规范定义一致
- 是否有规范已定义但代码未实现的功能
- 规范文档本身是否有歧义

---

## 5. 规则引擎规范

### 5.1 安全规则（必须全部实现）

| 规则 ID | 检测内容 | 严重度 |
|---------|---------|:---:|
| SEC-001 | 硬编码 API Key（`sk-*`, `ghp_*` 格式） | error |
| SEC-002 | 硬编码密码（`password = "..."` 模式） | error |
| SEC-003 | SQL 注入（字符串拼接/格式化构造 SQL） | error |
| SEC-004 | 命令注入（`os.system()` + 用户输入拼接） | warning |
| SEC-005 | eval() 调用 | warning |

### 5.2 风格规则（必须全部实现）

| 规则 ID | 检测内容 | 严重度 |
|---------|---------|:---:|
| STY-001 | 行长度超过 120 字符 | info |
| STY-002 | 行尾有空格或 Tab | info |

---

## 6. 汇总仲裁规范

### 6.1 去重规则

- 同文件、同行号的多个发现应合并，保留最高严重度
- severity 优先级：error > warning > info

### 6.2 排序规则

- category 优先级：security > bug > architecture > performance > spec > style
- 同类别内按 severity 排序
- 同严重度内按文件路径 + 行号排序

### 6.3 冲突检测

- 如果两个 Agent 对同一位置给出矛盾的建议，标记为 `pending_questions`
- 触发人机回环流程

---

## 7. 报告格式规范

### 7.1 输出物

每次审查必须生成以下文件：
1. `reviews/YYYY-MM-DD-HHMMSS.json` — 结构化审查报告（扁平时间戳命名）
2. `reviews/latest.json` — 始终指向最新一次审查的符号链接
3. 按需通过 `codefalcon export` 生成 `.md` Markdown 报告
4. 更新 `TODOS.md` — 新增待办事项

### 7.2 JSON 报告结构

```json
{
  "meta": {
    "timestamp": "ISO 8601 时间戳",
    "version": "版本号",
    "files_reviewed": ["文件列表"],
    "mode": "full|diff",
    "dry_run": false
  },
  "summary": {
    "total": <int>,
    "by_severity": {"error": <n>, "warning": <n>, "info": <n>},
    "by_category": {"security": <n>, "bug": <n>, "architecture": <n>, "performance": <n>, "spec": <n>, "style": <n>}
  },
  "findings": [...],
  "cost": {
    "estimated_usd": <float>,
    "total_tokens": <int>,
    "input_tokens": <int>,
    "output_tokens": <int>,
    "by_agent": {}
  }
}
```

### 7.3 Markdown 报告结构

- 标题 + 审查时间 + 文件数
- 摘要表格（按类别和严重度统计）
- 问题详情列表（编号、严重度图标、类别、位置）
- Token 消耗详情

---

## 8. TODO 管理规范

### 8.1 编号规则

- 全局自增序号：TODO-001, TODO-002, ...
- 编号跨审查会话持久化

### 8.2 去重规则

- 同文件 + 同行号 + 同类别 + 同消息 = 重复，不追加
- 已被标记为 done 的项再次出现时，不重新添加

### 8.3 归档规则

- 滚动窗口保留最新 10 次审查报告（MAX_WINDOW=10）
- 超出窗口的旧报告自动删除
- `latest.json` 始终指向最新一次审查

---

## 9. 成本控制规范

### 9.1 分级路由

| 层级 | 技术 | 单次成本 | 适用 |
|:---:|------|------|------|
| L1 | 规则引擎（正则/AST） | $0 | 确定性检查 |
| L2 | Qwen-Turbo | ~$0.00005/1K tokens | 风格检查、规范审查 |
| L3 | DeepSeek-V3 | ~$0.00014/1K tokens | Bug 检测、性能分析、架构审查 |

### 9.2 Token 追踪

- 全局单例 CostTracker 跨 Agent 累计消耗
- 每次审查结束显示总 Token 和费用
- 报告中嵌入成本明细

---

## 10. 安全要求

### 10.1 API Key 管理

- API Key 必须通过环境变量注入，不得硬编码在代码中
- `.env.example` 只能包含占位符，不得包含真实 Key
- `.env` 必须加入 `.gitignore`

### 10.2 投毒防御

- 注释投毒检测器应在审查流程第一步运行
- 检测并中和恶意注释（如隐藏的代码修改指令）

---

## 11. 测试要求

### 11.1 测试结构

```
tests/
├── test_rules.py       # 安全规则引擎测试
├── test_style.py       # 风格规则引擎测试
├── test_tools.py       # AST 分析器测试
├── test_review.py      # 汇总仲裁器测试
└── test_integration.py # 集成测试（含 mock LLM）
```

### 11.2 测试覆盖率要求

- 规则引擎：每条规则至少 1 个正向检测 + 1 个负向验证
- 汇总仲裁：去重、排序、冲突检测、空输入
- Agent：使用 monkeypatch mock LLM 调用，验证端到端流程

---

*本规范文件随 CodeFalcon 项目迭代持续更新，每次架构变更应同步更新本文档。*
