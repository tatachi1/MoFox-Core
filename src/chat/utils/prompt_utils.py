"""
共享提示词工具模块 - 消除重复代码
提供统一的工具函数供DefaultReplyer和SmartPrompt使用
"""

import re
import time
from typing import Dict, Any, Optional, Tuple

from src.common.logger import get_logger
from src.config.config import global_config
from src.chat.utils.chat_message_builder import (
    get_raw_msg_before_timestamp_with_chat,
    build_readable_messages_with_id,
)
from src.chat.message_receive.chat_stream import get_chat_manager
from src.person_info.person_info import get_person_info_manager

logger = get_logger("prompt_utils")


class PromptUtils:
    """提示词工具类 - 提供共享功能，移除缓存相关功能和依赖检查"""

    @staticmethod
    def parse_reply_target(target_message: str) -> Tuple[str, str]:
        """
        解析回复目标消息 - 统一实现

        Args:
            target_message: 目标消息，格式为 "发送者:消息内容" 或 "发送者：消息内容"

        Returns:
            Tuple[str, str]: (发送者名称, 消息内容)
        """
        sender = ""
        target = ""

        # 添加None检查，防止NoneType错误
        if target_message is None:
            return sender, target

        if ":" in target_message or "：" in target_message:
            # 使用正则表达式匹配中文或英文冒号
            parts = re.split(pattern=r"[:：]", string=target_message, maxsplit=1)
            if len(parts) == 2:
                sender = parts[0].strip()
                target = parts[1].strip()
        return sender, target

    @staticmethod
    async def build_relation_info(chat_id: str, reply_to: str) -> str:
        """
        构建关系信息 - 统一实现

        Args:
            chat_id: 聊天ID
            reply_to: 回复目标字符串

        Returns:
            str: 关系信息字符串
        """
        if not global_config.relationship.enable_relationship:
            return ""

        from src.person_info.relationship_fetcher import relationship_fetcher_manager

        relationship_fetcher = relationship_fetcher_manager.get_fetcher(chat_id)

        if not reply_to:
            return ""
        sender, text = PromptUtils.parse_reply_target(reply_to)
        if not sender or not text:
            return ""

        # 获取用户ID
        person_info_manager = get_person_info_manager()
        person_id = person_info_manager.get_person_id_by_person_name(sender)
        if not person_id:
            logger.warning(f"未找到用户 {sender} 的ID，跳过信息提取")
            return f"你完全不认识{sender}，不理解ta的相关信息。"

        return await relationship_fetcher.build_relation_info(person_id, points_num=5)

    @staticmethod
    async def build_cross_context(
        chat_id: str, target_user_info: Optional[Dict[str, Any]], current_prompt_mode: str
    ) -> str:
        """
        构建跨群聊上下文 - 统一实现，完全继承DefaultReplyer功能

        Args:
            chat_id: 当前聊天ID
            target_user_info: 目标用户信息
            current_prompt_mode: 当前提示模式

        Returns:
            str: 跨群上下文块
        """
        if not global_config.cross_context.enable:
            return ""

        # 找到当前群聊所在的共享组
        target_group = None
        current_stream = get_chat_manager().get_stream(chat_id)
        if not current_stream or not current_stream.group_info:
            return ""

        try:
            current_chat_raw_id = current_stream.group_info.group_id
        except Exception as e:
            logger.error(f"获取群聊ID失败: {e}")
            return ""

        for group in global_config.cross_context.groups:
            if str(current_chat_raw_id) in group.chat_ids:
                target_group = group
                break

        if not target_group:
            return ""

        # 根据prompt_mode选择策略
        other_chat_raw_ids = [chat_id for chat_id in target_group.chat_ids if chat_id != str(current_chat_raw_id)]

        cross_context_messages = []

        if current_prompt_mode == "normal":
            # normal模式：获取其他群聊的最近N条消息
            for chat_raw_id in other_chat_raw_ids:
                stream_id = get_chat_manager().get_stream_id(current_stream.platform, chat_raw_id, is_group=True)
                if not stream_id:
                    continue

                try:
                    messages = get_raw_msg_before_timestamp_with_chat(
                        chat_id=stream_id,
                        timestamp=time.time(),
                        limit=5,  # 可配置
                    )
                    if messages:
                        chat_name = get_chat_manager().get_stream_name(stream_id) or stream_id
                        formatted_messages, _ = build_readable_messages_with_id(messages, timestamp_mode="relative")
                        cross_context_messages.append(f'[以下是来自"{chat_name}"的近期消息]\n{formatted_messages}')
                except Exception as e:
                    logger.error(f"获取群聊{chat_raw_id}的消息失败: {e}")
                    continue

        elif current_prompt_mode == "s4u":
            # s4u模式：获取当前发言用户在其他群聊的消息
            if target_user_info:
                user_id = target_user_info.get("user_id")

                if user_id:
                    for chat_raw_id in other_chat_raw_ids:
                        stream_id = get_chat_manager().get_stream_id(
                            current_stream.platform, chat_raw_id, is_group=True
                        )
                        if not stream_id:
                            continue

                        try:
                            messages = get_raw_msg_before_timestamp_with_chat(
                                chat_id=stream_id,
                                timestamp=time.time(),
                                limit=20,  # 获取更多消息以供筛选
                            )
                            user_messages = [msg for msg in messages if msg.get("user_id") == user_id][
                                -5:
                            ]  # 筛选并取最近5条

                            if user_messages:
                                chat_name = get_chat_manager().get_stream_name(stream_id) or stream_id
                                user_name = (
                                    target_user_info.get("person_name")
                                    or target_user_info.get("user_nickname")
                                    or user_id
                                )
                                formatted_messages, _ = build_readable_messages_with_id(
                                    user_messages, timestamp_mode="relative"
                                )
                                cross_context_messages.append(
                                    f'[以下是"{user_name}"在"{chat_name}"的近期发言]\n{formatted_messages}'
                                )
                        except Exception as e:
                            logger.error(f"获取用户{user_id}在群聊{chat_raw_id}的消息失败: {e}")
                            continue

        if not cross_context_messages:
            return ""

        return "# 跨群上下文参考\n" + "\n\n".join(cross_context_messages) + "\n"

    @staticmethod
    def parse_reply_target_id(reply_to: str) -> str:
        """
        解析回复目标中的用户ID

        Args:
            reply_to: 回复目标字符串

        Returns:
            str: 用户ID
        """
        if not reply_to:
            return ""

        # 复用parse_reply_target方法的逻辑
        sender, _ = PromptUtils.parse_reply_target(reply_to)
        if not sender:
            return ""

        # 获取用户ID
        person_info_manager = get_person_info_manager()
        person_id = person_info_manager.get_person_id_by_person_name(sender)
        if person_id:
            user_id = person_info_manager.get_value_sync(person_id, "user_id")
            return str(user_id) if user_id else ""

        return ""
