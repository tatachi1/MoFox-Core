# 高级场景示例（Memory Graph）

> 因果链、引用关系、混合检索与批量操作。

## 因果链与引用关系
```python
# 创建两条记忆
await manager.create_memory(subject="我", memory_type="事实", topic="情绪", object="不开心", attributes={"时间": "今天"})
await manager.create_memory(subject="我", memory_type="事件", topic="摔东西", attributes={"时间": "今天"})

# 建立因果关系
await manager.link_memories(
    source_memory_description="我今天不开心",
    target_memory_description="我摔东西",
    relation_type="导致"
)

# 引用关系
await manager.link_memories(
    source_memory_description="小明考试满分",
    target_memory_description="我怀疑真实性",
    relation_type="基于"
)
```

## 混合检索（向量 + 图遍历）
```python
results = await manager.search_memories(
    query="和小明有关的记忆",
    memory_types=["事件", "事实", "关系"],
    max_results=10,
    expand_depth=1
)
```

## 批量操作（建议）
- 使用数据库 API 的 `QueryBuilder` 进行分页与过滤。
- 使用 `AdaptiveBatchScheduler` 批量插入/更新，避免逐条写入。

参考：
- [tool_calling_guide.md](../tool_calling_guide.md)
- [long_term_manager_optimization_summary.md](../long_term_manager_optimization_summary.md#实践示例新增)
