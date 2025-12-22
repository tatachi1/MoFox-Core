# 统一记忆管理器使用说明

> 适用于三层记忆（感知 / 短期 / 长期）的统一调度与检索。

## 定位与职责
- 入口：统一封装在 [src/memory_graph/unified_manager.py](src/memory_graph/unified_manager.py)，负责三层记忆的初始化、检索、转移与统计。
- 目标：对上层调用者隐藏各层实现细节，提供一致的 `initialize → add_message → search_memories → shutdown` 生命周期。
- 协作组件：
  - 感知层：`PerceptualMemoryManager`（消息块缓冲/激活检测）
  - 短期层：`ShortTermMemoryManager`（结构化、重要性评估）
  - 长期层：`LongTermMemoryManager`（持久化、语义检索、批量转移）

## 初始化与配置
调用 `UnifiedMemoryManager()` 时可覆盖的关键参数（参见文件内的默认值）：
- 感知层：`perceptual_max_blocks`、`perceptual_block_size`、`perceptual_activation_threshold`、`perceptual_recall_top_k`、`perceptual_recall_threshold`
- 短期层：`short_term_max_memories`、`short_term_transfer_threshold`、`short_term_overflow_strategy`、`short_term_enable_force_cleanup`、`short_term_cleanup_keep_ratio`
- 长期层：`long_term_batch_size`、`long_term_search_top_k`、`long_term_decay_factor`、`long_term_auto_transfer_interval`
- 智能裁判：`judge_confidence_threshold`（低于阈值时倾向触发长期检索）

### 生命周期钩子
- `initialize()`：创建/初始化三层管理器和底层 `MemoryManager`，并启动自动转移任务。
- `shutdown()`：取消后台任务，依次关闭各层管理器和底层存储。

## 核心调用流程
### 1) 写入路径
- `add_message(message: dict)`: 将新消息追加到感知层。感知→短期的转移不在这里发生，由检索阶段触发。

### 2) 检索路径
- `search_memories(query_text, use_judge=True, recent_chat_history="")`：主入口。流程概览：
  1. 并行检索感知块与短期记忆。
  2. 对感知块进行一次性扫描，标记 `needs_transfer` 的块并在后台转移至短期层。
  3. 召回结果送入“记忆判官”模型：
     - 若判定不足，生成补充 query，触发长期检索（多查询加权）。
     - 若判定充足，直接返回感知/短期结果。
  4. 最终输出包括三层记忆列表与裁判决策。

### 3) 长期检索细节
- `_build_manual_multi_queries()`：对裁判生成的补充查询去重并分配递减权重。
- `_retrieve_long_term_memories()`：根据基础 query 与补充 query 触发多查询搜索，可附带近期聊天上下文以优化召回。
- `_deduplicate_memories()`：根据 `memory.id` 去重，兼容 dict/object 结果。

## 自动与后台任务
- 感知→短期转移：
  - `_schedule_perceptual_block_transfer()`：在后台并行处理多个块，转移成功后触发唤醒事件。
  - `_transfer_blocks_to_short_term()`：转移成功后删除感知块，避免重复处理。
- 自动转移循环：
  - `_auto_transfer_loop()`：短期层满额时整批转移到长期层；等待间隔由 `_calculate_auto_sleep_interval()` 按占用率自适应调节。
  - 支持手动触发 `manual_transfer()`，用于调试或异常兜底。

## 统计与观测
- `get_statistics()`：返回三层统计以及总计数（感知消息量 + 短期记忆量 + 长期记忆量）。
- 日志：所有后台任务均附带异常回调，便于在日志中定位失败原因。

## 失败与兜底策略
- 裁判模型失败时默认判定“需要检索长期记忆”，降低漏检风险。
- 自动转移任务异常会被捕获记录，不会阻塞主流程；取消时吞掉 `CancelledError`。

## 使用示例
```python
from src.memory_graph.unified_manager import UnifiedMemoryManager

mgr = UnifiedMemoryManager()
await mgr.initialize()

# 写入消息
await mgr.add_message({"content": "我今天跑了5公里", "sender_id": "user_1"})

# 智能检索（含裁判与长期补充检索）
result = await mgr.search_memories(
    query_text="用户的运动记录",
    use_judge=True,
    recent_chat_history="昨天聊了跑步计划",
)

# 手动转移（需要短期层已满才会执行）
await mgr.manual_transfer()

# 关闭
await mgr.shutdown()
```

## 调试建议
- 若短期层迟迟不转移，检查 `short_term_max_memories` 与当前占用是否已达上限。
- 若长期检索无结果，确认裁判模型配置和补充 query 是否命中目标实体；必要时可将 `use_judge=False` 直接走长期检索。
- 调整 `long_term_auto_transfer_interval` 和 `_calculate_auto_sleep_interval()` 可平衡延迟与资源消耗。
