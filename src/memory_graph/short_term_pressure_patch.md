# 短期记忆压力泄压补丁

## 📋 概述

在高频消息场景下，短期记忆层（`ShortTermMemoryManager`）可能在自动转移机制触发前快速堆积大量记忆，当达到容量上限（`max_memories`）时可能阻塞后续写入。本功能提供一个**可选的泄压开关**，在容量溢出时自动删除低优先级记忆，防止系统阻塞。

**关键特性**：
- ✅ 默认关闭，保持向后兼容
- ✅ 基于重要性和时间的智能删除策略
- ✅ 异步持久化，不阻塞主流程
- ✅ 可通过配置文件或代码控制

---

## 🔧 配置方法

### 方法 1：代码配置（直接创建管理器）

如果您在代码中直接实例化 `UnifiedMemoryManager`：

```python
from src.memory_graph.unified_manager import UnifiedMemoryManager

manager = UnifiedMemoryManager(
    short_term_enable_force_cleanup=True,  # 开启泄压功能
    short_term_max_memories=30,            # 短期记忆容量上限
    # ... 其他参数
)
```

### 方法 2：配置文件（通过单例获取）

**推荐方式**：如果您使用 `get_unified_memory_manager()` 单例，需修改配置文件。

#### ❌ 目前的问题
配置文件 `config/bot_config.toml` 的 `[memory]` 节**尚未包含**此开关参数。

#### ✅ 解决方案
在 `config/bot_config.toml` 的 `[memory]` 节添加：

```toml
[memory]
# ... 其他配置 ...
short_term_max_memories = 30           # 短期记忆容量上限
short_term_transfer_threshold = 0.6    # 转移到长期记忆的重要性阈值
short_term_enable_force_cleanup = true  # 开启压力泄压（建议高频场景开启）
```

然后在 `src/memory_graph/manager_singleton.py` 第 157-175 行的 `get_unified_memory_manager()` 函数中添加读取逻辑：

```python
_unified_memory_manager = UnifiedMemoryManager(
    # ... 其他参数 ...
    short_term_enable_force_cleanup=getattr(config, "short_term_enable_force_cleanup", False),  # 添加此行
)
```

---

## ⚙️ 核心实现位置

### 1. 参数定义
**文件**：`src/memory_graph/unified_manager.py` 第 47 行
```python
class UnifiedMemoryManager:
    def __init__(
        self,
        short_term_enable_force_cleanup: bool = False,  # 开关参数
    ):
```

### 2. 传递到短期层
**文件**：`src/memory_graph/unified_manager.py` 第 100 行
```python
"short_term": {
    "enable_force_cleanup": short_term_enable_force_cleanup,  # 传递给 ShortTermMemoryManager
}
```

### 3. 泄压逻辑实现
**文件**：`src/memory_graph/short_term_manager.py` 第 693-726 行
```python
def force_cleanup_overflow(self, keep_ratio: float = 0.9) -> int:
    """当短期记忆超过容量时，强制删除低重要性且最早的记忆以泄压"""
    if not self.enable_force_cleanup:  # 检查开关
        return 0
    # ... 删除逻辑
```

### 4. 触发条件
**文件**：`src/memory_graph/unified_manager.py` 第 618-621 行
```python
# 在自动转移循环中检测
if occupancy_ratio >= 1.0 and not transfer_cache:
    removed = self.short_term_manager.force_cleanup_overflow()
    if removed > 0:
        logger.warning(f"短期记忆占用率 {occupancy_ratio:.0%}，已强制删除 {removed} 条低重要性记忆泄压")
```

---

## 🔄 运行机制

### 触发条件（同时满足）
1. ✅ 开关已开启（`enable_force_cleanup=True`）
2. ✅ 短期记忆占用率 ≥ 100%（`len(memories) >= max_memories`）
3. ✅ 当前没有待转移批次（`transfer_cache` 为空）

### 删除策略
**排序规则**：双重排序，先按重要性升序，再按创建时间升序
```python
sorted_memories = sorted(self.memories, key=lambda m: (m.importance, m.created_at))
```

**删除数量**：删除到容量的 90%
```python
current = len(self.memories)  # 当前记忆数
limit = int(self.max_memories * 0.9)  # 目标保留数
remove_count = current - limit  # 需要删除的数量
```

**示例**：
- 容量上限 `max_memories=30`
- 当前记忆数 `35` → 删除 `35 - 27 = 8` 条最低优先级记忆
- 优先删除：重要性 0.1 且创建于 10 分钟前的记忆

### 持久化
- 使用 `asyncio.create_task(self._save_to_disk())` 异步保存
- **不阻塞**消息处理主流程

---

## 📊 性能影响

| 场景 | 开关状态 | 行为 | 适用场景 |
|------|---------|------|---------|
| 高频消息 | ✅ 开启 | 自动泄压，防止阻塞 | 群聊、客服场景 |
| 低频消息 | ❌ 关闭 | 仅依赖自动转移 | 私聊、低活跃群 |
| 调试阶段 | ❌ 关闭 | 便于观察记忆堆积 | 开发测试 |

**日志示例**（开启后）：
```
[WARNING] 短期记忆压力泄压: 移除 8 条 (当前 27/30)
[WARNING] 短期记忆占用率 100%，已强制删除 8 条低重要性记忆泄压
```

---

## 🚨 注意事项

### ⚠️ 何时开启
- ✅ **推荐开启**：高频群聊、客服机器人、24/7 运行场景
- ❌ **不建议开启**：需要完整保留所有短期记忆、调试阶段

### ⚠️ 潜在影响
- 低重要性记忆可能被删除，**不会转移到长期记忆**
- 如需保留所有记忆，应调大 `max_memories` 或关闭此功能

### ⚠️ 与自动转移的协同
本功能是**兜底机制**，正常情况下：
1. 优先触发自动转移（占用率 ≥ 50%）
2. 高重要性记忆转移到长期层
3. 仅当转移来不及时，泄压才会触发

---

## 🔙 回滚与禁用

### 临时禁用（无需重启）
```python
# 运行时修改（如果您能访问管理器实例）
unified_manager.short_term_manager.enable_force_cleanup = False
```

### 永久禁用
**配置文件方式**：
```toml
[memory]
short_term_enable_force_cleanup = false  # 或直接删除此行
```

**代码方式**：
```python
manager = UnifiedMemoryManager(
    short_term_enable_force_cleanup=False,  # 显式关闭
)
```

---

## 📚 相关文档

- [三层记忆系统用户指南](../../docs/three_tier_memory_user_guide.md)
- [记忆图谱架构](../../docs/memory_graph_guide.md)
- [统一调度器指南](../../docs/unified_scheduler_guide.md)

---

**最后更新**：2025年12月16日
