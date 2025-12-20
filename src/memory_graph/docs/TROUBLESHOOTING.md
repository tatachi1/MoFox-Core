# 记忆系统故障排查指南 (MoFox-Core)

本文面向三层记忆系统（感知/短期/长期）在本仓库中的实现，汇总常见症状、定位方法与修复建议，优先提供“快速可落地”的排查步骤。若你处在生产运行中，建议先将日志级别调至调试，并保留最近一次完整日志用于回溯。

---

## 0. 快速自检清单（先做这些）

- 依赖安装
  - Python: 建议 3.10+（当前环境输出以此为准）
  - 关键依赖：networkx、json-repair、numpy、chromadb、faiss-cpu（如启用 Graph/向量存储）
  - 安装示例：
    ```powershell
    cd c:\MoFox-Core
    python -m pip install -r requirements.txt
    ```
- 配置与环境
  - .env: `EULA_CONFIRMED=true`
  - 配置：启用记忆系统（bot_config / model_config）
  - 路径：数据目录默认在 `data/memory_graph`
- 日志
  - 打开调试日志：在配置中将日志级别设为 debug；排查时关注 src.memory_graph.* 模块的日志

---

## 1. 症状：短期记忆“没有新建”或“检索不到”

- 典型现象
  - 调用 `add_from_block()` 后返回为 None，或数量没变
  - 刚创建的短期记忆无法通过 `search_memories()` 检索到

- 常见原因与定位
  - LLM 响应 JSON 解析失败
    - 位置：`ShortTermMemoryManager._parse_json_response()`
    - 表现：日志出现 “JSON 解析失败”/“LLM 响应解析失败”，随后跳过创建
  - 决策操作字段不规范
    - 位置：`_decide_memory_operation()`，LLM 返回如 `create-new`/大小写变体
    - 若未规范化会误判为未知操作
  - MERGE/UPDATE 目标不存在时的“回退创建”未刷新向量缓存
    - 位置：`_execute_decision()`，需要调用 `_invalidate_matrix_cache()`
    - 不刷新会导致检索短期内看不到新记忆
  - 向量生成器未初始化或生成失败
    - 位置：`_generate_embedding()`；若返回 None，后续相似度/检索为空

- 解决方案（已在代码中增强）
  - JSON 解析：兼容无语言的代码块，扩大异常捕获到 Exception
  - 操作名：统一 `strip().lower().replace('-', '_')`，枚举失败回退 `CREATE_NEW`
  - 回退创建：MERGE/UPDATE 的目标缺失与“未知操作默认创建”均调用 `_invalidate_matrix_cache()`
  - 快速验证（建议写一段最小脚本验证创建+检索链路）

---

## 2. 症状：短期 → 长期“没有转移”或“转移不完整”

- 机制说明（当前策略）
  - 自动转移：仅当短期记忆“满额”时，整批转移全部短期记忆（简化策略）
  - 手动转移：`UnifiedMemoryManager.manual_transfer()` 也在“未满”时返回不转移
  - 清理：转移成功后仅删除“已转移成功”的短期记忆 ID

- 常见原因与定位
  - 期望“按重要性阈值转移”，但现实现为“满额才整批转移”
    - 重要性阈值用于转移后“低重要性清理”条件，不参与“选择谁被转移”
  - 自动转移任务未运行或未被唤醒
    - 位置：`UnifiedMemoryManager._auto_transfer_loop()`
    - 观察日志是否有“自动转移任务已启动/整批转移完成”
  - 长期层图操作解析失败
    - 位置：`LongTermMemoryManager._parse_graph_operations()`
    - 若 LLM 返回格式异常（无语言代码块、带注释、尾逗号），可能解析失败
  - 存储/依赖未就绪
    - GraphStore 依赖 `networkx`
    - VectorStore 依赖 `chromadb`（如使用）与 embeddings
    - MemoryManager 需在配置中启用

