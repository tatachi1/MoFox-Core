# 新表情系统概览

本目录存放表情包的采集、注册与选择逻辑。

## 模块
- `emoji_constants.py`：共享路径与数量上限。
- `emoji_entities.py`：`MaiEmoji` 实体，负责哈希/格式检测、数据库注册与删除。
- `emoji_utils.py`：文件系统工具（目录保证、临时清理、DB 行转换、文件列表扫描）。
- `emoji_manager.py`：核心管理器，定期扫描、完整性检查、VLM/LLM 标注、容量替换、缓存查找。
- `emoji_history.py`：按会话保存的内存历史。

## 生命周期
1. 通过 `EmojiManager.start()` 启动后台任务（或在已有事件循环中直接 await `start_periodic_check_register()`）。
2. 循环会加载数据库状态、做完整性清理、清理临时缓存，并扫描 `data/emoji` 中的新文件。
3. 新图片会生成哈希，调用 VLM/LLM 生成描述后注册入库，并移动到 `data/emoji_registed`。
4. 达到容量上限时，`replace_a_emoji()` 可能在 LLM 协助下删除低使用量表情再注册新表情。

## 关键行为
- 完整性检查增量扫描，批量让出事件循环避免长阻塞。
- 循环内的文件操作使用 `asyncio.to_thread` 以保持事件循环可响应。
- 哈希索引 `_emoji_index` 加速内存查找；数据库为事实来源，内存为镜像。
- 描述与标签使用缓存（见管理器上的 `@cached`）。

## 常用操作
- `get_emoji_for_text(text_emotion)`：按目标情绪选取表情路径与描述。
- `record_usage(emoji_hash)`：累加使用次数。
- `delete_emoji(emoji_hash)`：删除文件与数据库记录并清缓存。

## 目录
- 待注册：`data/emoji`
- 已注册：`data/emoji_registed`
- 临时图片：`data/image`, `data/images`

## 说明
- 通过 `config/bot_config.toml`、`config/model_config.toml` 配置上限与模型。
- GIF 支持保留，注册前会提取关键帧再送 VLM。
- 避免直接使用 `Session`，请使用本模块提供的 API。
