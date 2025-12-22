# LLM 工具调用指南（Memory Graph）

> 更新于 2025-12-22 — 提供 `create_memory`、`link_memories`、`search_memories` 的参数与示例。

## 设计原则
- 参数简洁明了，结构化清晰，类型明确，容错性强，可组合性。
- 时间标准化，主体明确，复杂句子拆分+关联，转述标注来源，合理设定重要性。

## 工具定义摘要
- `create_memory(subject, memory_type, topic, object?, attributes?, importance?)`
- `link_memories(source_memory_description, target_memory_description, relation_type, importance?)`
- `search_memories(query, memory_types?, time_range?, max_results?, expand_depth?)`

完整 JSON Schema 参考 [design_outline.md](design_outline.md#附录-a-工具定义完整json-schema)。

## 示例

### 示例 1：简单事件
```json
{
  "subject": "我",
  "memory_type": "事件",
  "topic": "吃饭",
  "object": "白米饭",
  "attributes": {"时间": "今天"},
  "importance": 0.3
}
```

### 示例 2：事实状态
```json
{
  "subject": "小明",
  "memory_type": "事实",
  "topic": "喜好",
  "object": "打篮球",
  "importance": 0.5
}
```

### 示例 3：复杂观点 + 关联
```json
// 第一步：创建两条记忆
create_memory({subject: "我", memory_type: "事实", topic: "情绪", object: "不开心", attributes: {时间: "今天"}})
create_memory({subject: "我", memory_type: "事件", topic: "摔东西", attributes: {时间: "今天"}})

// 第二步：建立因果关系
link_memories({
  source_memory_description: "我今天不开心",
  target_memory_description: "我摔东西",
  relation_type: "导致"
})
```

### 示例 4：检索（语义 + 图扩展）
```json
{
  "query": "我为什么今天不开心？",
  "memory_types": ["事件", "事实"],
  "max_results": 10,
  "expand_depth": 1
}
```

## 使用建议
- 快速入库：工具调用先保存到临时池（staged），后台批量整理。
- 混合检索：向量初筛 + 图遍历扩展；`expand_depth` 按问题复杂度选择。
- 安全与权限：敏感操作需管理员/Master 权限；记录结构化日志。

更多示例与细节：
- [long_term_manager_optimization_summary.md](long_term_manager_optimization_summary.md#实践示例新增)
- [memory_graph_README.md](memory_graph_README.md#🔧-实践示例新增)

---

## 日志字段与观测清单（详细）

为保证工具调用的可观测性与可审计性，建议所有调用按以下字段记录结构化日志（JSONL）。日志器参见 [src/common/logger.py](../../../src/common/logger.py)。

### 全局字段（每条日志均应包含）
- `timestamp`: ISO 时间戳（UTC），例如 `2025-12-22T12:34:56.789Z`
- `module`: 固定模块名，例如 `memory_graph.tool_call`
- `tool_name`: `create_memory` | `link_memories` | `search_memories`
- `version`: 工具/模块版本，例如 `v0.2`
- `env`: 运行环境标签，例如 `dev` | `staging` | `prod`
- `request_id`: 本次调用的唯一 ID（UUID）
- `session_id`: 会话 ID（可与聊天上下文绑定）
- `user_id`: 用户标识（建议散列/脱敏存储，如 `hash(user_id)`）
- `correlation_id`: 跨模块关联 ID（事件/调度器任务/后续批处理）
- `permission_group`: 权限组，例如 `USER` | `ADMIN` | `MASTER`

### 请求字段（输入侧）
- `params_subject`: 主体（已标准化，例如 `用户`/`我`→`user`）
- `params_memory_type`: 事件/事实/关系/观点
- `params_topic`: 主题文本（必要时截断）
- `params_object`: 客体文本（可选，必要时截断）
- `params_attributes`: 归一化后的属性字典（`时间`、`地点`、`原因`等）
- `params_importance`: 重要性数值（0-1）
- `params_query`: 检索查询（用于 `search_memories`）
- `params_filters`: 类型/时间范围等过滤条件（用于检索）
- `params_expand_depth`: 图扩展深度（检索增强）
- `payload_size`: 原始参数大小（字符数/字节数）

### 过程字段（中间信息）
- `time_normalized`: 时间标准化结果（如 `今天`→`2025-12-22`）
- `judge_used`: 是否使用裁判/查询规划器（布尔）
- `vector_ops`: 向量检索操作计数/耗时（ms）
- `graph_ops`: 图遍历操作计数/耗时（ms）
- `db_reads`: 数据库读取次数/耗时（ms）
- `db_writes`: 数据库写入次数/耗时（ms）
- `cache_hit_rate`: L1/L2/L3 命中率（0-1）
- `scheduler_trigger`: 是否由统一调度器触发以及触发类型（`TIME`/`EVENT`）

### 结果字段（输出侧）
- `success`: 布尔值
- `error_code`: 统一错误码（见“解决方案”）
- `error_message`: 错误消息（安全脱敏）
- `retry_count`: 重试次数（如有）
- `latency_ms`: 总耗时（毫秒）
- `memories_returned`: 返回的记忆条数（检索）
- `memory_ids`: 涉及的记忆 ID 列表（创建/关联/检索）
- `nodes_created_count`: 新建节点数量（创建）
- `edges_created_count`: 新建边数量（创建/关联）
- `importance_effective`: 生效的重要性（考虑规则/修正后）

### 隐私与脱敏
- 对 `user_id`、`session_id` 可进行散列；对自由文本（`topic`/`object`）建议截断到安全长度并过滤潜在敏感词。
- `error_message` 需脱敏（去除 PII/密钥），保留必要上下文以便排障。

### 示例（JSON）
```json
{
  "timestamp": "2025-12-22T12:34:56.789Z",
  "module": "memory_graph.tool_call",
  "tool_name": "create_memory",
  "version": "v0.2",
  "env": "prod",
  "request_id": "8f1b5a0b-6f1a-4c5a-9a12-3c2c8e0e1234",
  "session_id": "s_abc123",
  "user_id": "hash_u_123456",
  "correlation_id": "corr_20251222_001",
  "permission_group": "USER",
  "params_subject": "user",
  "params_memory_type": "事件",
  "params_topic": "吃饭",
  "params_object": "白米饭",
  "params_attributes": {"时间": "2025-12-22"},
  "params_importance": 0.3,
  "time_normalized": true,
  "vector_ops": {"count": 0, "latency_ms": 0},
  "graph_ops": {"count": 0, "latency_ms": 0},
  "db_reads": {"count": 1, "latency_ms": 5},
  "db_writes": {"count": 1, "latency_ms": 12},
  "cache_hit_rate": 0.0,
  "scheduler_trigger": {"used": false},
  "success": true,
  "error_code": null,
  "error_message": null,
  "retry_count": 0,
  "latency_ms": 24,
  "memories_returned": 0,
  "memory_ids": ["mem_9b7f..."],
  "nodes_created_count": 3,
  "edges_created_count": 2,
  "importance_effective": 0.3
}
```

### 解决方案建议（落地）
1. 统一日志器使用：在工具执行器中通过项目日志器记录 `info`/`error`，使用上述字段作为 `extra`；按 JSONL 输出至 `logs/app_*.jsonl`。
2. 错误码规范：
  - `E_PARAM_VALIDATION`（参数校验失败）
  - `E_PERMISSION_DENIED`（权限不足）
  - `E_DB_IO`（数据库读写异常）
  - `E_VECTOR_SERVICE`（向量服务异常）
  - `E_GRAPH_INDEX`（图索引异常）
  - `E_TIMEOUT`（超时）
3. 重试与兜底：
  - 参数校验失败直接返回，不重试；
  - 可重试错误（网络/服务）按退避策略重试最多 2 次；
  - 写入失败时将记录保存至“临时池（staged）”以备后台整理与补写。
4. 采样与压缩：
  - 高流量场景对 `search_memories` 日志进行采样（例如 30%），但错误与慢调用（`latency_ms > 2000`）强制记录；
  - 对长文本字段进行截断（如 256 字符），保留摘要以便统计。
5. 监控集成：
  - 周期性汇总处理速度、平均延迟、缓存命中率、失败率；
  - 将慢查询与高错误率按 correlation_id 关联至统一调度器的后台任务，形成端到端追踪。
6. 隐私与合规：
  - 对用户标识做散列；移除 PII；保留必要的上下文键；
  - 日志保留期与访问控制遵循仓库隐私策略（见 [PRIVACY.md](../../../PRIVACY.md)）。

### 代码片段（Python）
```python
from src.common.logger import get_logger

logger = get_logger("memory_graph.tool_call")

def log_tool_call(payload: dict, result: dict | None, error: Exception | None = None):
   base = {
      "module": "memory_graph.tool_call",
      "version": "v0.2",
      # ... 补充 request_id/session_id/user_id 等
   }
   if error:
      logger.error("tool_call_error", extra={**base, **payload, "error_code": "E_DB_IO", "error_message": str(error)[:256]})
   else:
      logger.info("tool_call_ok", extra={**base, **payload, **(result or {}), "success": True})
```
