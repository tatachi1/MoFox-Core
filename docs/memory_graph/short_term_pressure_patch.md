# 短期记忆压力泄压补丁（弃用）

## 背景

部分场景下，短期记忆层在自动转移尚未触发时会快速堆积，可能导致短期记忆达到容量上限并阻塞后续写入。

## 变更（补丁）

- 新增“压力泄压”开关：可选择在占用率达到 100% 时，删除低重要性且最早的短期记忆，防止短期层持续膨胀。
- 默认关闭，需显式开启后才会执行自动删除。

## 开关配置

- 入口：`UnifiedMemoryManager` 构造参数
  - `short_term_enable_force_cleanup: bool = False`
- 传递到短期层：`ShortTermMemoryManager(enable_force_cleanup=True)`
- 关闭示例：
  ```python
  manager = UnifiedMemoryManager(
      short_term_enable_force_cleanup=False,
  )
  ```

## 行为说明

- 当短期记忆占用率达到或超过 100%，且当前没有待转移批次时：
  - 触发 `force_cleanup_overflow()`
  - 按“低重要性优先、创建时间最早优先”删除一批记忆，将容量压回约 `max_memories * 0.9`
- 清理在后台持久化，不阻塞主流程。

## 影响范围

- 默认行为保持与补丁前一致（开关默认 `off`）。
- 如果关闭开关，短期层将不再做强制删除，只依赖自动转移机制。

## 回滚

- 构造时将 `short_term_enable_force_cleanup=False` 即可关闭；无需代码回滚。
