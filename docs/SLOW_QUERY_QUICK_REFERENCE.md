# 慢查询监控快速参考

## 🚀 快速启用

### 方法 1：修改配置（推荐）

```toml
# config/bot_config.toml
[database]
enable_slow_query_logging = true  # 改为 true 启用
slow_query_threshold = 0.5        # 选项：阈值（秒）
```

### 方法 2：代码启用

```python
from src.common.database.utils import enable_slow_query_monitoring

enable_slow_query_monitoring()  # 启用

# ... 你的代码 ...

disable_slow_query_monitoring()  # 禁用
```

### 方法 3：检查状态

```python
from src.common.database.utils import is_slow_query_monitoring_enabled

if is_slow_query_monitoring_enabled():
    print("✅ 已启用")
else:
    print("❌ 已禁用")
```

---

## 📊 关键命令

```python
# 启用/禁用
from src.common.database.utils import (
    enable_slow_query_monitoring,
    disable_slow_query_monitoring,
    is_slow_query_monitoring_enabled
)

enable_slow_query_monitoring()
disable_slow_query_monitoring()
is_slow_query_monitoring_enabled()

# 获取数据
from src.common.database.utils import (
    get_slow_queries,
    get_slow_query_report
)

queries = get_slow_queries(limit=20)
report = get_slow_query_report()

# 生成报告
from src.common.database.utils.slow_query_analyzer import SlowQueryAnalyzer

SlowQueryAnalyzer.generate_html_report("report.html")
text = SlowQueryAnalyzer.generate_text_report()
```

---

## ⚙️ 推荐配置

```toml
# 生产环境（默认）
enable_slow_query_logging = false

# 测试环境
enable_slow_query_logging = true
slow_query_threshold = 0.5

# 开发环境
enable_slow_query_logging = true
slow_query_threshold = 0.1
```

---

## 💡 使用示例

```python
# 1. 启用监控
enable_slow_query_monitoring()

# 2. 自动监控函数
@measure_time()
async def slow_operation():
    return await db.query(...)

# 3. 查看报告
report = get_slow_query_report()
print(f"总慢查询数: {report['total']}")

# 4. 禁用监控
disable_slow_query_monitoring()
```

---

## 📈 性能

| 状态 | CPU 开销 | 内存占用 |
|------|----------|----------|
| 启用 | < 0.1% | ~50 KB |
| 禁用 | ~0% | 0 KB |

---

## 🎯 核心要点

✅ **默认关闭** - 无性能开销  
✅ **按需启用** - 方便的启用/禁用  
✅ **实时告警** - 超过阈值时输出  
✅ **详细报告** - 关闭时输出分析  
✅ **零成本** - 禁用时完全无开销  

---

**启用**: `enable_slow_query_monitoring()`  
**禁用**: `disable_slow_query_monitoring()`  
**查看**: `get_slow_query_report()`  

更多信息: `docs/slow_query_monitoring_guide.md`
