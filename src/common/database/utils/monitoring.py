"""数据库性能监控

提供数据库操作的性能监控和统计功能
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from src.common.logger import get_logger

logger = get_logger("database.monitoring")


@dataclass
class SlowQueryRecord:
    """慢查询记录"""

    operation_name: str
    execution_time: float
    timestamp: float
    sql: str | None = None
    args: tuple | None = None
    stack_trace: str | None = None

    def __str__(self) -> str:
        return (
            f"[{self.operation_name}] {self.execution_time:.3f}s "
            f"@ {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.timestamp))}"
        )


@dataclass
class OperationMetrics:
    """操作指标"""

    count: int = 0
    total_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0
    error_count: int = 0
    last_execution_time: float | None = None
    slow_query_count: int = 0  # 该操作的慢查询数

    @property
    def avg_time(self) -> float:
        """平均执行时间"""
        return self.total_time / self.count if self.count > 0 else 0.0

    def record_success(self, execution_time: float):
        """记录成功执行"""
        self.count += 1
        self.total_time += execution_time
        self.min_time = min(self.min_time, execution_time)
        self.max_time = max(self.max_time, execution_time)
        self.last_execution_time = time.time()

    def record_error(self):
        """记录错误"""
        self.error_count += 1

    def record_slow_query(self):
        """记录慢查询"""
        self.slow_query_count += 1


@dataclass
class DatabaseMetrics:
    """数据库指标"""

    # 操作统计
    operations: dict[str, OperationMetrics] = field(default_factory=dict)

    # 连接池统计
    connection_acquired: int = 0
    connection_released: int = 0
    connection_errors: int = 0

    # 缓存统计
    cache_hits: int = 0
    cache_misses: int = 0
    cache_sets: int = 0
    cache_invalidations: int = 0

    # 批处理统计
    batch_operations: int = 0
    batch_items_total: int = 0
    batch_avg_size: float = 0.0

    # 慢查询统计
    slow_query_count: int = 0
    slow_query_threshold: float = 0.5  # 慢查询阈值

    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    @property
    def error_rate(self) -> float:
        """错误率"""
        total_ops = sum(m.count for m in self.operations.values())
        total_errors = sum(m.error_count for m in self.operations.values())
        return total_errors / total_ops if total_ops > 0 else 0.0

    def get_operation_metrics(self, operation_name: str) -> OperationMetrics:
        """获取操作指标"""
        if operation_name not in self.operations:
            self.operations[operation_name] = OperationMetrics()
        return self.operations[operation_name]


class DatabaseMonitor:
    """数据库监控器

    单例模式，收集和报告数据库性能指标
    """

    _instance: Optional["DatabaseMonitor"] = None
    _metrics: DatabaseMetrics
    _slow_queries: deque  # 最近的慢查询记录
    _slow_query_buffer_size: int = 100
    _enabled: bool = False  # 慢查询监控是否启用

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._metrics = DatabaseMetrics()
            cls._instance._slow_queries = deque(maxlen=cls._slow_query_buffer_size)
            cls._instance._enabled = False
        return cls._instance

    def enable(self):
        """启用慢查询监控"""
        self._enabled = True
        logger.info("✅ 慢查询监控已启用")

    def disable(self):
        """禁用慢查询监控"""
        self._enabled = False
        logger.info("❌ 慢查询监控已禁用")

    def is_enabled(self) -> bool:
        """检查慢查询监控是否启用"""
        return self._enabled

    def set_slow_query_config(self, threshold: float, buffer_size: int):
        """设置慢查询配置"""
        self._metrics.slow_query_threshold = threshold
        self._slow_query_buffer_size = buffer_size
        self._slow_queries = deque(maxlen=buffer_size)
        # 设置配置时自动启用
        self._enabled = True

    def record_operation(
        self,
        operation_name: str,
        execution_time: float,
        success: bool = True,
        sql: str | None = None,
    ):
        """记录操作"""
        metrics = self._metrics.get_operation_metrics(operation_name)
        if success:
            metrics.record_success(execution_time)

            # 只在启用时检查是否为慢查询
            if self._enabled and execution_time > self._metrics.slow_query_threshold:
                self.record_slow_query(operation_name, execution_time, sql)
        else:
            metrics.record_error()

    def record_slow_query(
        self,
        operation_name: str,
        execution_time: float,
        sql: str | None = None,
        args: tuple | None = None,
        stack_trace: str | None = None,
    ):
        """记录慢查询"""
        self._metrics.slow_query_count += 1
        self._metrics.get_operation_metrics(operation_name).record_slow_query()

        record = SlowQueryRecord(
            operation_name=operation_name,
            execution_time=execution_time,
            timestamp=time.time(),
            sql=sql,
            args=args,
            stack_trace=stack_trace,
        )
        self._slow_queries.append(record)

        # 立即记录到日志（实时告警）
        logger.warning(f"🐢 慢查询: {record}")

    def record_connection_acquired(self):
        """记录连接获取"""
        self._metrics.connection_acquired += 1

    def record_connection_released(self):
        """记录连接释放"""
        self._metrics.connection_released += 1

    def record_connection_error(self):
        """记录连接错误"""
        self._metrics.connection_errors += 1

    def record_cache_hit(self):
        """记录缓存命中"""
        self._metrics.cache_hits += 1

    def record_cache_miss(self):
        """记录缓存未命中"""
        self._metrics.cache_misses += 1

    def record_cache_set(self):
        """记录缓存设置"""
        self._metrics.cache_sets += 1

    def record_cache_invalidation(self):
        """记录缓存失效"""
        self._metrics.cache_invalidations += 1

    def record_batch_operation(self, batch_size: int):
        """记录批处理操作"""
        self._metrics.batch_operations += 1
        self._metrics.batch_items_total += batch_size
        self._metrics.batch_avg_size = (
            self._metrics.batch_items_total / self._metrics.batch_operations
        )

    def get_metrics(self) -> DatabaseMetrics:
        """获取指标"""
        return self._metrics

    def get_slow_queries(self, limit: int = 0) -> list[SlowQueryRecord]:
        """获取慢查询记录

        Args:
            limit: 返回数量限制，0 表示返回全部

        Returns:
            慢查询记录列表
        """
        records = list(self._slow_queries)
        if limit > 0:
            records = records[-limit:]
        return records

    def get_slow_query_report(self) -> dict[str, Any]:
        """获取慢查询报告"""
        slow_queries = list(self._slow_queries)

        if not slow_queries:
            return {
                "total": 0,
                "threshold": f"{self._metrics.slow_query_threshold:.3f}s",
                "top_operations": [],
                "recent_queries": [],
            }

        # 按操作分组统计
        operation_stats = {}
        for record in slow_queries:
            if record.operation_name not in operation_stats:
                operation_stats[record.operation_name] = {
                    "count": 0,
                    "total_time": 0.0,
                    "max_time": 0.0,
                    "min_time": float("inf"),
                }
            stats = operation_stats[record.operation_name]
            stats["count"] += 1
            stats["total_time"] += record.execution_time
            stats["max_time"] = max(stats["max_time"], record.execution_time)
            stats["min_time"] = min(stats["min_time"], record.execution_time)

        # 按慢查询数排序
        top_operations = sorted(
            operation_stats.items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )[:10]

        return {
            "total": len(slow_queries),
            "threshold": f"{self._metrics.slow_query_threshold:.3f}s",
            "top_operations": [
                {
                    "operation": op_name,
                    "count": stats["count"],
                    "avg_time": f"{stats['total_time'] / stats['count']:.3f}s",
                    "max_time": f"{stats['max_time']:.3f}s",
                    "min_time": f"{stats['min_time']:.3f}s",
                }
                for op_name, stats in top_operations
            ],
            "recent_queries": [
                {
                    "operation": record.operation_name,
                    "time": f"{record.execution_time:.3f}s",
                    "timestamp": time.strftime(
                        "%Y-%m-%d %H:%M:%S",
                        time.localtime(record.timestamp),
                    ),
                }
                for record in slow_queries[-20:]
            ],
        }

    def get_summary(self) -> dict[str, Any]:
        """获取统计摘要"""
        metrics = self._metrics

        operation_summary = {}
        for op_name, op_metrics in metrics.operations.items():
            operation_summary[op_name] = {
                "count": op_metrics.count,
                "avg_time": f"{op_metrics.avg_time:.3f}s",
                "min_time": f"{op_metrics.min_time:.3f}s",
                "max_time": f"{op_metrics.max_time:.3f}s",
                "error_count": op_metrics.error_count,
                "slow_query_count": op_metrics.slow_query_count,
            }

        return {
            "operations": operation_summary,
            "connections": {
                "acquired": metrics.connection_acquired,
                "released": metrics.connection_released,
                "errors": metrics.connection_errors,
                "active": metrics.connection_acquired - metrics.connection_released,
            },
            "cache": {
                "hits": metrics.cache_hits,
                "misses": metrics.cache_misses,
                "sets": metrics.cache_sets,
                "invalidations": metrics.cache_invalidations,
                "hit_rate": f"{metrics.cache_hit_rate:.2%}",
            },
            "batch": {
                "operations": metrics.batch_operations,
                "total_items": metrics.batch_items_total,
                "avg_size": f"{metrics.batch_avg_size:.1f}",
            },
            "overall": {
                "error_rate": f"{metrics.error_rate:.2%}",
                "slow_query_count": metrics.slow_query_count,
                "slow_query_threshold": f"{metrics.slow_query_threshold:.3f}s",
            },
        }

    def print_summary(self):
        """打印统计摘要"""
        summary = self.get_summary()

        logger.info("=" * 60)
        logger.info("数据库性能统计")
        logger.info("=" * 60)

        # 操作统计
        if summary["operations"]:
            logger.info("\n操作统计:")
            for op_name, stats in summary["operations"].items():
                logger.info(
                    f"  {op_name}: "
                    f"次数={stats['count']}, "
                    f"平均={stats['avg_time']}, "
                    f"最小={stats['min_time']}, "
                    f"最大={stats['max_time']}, "
                    f"错误={stats['error_count']}, "
                    f"慢查询={stats['slow_query_count']}"
                )

        # 连接池统计
        logger.info("\n连接池:")
        conn = summary["connections"]
        logger.info(
            f"  获取={conn['acquired']}, "
            f"释放={conn['released']}, "
            f"活跃={conn['active']}, "
            f"错误={conn['errors']}"
        )

        # 缓存统计
        logger.info("\n缓存:")
        cache = summary["cache"]
        logger.info(
            f"  命中={cache['hits']}, "
            f"未命中={cache['misses']}, "
            f"设置={cache['sets']}, "
            f"失效={cache['invalidations']}, "
            f"命中率={cache['hit_rate']}"
        )

        # 批处理统计
        logger.info("\n批处理:")
        batch = summary["batch"]
        logger.info(
            f"  操作={batch['operations']}, "
            f"总项目={batch['total_items']}, "
            f"平均大小={batch['avg_size']}"
        )

        # 整体统计
        logger.info("\n整体:")
        overall = summary["overall"]
        logger.info(f"  错误率={overall['error_rate']}")
        logger.info(f"  慢查询总数={overall['slow_query_count']}")
        logger.info(f"  慢查询阈值={overall['slow_query_threshold']}")

        # 慢查询报告
        if overall["slow_query_count"] > 0:
            logger.info("\n🐢 慢查询报告:")
            slow_report = self.get_slow_query_report()

            if slow_report["top_operations"]:
                logger.info("  按操作排名（Top 10）:")
                for idx, op in enumerate(slow_report["top_operations"], 1):
                    logger.info(
                        f"    {idx}. {op['operation']}: "
                        f"次数={op['count']}, "
                        f"平均={op['avg_time']}, "
                        f"最大={op['max_time']}"
                    )


        logger.info("=" * 60)

    def reset(self):
        """重置统计"""
        self._metrics = DatabaseMetrics()
        logger.info("数据库监控统计已重置")


# 全局监控器实例
_monitor: DatabaseMonitor | None = None


def get_monitor() -> DatabaseMonitor:
    """获取监控器实例"""
    global _monitor
    if _monitor is None:
        _monitor = DatabaseMonitor()
    return _monitor


# 便捷函数
def record_operation(operation_name: str, execution_time: float, success: bool = True):
    """记录操作"""
    get_monitor().record_operation(operation_name, execution_time, success)


def record_slow_query(
    operation_name: str,
    execution_time: float,
    sql: str | None = None,
    args: tuple | None = None,
):
    """记录慢查询"""
    get_monitor().record_slow_query(operation_name, execution_time, sql, args)


def get_slow_queries(limit: int = 0) -> list[SlowQueryRecord]:
    """获取慢查询记录"""
    return get_monitor().get_slow_queries(limit)


def get_slow_query_report() -> dict[str, Any]:
    """获取慢查询报告"""
    return get_monitor().get_slow_query_report()


def set_slow_query_config(threshold: float, buffer_size: int):
    """设置慢查询配置"""
    get_monitor().set_slow_query_config(threshold, buffer_size)


def enable_slow_query_monitoring():
    """启用慢查询监控"""
    get_monitor().enable()


def disable_slow_query_monitoring():
    """禁用慢查询监控"""
    get_monitor().disable()


def is_slow_query_monitoring_enabled() -> bool:
    """检查慢查询监控是否启用"""
    return get_monitor().is_enabled()


def record_cache_hit():
    """记录缓存命中"""
    get_monitor().record_cache_hit()


def record_cache_miss():
    """记录缓存未命中"""
    get_monitor().record_cache_miss()


def print_stats():
    """打印统计信息"""
    get_monitor().print_summary()


def reset_stats():
    """重置统计"""
    get_monitor().reset()
