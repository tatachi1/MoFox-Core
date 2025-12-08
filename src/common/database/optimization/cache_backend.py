"""缓存后端抽象基类

定义统一的缓存接口，支持多种缓存后端实现：
- MemoryCache: 内存多级缓存（L1 + L2）
- RedisCache: Redis 分布式缓存
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheStats:
    """缓存统计信息

    Attributes:
        hits: 命中次数
        misses: 未命中次数
        evictions: 淘汰次数
        total_size: 总大小（字节）
        item_count: 条目数量
    """

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_size: int = 0
    item_count: int = 0

    @property
    def hit_rate(self) -> float:
        """命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def eviction_rate(self) -> float:
        """淘汰率"""
        return self.evictions / self.item_count if self.item_count > 0 else 0.0


class CacheBackend(ABC):
    """缓存后端抽象基类

    定义统一的缓存操作接口，所有缓存实现必须继承此类
    """

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """从缓存获取数据

        Args:
            key: 缓存键

        Returns:
            缓存值，如果不存在返回 None
        """
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
    ) -> None:
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 表示使用默认 TTL
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存条目

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查键是否存在

        Args:
            key: 缓存键

        Returns:
            键是否存在
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """清空所有缓存"""
        pass

    @abstractmethod
    async def get_stats(self) -> dict[str, Any]:
        """获取缓存统计信息

        Returns:
            包含命中率、条目数等统计数据的字典
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭缓存连接/清理资源"""
        pass

    async def get_or_load(
        self,
        key: str,
        loader: Any,
        ttl: float | None = None,
    ) -> Any | None:
        """获取缓存或通过 loader 加载

        Args:
            key: 缓存键
            loader: 数据加载函数（同步或异步）
            ttl: 过期时间（秒）

        Returns:
            缓存值或加载的值
        """
        import asyncio

        # 尝试从缓存获取
        value = await self.get(key)
        if value is not None:
            return value

        # 缓存未命中，使用 loader 加载
        if loader is not None:
            if asyncio.iscoroutinefunction(loader):
                value = await loader()
            else:
                value = loader()

            if value is not None:
                await self.set(key, value, ttl=ttl)

            return value

        return None

    async def delete_pattern(self, pattern: str) -> int:
        """删除匹配模式的所有键（可选实现）

        Args:
            pattern: 键模式（支持 * 通配符）

        Returns:
            删除的键数量
        """
        # 默认实现：不支持模式删除
        raise NotImplementedError("此缓存后端不支持模式删除")

    async def mget(self, keys: list[str]) -> dict[str, Any]:
        """批量获取多个键的值（可选实现）

        Args:
            keys: 键列表

        Returns:
            键值对字典，不存在的键不包含在结果中
        """
        # 默认实现：逐个获取
        result = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value
        return result

    async def mset(
        self,
        mapping: dict[str, Any],
        ttl: float | None = None,
    ) -> None:
        """批量设置多个键值对（可选实现）

        Args:
            mapping: 键值对字典
            ttl: 过期时间（秒）
        """
        # 默认实现：逐个设置
        for key, value in mapping.items():
            await self.set(key, value, ttl=ttl)

    @property
    @abstractmethod
    def backend_type(self) -> str:
        """返回缓存后端类型标识"""
        pass

    @property
    def is_distributed(self) -> bool:
        """是否为分布式缓存（默认 False）"""
        return False
