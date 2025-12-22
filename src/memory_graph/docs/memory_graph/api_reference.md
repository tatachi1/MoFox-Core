# Memory Graph API Reference (v0.2)

> 更新于 2025-12-22 — 与六层数据库架构、统一调度器对齐。

## 概览
- 核心模块：节点/边/记忆数据模型，管理器操作（创建/检索/整理），LLM 工具接口。
- 依赖约定：数据库访问走 `CRUDBase`/`QueryBuilder`；批量操作用 `AdaptiveBatchScheduler`；避免直接 `Session`。
- 运行建议：自动/批量任务通过统一调度器后台化；事件中仅进行轻量操作。

## 数据模型
- 枚举：`NodeType`、`MemoryType`、`EdgeType`。
- 数据类：`MemoryNode`、`MemoryEdge`、`Memory`。
- 存放位置：参考 [src/memory_graph/models.py](../../../src/memory_graph/models.py)。

### 字段摘要
- `MemoryNode`: `id`, `content`, `node_type`, `embedding?`, `metadata`, `created_at`
- `MemoryEdge`: `id`, `source_id`, `target_id`, `relation`, `edge_type`, `importance`, `metadata`, `created_at`
- `Memory`: `id`, `subject_id`, `memory_type`, `nodes[]`, `edges[]`, `importance`, `created_at`, `last_accessed`, `access_count`, `decay_factor`

## 管理器 API
- 统一入口：[src/memory_graph/unified_manager.py](../../../src/memory_graph/unified_manager.py)
- 记忆图入口：[src/memory_graph/manager.py](../../../src/memory_graph/manager.py)

### UnifiedMemoryManager
- `initialize()` / `shutdown()`
- `add_message(message: dict)`
- `search_memories(query_text: str, use_judge: bool = True, recent_chat_history: str = "")`
- `manual_transfer()`

详见 [unified_memory_manager.md](unified_memory_manager.md#使用示例)。

### MemoryManager（示例）
- `create_memory(subject, memory_type, topic, object? = None, attributes? = None, importance? = 0.5)`
- `search_memories(query: str, top_k: int = 10)`
- `create_node(node_type: str, label: str)` / `create_edge(source_id, target_id, relation_type, weight?)`

参考 [memory_graph_README.md](memory_graph_README.md#方案-b-记忆图系统-高级用户)。

## LLM 工具接口
- `create_memory(subject, memory_type, topic, object?, attributes?, importance?)`
- `link_memories(source_memory_description, target_memory_description, relation_type, importance?)`
- `search_memories(query, memory_types?, time_range?, max_results?, expand_depth?)`

完整示例见 [tool_calling_guide.md](tool_calling_guide.md)。

## 数据库 API 与批量操作
- 查询：使用 `QueryBuilder` 链式过滤与分页；减少频繁小查询。
- 写入：使用 `AdaptiveBatchScheduler` 批量插入/更新；避免逐条循环。
- 缓存：结合 L1/L2/L3 缓存；热点主体与最近活跃记忆优先缓存/预加载。

进一步说明见 [long_term_manager_optimization_summary.md](long_term_manager_optimization_summary.md#数据库-api-与优化层使用建议新增)。

## 调度与事件
- 统一调度器：TIME/事件双触发，用于整理/嵌入刷新/衰减等后台任务。
- 事件系统：在 `ON_MESSAGE_RECEIVED` 等事件中进行轻量处理（入临时池/标记）。

示例见：
- [unified_memory_manager.md](unified_memory_manager.md#与统一调度器集成新增)
- [memory_graph_README.md](memory_graph_README.md#🔧-实践示例新增)

## 权限与审计
- 权限节点：`plugin.memory_graph.admin`（批量清理/导出/合并等敏感操作）。
- 审计日志：结构化日志记录批量大小、耗时、缓存命中率与错误明细（见 logs/）。

## 监控指标
- 处理速度、平均延迟、内存使用、批处理大小、缓存命中率。
- 采集建议：定期导出或接入监控系统，详见各文档的监控章节。

## 参考与导航
- [design_outline.md](design_outline.md)
- [memory_graph_README.md](memory_graph_README.md)
- [long_term_manager_optimization_summary.md](long_term_manager_optimization_summary.md)
- [unified_memory_manager.md](unified_memory_manager.md)
