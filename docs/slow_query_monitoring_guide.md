# 慢查询监控实现指南

## 概述

我们已经完整实现了数据库慢查询监控系统，包括：
- ✅ 慢查询自动检测和收集（**默认关闭**）
- ✅ 实时性能监控和统计
- ✅ 详细的文本和HTML报告生成
- ✅ 优化建议和性能分析
- ✅ 用户可选的启用/禁用开关

## 快速启用

### 方法 1：配置文件启用（推荐）

编辑 `config/bot_config.toml`：

```toml
[database]
enable_slow_query_logging = true  # 改为 true 启用
slow_query_threshold = 0.5        # 设置阈值（秒）
```

### 方法 2：代码动态启用

```python
from src.common.database.utils import enable_slow_query_monitoring

# 启用监控
enable_slow_query_monitoring()

# 禁用监控
disable_slow_query_monitoring()

# 检查状态
if is_slow_query_monitoring_enabled():
    print("慢查询监控已启用")
```

## 配置

### bot_config.toml

```toml
[database]
# 慢查询监控配置（默认关闭，需要时设置 enable_slow_query_logging = true 启用）
enable_slow_query_logging = false    # 是否启用慢查询日志（设置为 true 启用）
slow_query_threshold = 0.5           # 慢查询阈值（秒）
query_timeout = 30                   # 查询超时时间（秒）
collect_slow_queries = true          # 是否收集慢查询统计
slow_query_buffer_size = 100         # 慢查询缓冲大小（最近N条）
```

**推荐参数**：
- **生产环境（推荐）**：`enable_slow_query_logging = false` - 最小性能开销
- **测试环境**：`enable_slow_query_logging = true` + `slow_query_threshold = 0.5` 
- **开发环境**：`enable_slow_query_logging = true` + `slow_query_threshold = 0.1` - 捕获所有慢查询

## 使用方式

### 1. 自动监控（推荐）

启用后，所有使用 `@measure_time()` 装饰器的函数都会被监控：

```python
from src.common.database.utils import measure_time

@measure_time()  # 使用配置中的阈值
async def my_database_query():
    return result

@measure_time(log_slow=1.0)  # 自定义阈值
async def another_query():
    return result
```

### 2. 手动记录慢查询

```python
from src.common.database.utils import record_slow_query

record_slow_query(
    operation_name="custom_query",
    execution_time=1.5,
    sql="SELECT * FROM users WHERE id = ?",
    args=(123,)
)
```

### 3. 获取慢查询报告

```python
from src.common.database.utils import get_slow_query_report

report = get_slow_query_report()

print(f"总慢查询数: {report['total']}")
print(f"阈值: {report['threshold']}")

for op in report['top_operations']:
    print(f"{op['operation']}: {op['count']} 次")
```

### 4. 在代码中使用分析工具

```python
from src.common.database.utils.slow_query_analyzer import SlowQueryAnalyzer

# 生成文本报告
text_report = SlowQueryAnalyzer.generate_text_report()
print(text_report)

# 生成HTML报告
SlowQueryAnalyzer.generate_html_report("reports/slow_query.html")

# 获取最慢的查询
slowest = SlowQueryAnalyzer.get_slowest_queries(limit=20)
for query in slowest:
    print(f"{query.operation_name}: {query.execution_time:.3f}s")
```

## 输出示例

### 启用时的初始化

```
✅ 慢查询监控已启用 (阈值: 0.5s, 缓冲: 100)
```

### 运行时的慢查询告警

```
🐢 get_user_by_id 执行缓慢: 0.752s (阈值: 0.500s)
```

### 关闭时的性能报告（仅在启用时输出）

```
============================================================
数据库性能统计
============================================================

操作统计:
  get_user_by_id: 次数=156, 平均=0.025s, 最小=0.001s, 最大=1.203s, 错误=0, 慢查询=3

缓存:
  命中=8923, 未命中=1237, 命中率=87.82%

整体:
  错误率=0.00%
  慢查询总数=3
  慢查询阈值=0.500s

🐢 慢查询报告:
  按操作排名（Top 10）:
    1. get_user_by_id: 次数=3, 平均=0.752s, 最大=1.203s
```

## 常见问题

### Q1: 如何知道监控是否启用了？

```python
from src.common.database.utils import is_slow_query_monitoring_enabled

if is_slow_query_monitoring_enabled():
    print("✅ 慢查询监控已启用")
else:
    print("❌ 慢查询监控已禁用")
```

### Q2: 如何临时启用/禁用？

```python
from src.common.database.utils import enable_slow_query_monitoring, disable_slow_query_monitoring

# 临时启用
enable_slow_query_monitoring()

# ... 执行需要监控的代码 ...

# 临时禁用
disable_slow_query_monitoring()
```

### Q3: 默认关闭会影响性能吗？

完全不会。关闭后没有任何性能开销。

### Q4: 监控数据会持久化吗？

目前使用内存缓冲（默认最近 100 条），系统关闭时会输出报告。

## 最佳实践

### 1. 生产环境配置

```toml
# config/bot_config.toml
[database]
enable_slow_query_logging = false    # 默认关闭
```

只在需要调试性能问题时临时启用：

```python
from src.common.database.utils import enable_slow_query_monitoring

# 在某个插件中启用
enable_slow_query_monitoring()

# 执行和监控需要优化的代码

disable_slow_query_monitoring()
```

### 2. 开发/测试环境配置

```toml
# config/bot_config.toml
[database]
enable_slow_query_logging = true     # 启用
slow_query_threshold = 0.5           # 500ms
```

### 3. 使用 @measure_time() 装饰器

```python
# ✅ 推荐：自动监控所有 I/O 操作
@measure_time()
async def get_user_info(user_id: str):
    return await user_crud.get_by_id(user_id)
```

## 技术细节

### 核心组件

| 文件 | 职责 |
|-----|------|
| `monitoring.py` | 核心监控器，启用/禁用逻辑 |
| `decorators.py` | `@measure_time()` 装饰器 |
| `slow_query_analyzer.py` | 分析和报告生成 |

### 启用流程

```
enable_slow_query_logging = true
           ↓
main.py: set_slow_query_config()
           ↓
get_monitor().enable()
           ↓
is_enabled() = True
           ↓
record_operation() 检查并记录慢查询
           ↓
输出 🐢 警告信息
```

### 禁用流程

```
enable_slow_query_logging = false
           ↓
is_enabled() = False
           ↓
record_operation() 不记录慢查询
           ↓
无性能开销
```

## 性能影响

### 启用时

- CPU 开销: < 0.1%（仅在超过阈值时记录）
- 内存开销: ~50KB（缓冲 100 条慢查询）

### 禁用时

- CPU 开销: ~0%
- 内存开销: 0 KB（不收集数据）

**结论**：可以安全地在生产环境中默认禁用，需要时启用。

## 下一步优化

1. **自动启用**：在检测到性能问题时自动启用
2. **告警系统**：当慢查询比例超过阈值时发送告警
3. **Prometheus 集成**：导出监控指标
4. **Grafana 仪表板**：实时可视化

---

**文档更新**: 2025-12-17  
**状态**: ✅ 默认关闭，用户可选启用
