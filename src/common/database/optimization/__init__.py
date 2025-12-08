"""数据库优化层

职责：
- 批量调度
- 多级缓存
- 数据预加载
"""

from .batch_scheduler import (
    AdaptiveBatchScheduler,
    BatchOperation,
    BatchStats,
    Priority,
    close_batch_scheduler,
    get_batch_scheduler,
)
from .cache_manager import (
    CacheEntry,
    CacheStats,
    LRUCache,
    MultiLevelCache,
    close_cache,
    get_cache,
)
from .preloader import (
    AccessPattern,
    CommonDataPreloader,
    DataPreloader,
    close_preloader,
    get_preloader,
    record_preload_access,
)

__all__ = [
    "AccessPattern",
    # Batch Scheduler
    "AdaptiveBatchScheduler",
    "BatchOperation",
    "BatchStats",
    "CacheEntry",
    "CacheStats",
    "CommonDataPreloader",
    # Preloader
    "DataPreloader",
    "LRUCache",
    # Cache
    "MultiLevelCache",
    "Priority",
    "close_batch_scheduler",
    "close_cache",
    "close_preloader",
    "get_batch_scheduler",
    "get_cache",
    "get_preloader",
    "record_preload_access",
]
