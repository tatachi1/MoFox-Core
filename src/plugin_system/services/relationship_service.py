"""
用户关系分服务
提供独立的关系分获取和管理功能，不依赖任何插件
"""

import time

from src.common.database.core import get_db_session
from src.common.database.core.models import UserRelationships
from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("relationship_service")


class RelationshipService:
    """用户关系分服务 - 独立于插件的数据库直接访问层

    内存优化：添加缓存大小限制和自动过期清理
    """

    # 🔧 缓存配置
    CACHE_MAX_SIZE = 1000  # 最大缓存用户数

    def __init__(self):
        self._cache: dict[str, dict] = {}  # user_id -> {score, text, last_updated}
        self._cache_ttl = 300  # 缓存5分钟
        self._last_cleanup = time.time()  # 上次清理时间
        self._cleanup_interval = 60  # 每60秒清理一次过期条目

    async def get_user_relationship_score(self, user_id: str) -> float:
        """
        获取用户关系分

        Args:
            user_id: 用户ID

        Returns:
            关系分 (0.0 - 1.0)
        """
        try:
            # 先检查缓存
            cached_data = self._get_from_cache(user_id)
            if cached_data is not None:
                return cached_data["score"]

            # 从数据库获取
            relationship_data = await self._fetch_from_database(user_id)
            if relationship_data:
                score = relationship_data.relationship_score
                # 更新缓存
                self._update_cache(user_id, score, relationship_data.relationship_text)
                logger.debug(f"从数据库获取用户关系分: {user_id} -> {score:.3f}")
                return max(0.0, min(1.0, score))
            else:
                # 用户不存在，返回默认分数并创建记录
                default_score = global_config.affinity_flow.base_relationship_score
                await self._create_default_relationship(user_id)
                self._update_cache(user_id, default_score, "新用户")
                logger.debug(f"创建默认关系分: {user_id} -> {default_score:.3f}")
                return default_score

        except Exception as e:
            logger.error(f"获取用户关系分失败: {user_id}, 错误: {e}")
            return global_config.affinity_flow.base_relationship_score

    async def get_user_relationship_data(self, user_id: str) -> dict:
        """
        获取用户完整关系数据

        Args:
            user_id: 用户ID

        Returns:
            包含关系分、关系文本等的字典
        """
        try:
            # 先检查缓存
            cached_data = self._get_from_cache(user_id)
            if cached_data is not None:
                return {
                    "relationship_score": cached_data["score"],
                    "relationship_text": cached_data["text"],
                    "last_updated": cached_data["last_updated"]
                }

            # 从数据库获取
            relationship_data = await self._fetch_from_database(user_id)
            if relationship_data:
                result = {
                    "relationship_score": relationship_data.relationship_score,
                    "relationship_text": relationship_data.relationship_text or "",
                    "last_updated": relationship_data.last_updated,
                    "user_name": relationship_data.user_name or ""
                }
                # 更新缓存
                self._update_cache(user_id, result["relationship_score"], result["relationship_text"])
                return result
            else:
                # 创建默认记录
                default_score = global_config.affinity_flow.base_relationship_score
                await self._create_default_relationship(user_id)
                default_result = {
                    "relationship_score": default_score,
                    "relationship_text": "新用户",
                    "last_updated": time.time(),
                    "user_name": ""
                }
                self._update_cache(user_id, default_score, "新用户")
                return default_result

        except Exception as e:
            logger.error(f"获取用户关系数据失败: {user_id}, 错误: {e}")
            return {
                "relationship_score": global_config.affinity_flow.base_relationship_score,
                "relationship_text": "新用户",
                "last_updated": time.time(),
                "user_name": ""
            }

    async def update_user_relationship(self, user_id: str, relationship_score: float, relationship_text: str | None = None, user_name: str | None = None):
        """
        更新用户关系数据

        Args:
            user_id: 用户ID
            relationship_score: 关系分 (0.0 - 1.0)
            relationship_text: 关系描述文本
            user_name: 用户名称
        """
        try:
            # 限制分数范围
            score = max(0.0, min(1.0, relationship_score))

            async with get_db_session() as session:
                # 查找现有记录
                from sqlalchemy import select
                stmt = select(UserRelationships).where(UserRelationships.user_id == user_id)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    # 更新现有记录
                    existing.relationship_score = score
                    existing.last_updated = time.time()
                    if relationship_text is not None:
                        existing.relationship_text = relationship_text
                    if user_name is not None:
                        existing.user_name = user_name
                    logger.debug(f"更新用户关系: {user_id} -> {score:.3f}")
                else:
                    # 创建新记录
                    new_relationship = UserRelationships(
                        user_id=user_id,
                        user_name=user_name or "",
                        relationship_text=relationship_text or "新用户",
                        relationship_score=score,
                        last_updated=time.time()
                    )
                    session.add(new_relationship)
                    logger.debug(f"创建用户关系: {user_id} -> {score:.3f}")

                await session.commit()

                # 更新缓存
                self._update_cache(user_id, score, relationship_text or "新用户")

        except Exception as e:
            logger.error(f"更新用户关系失败: {user_id}, 错误: {e}")

    def _get_from_cache(self, user_id: str) -> dict | None:
        """从缓存获取数据"""
        # 🔧 触发定期清理
        self._maybe_cleanup_expired()

        if user_id in self._cache:
            cached_data = self._cache[user_id]
            if time.time() - cached_data["last_updated"] < self._cache_ttl:
                return cached_data
            else:
                # 缓存过期，删除
                del self._cache[user_id]
        return None

    def _update_cache(self, user_id: str, score: float, text: str):
        """更新缓存"""
        # 🔧 内存优化：检查缓存大小限制
        if len(self._cache) >= self.CACHE_MAX_SIZE and user_id not in self._cache:
            # 淘汰最旧的 10% 条目
            self._evict_oldest_entries()

        self._cache[user_id] = {
            "score": score,
            "text": text,
            "last_updated": time.time()
        }

    def _maybe_cleanup_expired(self):
        """🔧 内存优化：定期清理过期条目"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        expired_keys = []
        for user_id, data in self._cache.items():
            if now - data["last_updated"] >= self._cache_ttl:
                expired_keys.append(user_id)

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"🔧 relationship_service 清理了 {len(expired_keys)} 个过期缓存条目")

    def _evict_oldest_entries(self):
        """🔧 内存优化：淘汰最旧的条目"""
        evict_count = max(1, len(self._cache) // 10)
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1]["last_updated"]
        )
        for user_id, _ in sorted_entries[:evict_count]:
            del self._cache[user_id]
        logger.debug(f"🔧 relationship_service LRU淘汰了 {evict_count} 个缓存条目")

    async def _fetch_from_database(self, user_id: str) -> UserRelationships | None:
        """从数据库获取关系数据"""
        try:
            async with get_db_session() as session:
                from sqlalchemy import select
                stmt = select(UserRelationships).where(UserRelationships.user_id == user_id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"从数据库获取关系数据失败: {user_id}, 错误: {e}")
            return None

    async def _create_default_relationship(self, user_id: str):
        """创建默认关系记录"""
        try:
            default_score = global_config.affinity_flow.base_relationship_score
            async with get_db_session() as session:
                new_relationship = UserRelationships(
                    user_id=user_id,
                    user_name="",
                    relationship_text="新用户",
                    relationship_score=default_score,
                    last_updated=time.time()
                )
                session.add(new_relationship)
                await session.commit()
                logger.debug(f"创建默认关系记录: {user_id} -> {default_score:.3f}")
        except Exception as e:
            logger.error(f"创建默认关系记录失败: {user_id}, 错误: {e}")

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return {
            "cached_users": len(self._cache),
            "cache_ttl": self._cache_ttl,
            "cache_keys": list(self._cache.keys())
        }

    def clear_cache(self, user_id: str | None = None):
        """清理缓存"""
        if user_id:
            if user_id in self._cache:
                del self._cache[user_id]
                logger.debug(f"清理用户缓存: {user_id}")
        else:
            self._cache.clear()
            logger.debug("清理所有缓存")


# 创建全局实例
relationship_service = RelationshipService()
