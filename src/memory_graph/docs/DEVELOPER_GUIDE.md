# 记忆系统（Memory Graph）开发说明（核心仓库）

> 维护级别：仅修复 BUG 与安全问题（不做功能迭代）。
> 适用范围：本仓库 `src/memory_graph` 与本目录文档的维护性更新。

## 目标与原则
- 保持现有公共 API 与数据结构的向后兼容。
- 避免架构性改动；必要兼容通过“兼容层”处理。
- 严格遵循项目的数据库六层架构与异步 I/O 约定。
- 所有修复需配套最小化测试与结构化日志。

## 目录定位
- 代码：`src/memory_graph/`（管理器、模型、工具、算法等）
- 文档：`src/memory_graph/docs/` 与 `src/memory_graph/docs/memory_graph/`
- 测试：`tests/memory_graph/`（单元/集成/基准）

## 环境准备

```powershell
# Windows (PowerShell)
# 1) 创建虚拟环境
uv venv

# 2) 安装依赖
uv pip install -r requirements.txt

# 3) 代码质量
ruff check .
ruff format .

# 4) 运行（标准启动）
python bot.py
```

配置要点：
- 复制 `template/template.env` → `.env` 并设置 `EULA_CONFIRMED=true`。
- 按需开启三层/记忆图/兴趣系统，参考 [memory_graph/memory_graph_README.md](memory_graph/memory_graph_README.md)。

## 开发约束（重要）
- 数据库访问：统一使用 API 层（`CRUDBase`/`QueryBuilder`）；批量写入/更新使用 `AdaptiveBatchScheduler`；禁止直接新建 `Session`。
- 异步 I/O：优先 `async/await`；避免阻塞主事件循环；必要时使用 `asyncio.to_thread()`。
- 日志：使用项目日志器（`src/common/logger.py`），记录错误与关键指标；保持结构化字段一致性。
- 风格：行宽 ≤ 120，双引号，类型提示推荐用于公共 API。
- 兼容性：修复不改变行为语义；涉及破坏性变更需走兼容层并标注迁移方案。

## 修复流程（推荐）
1. 复现：收集最小复现、日志片段与版本信息。
2. 定位：在 `src/memory_graph/` 内定位模块与函数；确认是否涉及数据库或调度。
3. 测试：在 `tests/memory_graph/` 添加/完善针对性用例（单元优先、必要时集成）。
4. 修复：按照“开发约束”实施最小改动；增加必要的日志与指标。
5. 校验：本地运行 `ruff check` 与 `pytest`；查看 `logs/app_*.jsonl` 的结构化指标。
6. 提交：撰写清晰的变更说明与影响范围；链接相关文档。

## 常用命令

```powershell
# 运行测试（精确到子模块）
python -m pytest tests/memory_graph/test_builder.py -q
python -m pytest tests/memory_graph/test_retriever.py -q
python -m pytest tests/memory_graph -q

# 格式化与检查
ruff format src/memory_graph
ruff check src/memory_graph

# 查看结构化日志（简）
Get-Content logs/app_*.jsonl | Select-Object -First 50
```

## 架构对齐与参考
- 总体架构与集成：[memory_graph/design_outline.md](memory_graph/design_outline.md)
- 长期管理优化与示例：[memory_graph/long_term_manager_optimization_summary.md](memory_graph/long_term_manager_optimization_summary.md)
- 统一管理器说明：[memory_graph/unified_memory_manager.md](memory_graph/unified_memory_manager.md)
- 统一调度器指南：[docs/unified_scheduler_guide.md](unified_scheduler_guide.md)
- 数据库重构说明：[docs/database_refactoring_completion.md](database_refactoring_completion.md)

## 监控与审计
- 指标：处理速度、平均延迟、内存使用、批处理大小、缓存命中率。
- 日志：为修复点添加必要结构化字段，便于后续回溯与统计。
- 权限：批量清理/导出/合并等敏感操作需管理员或 Master 权限；遵循 `plugin.memory_graph.admin` 节点约定。

## 提交与评审
- 提交信息包含：问题编号、影响范围、复现说明、修复方案、测试覆盖。
- 评审重点：兼容性、最小改动、性能影响、日志与监控是否完善。

---
本指南面向核心仓库的维护性开发，若需功能扩展，请关注插件版的发布与独立仓库的开发流程。
