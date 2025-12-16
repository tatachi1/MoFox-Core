# StyleLearner 资源上限开关（默认开启）

## 概览
StyleLearner 支持资源上限控制，用于约束风格容量与清理行为。开关默认 **开启**，以防止模型无限膨胀；可在运行时动态关闭。

## 开关位置与用法（务必看这里）

开关在 **代码层**，默认开启，不依赖配置文件。

1) **全局运行时切换（推荐）**  
  路径：`src/chat/express/style_learner.py` 暴露的单例 `style_learner_manager`  
  ```python
  from src.chat.express.style_learner import style_learner_manager

  # 关闭资源上限（放开容量，谨慎使用）
  style_learner_manager.set_resource_limit(False)

  # 再次开启资源上限
  style_learner_manager.set_resource_limit(True)
  ```
  - 影响范围：实时作用于已创建的全部 learner（逐个同步 `resource_limit_enabled`）。
  - 生效时机：调用后立即生效，无需重启。

2) **构造时指定（不常用）**  
  - `StyleLearner(resource_limit_enabled: True|False, ...)`  
  - `StyleLearnerManager(resource_limit_enabled: True|False, ...)`  
  用于自定义实例化逻辑（通常保持默认即可）。

3) **默认行为**  
  - 开关默认 **开启**，即启用容量管理与清理。
  - 没有配置文件项；若需持久化开关状态，可自行在启动代码中显式调用 `set_resource_limit`。

## 资源上限行为（开启时）
- 容量参数（每个 chat）：
  - `max_styles = 2000`
  - `cleanup_threshold = 0.9`（≥90% 容量触发清理）
  - `cleanup_ratio = 0.2`（清理低价值风格约 20%）
- 价值评分：结合使用频率（log 平滑）与最近使用时间（指数衰减），得分低者优先清理。
- 仅对单个 learner 的容量管理生效；LRU 淘汰逻辑保持不变。

> ⚙️ 开关作用面：
> - **开启**：在 add_style 时会检查容量并触发 `_cleanup_styles`；预测/学习逻辑不变。
> - **关闭**：不再触发容量清理，但 LRU 管理器仍可能在进程层面淘汰不活跃 learner。

## I/O 与健壮性
- 模型与元数据保存采用原子写（`.tmp` + `os.replace`），避免部分写入。
- `pickle` 使用 `HIGHEST_PROTOCOL`，并执行 `fsync` 确保落盘。

## 兼容性
- 默认开启，无需修改配置文件；关闭后行为与旧版本类似。
- 已有模型文件可直接加载，开关仅影响运行时清理策略。

## 何时建议开启/关闭
- 开启（默认）：内存/磁盘受限，或聊天风格高频增长，需防止模型膨胀。
- 关闭：需要完整保留所有历史风格且资源充足，或进行一次性数据收集实验。

## 监控与调优建议
- 监控：每 chat 风格数量、清理触发次数、删除数量、预测延迟 p95。
- 如清理过于激进：提高 `cleanup_threshold` 或降低 `cleanup_ratio`。
- 如内存/磁盘依旧偏高：降低 `max_styles`，或增加定期持久化与压缩策略。
