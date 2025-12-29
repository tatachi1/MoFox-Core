# 基础用法示例（Memory Graph）

> 快速创建、检索与关系建立。

## 创建与检索
```python
from src.memory_graph.manager_singleton import get_memory_manager

manager = await get_memory_manager()

# 创建记忆
memory = await manager.create_memory(
    subject="用户",
    memory_type="偏好",
    topic="喜欢晴天",
    importance=0.7
)

# 搜索
memories = await manager.search_memories(query="天气", top_k=5)
```

## 节点与关系
```python
user_node = await manager.create_node(node_type="person", label="小王")
friend_node = await manager.create_node(node_type="person", label="小李")

await manager.create_edge(
    source_id=user_node.id,
    target_id=friend_node.id,
    relation_type="knows",
    weight=0.9
)
```

## 调度器集成（简例）
```python
from src.schedule.unified_scheduler import unified_scheduler, TriggerType

async def register_tasks():
    await unified_scheduler.create_schedule(
        callback=run_memory_consolidation,
        trigger_type=TriggerType.TIME,
        trigger_config={"delay_seconds": 6 * 3600},
        is_recurring=True,
        task_name="periodic_memory_consolidation"
    )
```

更多：见 [memory_graph_README.md](../memory_graph_README.md) 与 [long_term_manager_optimization_summary.md](../long_term_manager_optimization_summary.md)。
