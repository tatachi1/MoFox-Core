"""数据库工具层

职责：
- 异常定义
- 装饰器工具
- 性能监控
"""

from .decorators import (
    cached,
    db_operation,
    measure_time,
    retry,
    timeout,
    transactional,
)
from .exceptions import (
    BatchSchedulerError,
    CacheError,
    ConnectionPoolError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseInitializationError,
    DatabaseMigrationError,
    DatabaseQueryError,
    DatabaseTransactionError,
)
from .monitoring import (
    DatabaseMonitor,
    get_monitor,
    print_stats,
    record_cache_hit,
    record_cache_miss,
    record_operation,
    reset_stats,
    get_slow_queries,
    get_slow_query_report,
    record_slow_query,
    set_slow_query_config,
    enable_slow_query_monitoring,
    disable_slow_query_monitoring,
    is_slow_query_monitoring_enabled,
)

__all__ = [
    "BatchSchedulerError",
    "CacheError",
    "ConnectionPoolError",
    "DatabaseConnectionError",
    # 异常
    "DatabaseError",
    "DatabaseInitializationError",
    "DatabaseMigrationError",
    # 监控
    "DatabaseMonitor",
    "DatabaseQueryError",
    "DatabaseTransactionError",
    "cached",
    "db_operation",
    "get_monitor",
    "measure_time",
    "print_stats",
    "record_cache_hit",
    "record_cache_miss",
    "record_operation",
    "reset_stats",
    "get_slow_queries",
    "get_slow_query_report",
    "record_slow_query",
    "set_slow_query_config",
    "enable_slow_query_monitoring",
    "disable_slow_query_monitoring",
    "is_slow_query_monitoring_enabled",
    # 装饰器
    "retry",
    "timeout",
    "transactional",
]
