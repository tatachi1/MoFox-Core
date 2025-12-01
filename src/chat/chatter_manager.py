import asyncio
import time
from typing import TYPE_CHECKING, Any

from src.chat.planner_actions.action_manager import ChatterActionManager
from src.common.logger import get_logger
from src.plugin_system.base.base_chatter import BaseChatter
from src.plugin_system.base.component_types import ChatType

if TYPE_CHECKING:
    from src.common.data_models.message_manager_data_model import StreamContext

logger = get_logger("chatter_manager")


class ChatterManager:
    def __init__(self, action_manager: ChatterActionManager):
        self.action_manager = action_manager
        self.chatter_classes: dict[ChatType, list[type]] = {}
        self.instances: dict[str, BaseChatter] = {}
        self._auto_registered = False

        # 管理器统计
        self.stats = {
            "chatters_registered": 0,
            "streams_processed": 0,
            "successful_executions": 0,
            "failed_executions": 0,
        }

    def _auto_register_from_component_registry(self):
        """从组件注册表自动注册已注册的chatter组件"""
        try:
            from src.plugin_system.core.component_registry import component_registry

            # 获取所有CHATTER类型的组件
            chatter_components = component_registry.get_enabled_chatter_registry()
            for chatter_name, chatter_class in chatter_components.items():
                self.register_chatter(chatter_class)
                logger.info(f"自动注册chatter组件: {chatter_name}")
        except Exception as e:
            logger.warning(f"自动注册chatter组件时发生错误: {e}")

    def _ensure_chatter_registry(self):
        """确保聊天处理器注册表已初始化"""
        if not self.chatter_classes and not self._auto_registered:
            self._auto_register_from_component_registry()
            self._auto_registered = True

    def register_chatter(self, chatter_class: type):
        """注册聊天处理器类"""
        for chat_type in chatter_class.chat_types:
            if chat_type not in self.chatter_classes:
                self.chatter_classes[chat_type] = []
            self.chatter_classes[chat_type].append(chatter_class)
            logger.info(f"注册聊天处理器 {chatter_class.__name__} 支持 {chat_type.value} 聊天类型")

        self.stats["chatters_registered"] += 1

    def get_chatter_class_for_chat_type(self, chat_type: ChatType) -> type | None:
        """
        获取指定聊天类型的最佳聊天处理器类
        
        优先级规则：
        1. 优先选择明确匹配当前聊天类型的 Chatter（如 PRIVATE 或 GROUP）
        2. 如果没有精确匹配，才使用 ALL 类型的 Chatter
        
        Args:
            chat_type: 聊天类型
            
        Returns:
            最佳匹配的聊天处理器类，如果没有匹配则返回 None
        """
        # 1. 首先尝试精确匹配（排除 ALL 类型）
        if chat_type != ChatType.ALL and chat_type in self.chatter_classes:
            chatter_list = self.chatter_classes[chat_type]
            if chatter_list:
                logger.debug(f"找到精确匹配的聊天处理器: {chatter_list[0].__name__} for {chat_type.value}")
                return chatter_list[0]
        
        # 2. 如果没有精确匹配，回退到 ALL 类型
        if ChatType.ALL in self.chatter_classes:
            chatter_list = self.chatter_classes[ChatType.ALL]
            if chatter_list:
                logger.debug(f"使用通用聊天处理器: {chatter_list[0].__name__} for {chat_type.value}")
                return chatter_list[0]
        
        return None

    def get_chatter_class(self, chat_type: ChatType) -> type | None:
        """获取指定聊天类型的聊天处理器类（兼容旧接口）"""
        return self.get_chatter_class_for_chat_type(chat_type)

    def get_supported_chat_types(self) -> list[ChatType]:
        """获取支持的聊天类型列表"""
        return list(self.chatter_classes.keys())

    def get_registered_chatters(self) -> dict[ChatType, list[type]]:
        """获取已注册的聊天处理器"""
        return self.chatter_classes.copy()

    def get_stream_instance(self, stream_id: str) -> BaseChatter | None:
        """获取指定流的聊天处理器实例"""
        return self.instances.get(stream_id)

    def cleanup_inactive_instances(self, max_inactive_minutes: int = 60):
        """清理不活跃的实例"""
        current_time = time.time()
        max_inactive_seconds = max_inactive_minutes * 60

        inactive_streams = []
        for stream_id, instance in self.instances.items():
            if hasattr(instance, "get_activity_time"):
                activity_time = getattr(instance, "get_activity_time")()
                if (current_time - activity_time) > max_inactive_seconds:
                    inactive_streams.append(stream_id)

        for stream_id in inactive_streams:
            del self.instances[stream_id]
            logger.info(f"清理不活跃聊天流实例: {stream_id}")

    def _schedule_unread_cleanup(self, stream_id: str):
        """异步清理未读消息计数"""
        try:
            from src.chat.message_manager.message_manager import message_manager
        except Exception as import_error:
            logger.error("加载 message_manager 失败", stream_id=stream_id, error=import_error)
            return

        async def _clear_unread():
            try:
                await message_manager.clear_stream_unread_messages(stream_id)
                logger.debug("清理未读消息完成", stream_id=stream_id)
            except Exception as clear_error:
                logger.error("清理未读消息失败", stream_id=stream_id, error=clear_error)

        try:
            asyncio.create_task(_clear_unread(), name=f"clear-unread-{stream_id}")
        except RuntimeError as runtime_error:
            logger.error("schedule unread cleanup failed", stream_id=stream_id, error=runtime_error)

    async def process_stream_context(self, stream_id: str, context: "StreamContext") -> dict:
        """
        处理流上下文
        
        每个聊天流只能有一个活跃的 Chatter 组件。
        选择优先级：明确指定聊天类型的 Chatter > ALL 类型的 Chatter
        """
        chat_type = context.chat_type
        chat_type_value = chat_type.value
        logger.debug("处理流上下文", stream_id=stream_id, chat_type=chat_type_value)

        self._ensure_chatter_registry()

        # 检查是否已有该流的 Chatter 实例
        stream_instance = self.instances.get(stream_id)
        
        if stream_instance is None:
            # 使用新的优先级选择逻辑获取最佳 Chatter 类
            chatter_class = self.get_chatter_class_for_chat_type(chat_type)
            
            if not chatter_class:
                raise ValueError(f"No chatter registered for chat type {chat_type}")

            # 创建新实例
            stream_instance = chatter_class(stream_id=stream_id, action_manager=self.action_manager)
            self.instances[stream_id] = stream_instance
            logger.info(
                "创建聊天处理器实例",
                stream_id=stream_id,
                chatter_class=chatter_class.__name__,
                chat_type=chat_type_value,
            )
        else:
            # 已有实例，直接使用（每个流只有一个活跃的 Chatter）
            logger.debug(
                "使用已有聊天处理器实例",
                stream_id=stream_id,
                chatter_class=stream_instance.__class__.__name__,
            )

        self.stats["streams_processed"] += 1
        try:
            result = await stream_instance.execute(context)
            success = result.get("success", False)

            if success:
                self.stats["successful_executions"] += 1
                self._schedule_unread_cleanup(stream_id)
            else:
                self.stats["failed_executions"] += 1
                logger.warning("聊天处理器执行失败", stream_id=stream_id)

            actions_count = result.get("actions_count", 0)
            logger.debug(
                "聊天处理器执行完成",
                stream_id=stream_id,
                success=success,
                actions_count=actions_count,
            )

            return result
        except asyncio.CancelledError:
            self.stats["failed_executions"] += 1
            logger.info("流处理被取消", stream_id=stream_id)
            context.triggering_user_id = None
            context.processing_message_id = None
            raise
        except Exception as e:  # noqa: BLE001
            self.stats["failed_executions"] += 1
            logger.error("处理流时出错", stream_id=stream_id, error=e)
            context.triggering_user_id = None
            context.processing_message_id = None
            raise
        finally:
            context.triggering_user_id = None

    def get_stats(self) -> dict[str, Any]:
        """获取管理器统计信息"""
        stats = self.stats.copy()
        stats["active_instances"] = len(self.instances)
        stats["registered_chatter_types"] = len(self.chatter_classes)
        return stats

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "chatters_registered": 0,
            "streams_processed": 0,
            "successful_executions": 0,
            "failed_executions": 0,
        }