- 解决方案（关键增强点）
  - 图操作解析已增强：
    - 支持无语言代码块；清理注释；优先 `json.loads()`，失败回退 `json_repair.loads()`；
      再失败则截取首个 `[]` 或 `{}` 片段再修复；若为对象则自动包装为数组
  - 环境准备：确保 `networkx`、`json-repair`、`chromadb` 等依赖已安装
  - 验证：运行示例脚本 `examples/ltm_parse_test.py`（已包含多种解析变体）

---

## 3. 症状：长期层图操作解析失败（LLM 输出不规整）

- 表现
  - 日志出现 “JSON 解析失败/图操作解析异常/图操作解析结果非列表”
  - 批次转移失败计数增加

- 定位步骤
  1. 从日志中复制 LLM 原始响应片段
  2. 尝试在本地使用 `json_repair` 进行修复解析
  3. 确认是否存在：无语言三引号代码块、注释、尾逗号、内容嵌在其他文本中

- 解决方案
  - 已内置解析回退链；若仍失败，建议：
    - 调整上游 Prompt 强制标准 JSON 输出
    - 在解析失败时落盘原文（增加临时 telemetry）便于复现

---

## 4. 症状：向量检索异常或结果空

- 短期层
  - 未生成 embedding 或全部为 None → 相似度/检索为空
  - 缓存未失效 → 新增/更新后矩阵仍旧
  - 工具：检查 `_ensure_embeddings_matrix()` 是否返回有效 `matrix`
- 长期层
  - VectorStore 未初始化或未持久化 → 初始化失败/结果为 0
  - ChromaDB 路径/权限问题 → 检查 `data/memory_graph/chroma`
  - Embedding 维度不一致 → 排查 embeddings pipeline

- 排查建议
  - 针对记忆文本，独立调用 embeddings 接口，确认能返回向量
  - 在修改内容后确认有 `_invalidate_matrix_cache()` 调用

---

## 5. 症状：保存/加载异常（短期数据不落盘/未加载）

- 保存：`ShortTermMemoryManager._save_to_disk()` 使用 `orjson` 写入 `short_term_memory.json`
  - 并发保护：有 `_save_lock`
  - 若保存失败：检查路径与权限；捕获错误日志
- 加载：`_load_from_disk()` 读取后重建索引 + 批量补生成向量
  - 若向量缺失：会调用 `_reload_embeddings()` 批量生成
  - 初次运行可能为空属正常

---

## 6. 常用快速操作与验证

- 安装核心依赖
  ```powershell
  cd c:\MoFox-Core
  python -m pip install -r requirements.txt
  ```
- 运行长期层解析健壮性测试（示例）
  ```powershell
  python examples\ltm_parse_test.py
  ```
  预期输出包含：create_memory / update_memory / merge_memories / create_node 等类型计数
- 代码质量自检
  ```powershell
  ruff check .
  ```

---

## 7. 日志与文件位置

- 结构化运行日志：`logs/app_*.log.jsonl`
- 短期数据：`data/memory_graph/short_term_memory.json`
- 向量存储（ChromaDB）：`data/memory_graph/chroma`
- 关键模块：
  - 短期：`src/memory_graph/short_term_manager.py`
  - 长期：`src/memory_graph/long_term_manager.py`
  - 统一：`src/memory_graph/unified_manager.py`
  - 模型与枚举：`src/memory_graph/models.py`
  - 图/向量存储：`src/memory_graph/storage/graph_store.py`, `src/memory_graph/storage/vector_store.py`

---

## 8. 设计要点与注意事项

- 当前“转移策略”为：短期满额才整批转移；重要性阈值用于转移后低重要性清理，不参与选择谁被转移
- 创建/更新记忆后务必刷新相似度缓存（本仓库的主创建路径已处理）
- 解析 LLM 的 JSON 应对多变格式要容错：无语言代码块、注释、尾逗号、混杂文本

---

若仍无法定位问题，建议：
- 附上最近一次运行日志（含 DEBUG 级别），并标注“发生问题的消息/记忆内容、时间点、预期行为”。
- 提供最小复现脚本（可参考 `examples/ltm_parse_test.py` 的组织方式）。
