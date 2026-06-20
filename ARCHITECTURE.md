# CodeFalcon 架构设计文档

## 一、设计哲学

### 核心原则

1. **规则+Agent混合决策**：确定性检查0成本，复杂推理按需调用LLM
2. **多Agent并行协作**：维度独立则并行，有依赖则串行
3. **分级成本控制**：规则引擎 → Qwen → DeepSeek-V3 三级路由
4. **人机协作回环**：Agent判断不了的交给人，人的决策反哺Agent

### 为什么选LangGraph而不是CrewAI/AutoGen？

CodeFalcon是一个**多阶段流水线**而非自由对话式协作。LangGraph的StateGraph+条件路由天然适合：
- 明确定义的状态流转（State Schema）
- 条件分支（遇到复杂问题→人机回环）
- 并行节点（规则引擎完成后 Agent A 和 Agent B 同时执行）
- 内置Human-in-the-loop支持（interrupt机制）

## 二、审查流程

### 完整状态流转

```
START
  │
  ▼
context_collection   ← 读取文件、收集相关代码段、构建调用图
  │
  ▼
rule_engine          ← 正则扫描安全/风格问题（同步，0成本）
  │
  ├──→ agent_a       ← Bug检测 + 性能分析（异步，DeepSeek-V3）
  │
  └──→ agent_b       ← 风格检查 + 验收（异步，Qwen）
  │
  ├──→ aggregate     ← 去重、排序、冲突检测（等待A和B都完成）
  │
  ▼
route_after_aggregate
  │
  ├── 有待确认问题 → human_interrupt → generate_output
  │
  └── 无待确认问题 → generate_output
  │
  ▼
END
```

### Agent通信模式

Agent A 和 Agent B 之间不需要直接通信。采用 **交接文档（Handover Document）** 模式：

1. Agent A 完成审查后，在 state 中写入"给Agent B的交接文档"
2. Agent B 启动时读取交接文档，作为审查的额外上下文
3. 汇总仲裁层负责去重和冲突检测

这种模式模拟真实团队中的"文档交接"，Agent间解耦，各自独立可替换。

## 三、成本控制策略

### 三级路由

| 任务类型 | 使用模型 | 成本 | 示例 |
|---------|---------|------|------|
| 确定性检查 | 规则引擎（正则/AST） | $0 | 硬编码密钥、SQL注入、尾随空格 |
| 简单推理 | Qwen-Turbo | ~$0.00005/1K tokens | 命名规范、基础风格 |
| 复杂推理 | DeepSeek-V3 | ~$0.00014/1K tokens | 跨文件逻辑Bug、性能设计 |

### 上下文优化

- **增量diff分析**：仅提取变更代码，非全量传输
- **Agent主动检索**：Agent通过工具调用搜索相关代码，而非预先全量传入
- **Token预算限制**：每次审查设置Token上限，超出则截断并有日志记录

## 四、记忆与检索

### MVP阶段

基于AST构建函数调用图索引，覆盖90%的关联代码检索需求：
- 函数定义查询
- 调用者分析
- 调用关系图

### 扩展方向

预留FAISS语义检索接口：
- 语义级代码片段搜索
- 相似问题模式匹配
- 历史审查记录关联

## 五、扩展性设计

1. **Agent可插拔**：通过BaseAgent基类统一接口，可新增Agent维度
2. **规则可配置**：SecurityRuleEngine支持新增检测模式
3. **模型可替换**：Config中配置API，支持切换不同LLM提供商
4. **输出可定制**：Reporter支持自定义模板
