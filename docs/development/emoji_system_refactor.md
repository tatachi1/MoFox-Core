# 表情系统重构说明

日期：2025-12-15

## 目标
- 拆分单体的 `emoji_manager.py`，将实体、常量、文件工具解耦。
- 减少扫描/注册期间的事件循环阻塞。
- 保留现有行为（LLM/VLM 流程、容量替换、缓存查找），同时提升可维护性。

## 新结构
- `src/chat/emoji_system/emoji_constants.py`：共享路径与提示/数量上限。
- `src/chat/emoji_system/emoji_entities.py`：`MaiEmoji`（哈希、格式检测、入库/删除、缓存失效）。
- `src/chat/emoji_system/emoji_utils.py`：目录保证、临时清理、增量文件扫描、DB 行到实体转换。
- `src/chat/emoji_system/emoji_manager.py`：负责完整性检查、扫描、注册、VLM/LLM 描述、替换与缓存，现委托给上述模块。
- `src/chat/emoji_system/README.md`：快速使用/生命周期指引。

## 行为变化
- 完整性检查改为游标+批量增量扫描，每处理 50 个让出一次事件循环。
- 循环内的重文件操作（exists、listdir、remove、makedirs）通过 `asyncio.to_thread` 释放主循环。
- 目录扫描使用 `os.scandir`（经 `list_image_files`），减少重复 stat，并返回文件列表与是否为空。
- 快速查找：加载时重建 `_emoji_index`，增删时保持同步；`get_emoji_from_manager` 优先走索引。
- 注册与替换流程在更新索引的同时，异步清理失败/重复文件。

## 迁移提示
- 现有调用继续使用 `get_emoji_manager()` 与 `EmojiManager` API，外部接口未改动。
- 如曾直接从 `emoji_manager` 引入常量或工具，请改为从 `emoji_constants`、`emoji_entities`、`emoji_utils` 引入。
- 依赖同步文件时序的测试/脚本可能观察到不同的耗时，但逻辑等价。

## 后续建议
1. 为 `list_image_files`、`clean_unused_emojis`、完整性扫描游标行为补充单测。
2. 将 VLM/LLM 提示词模板外置为配置，便于迭代。
3. 暴露扫描耗时、清理数量、注册延迟等指标，便于观测。
4. 为 `replace_a_emoji` 的 LLM 调用添加重试上限，并记录 prompt/决策日志以便审计。
