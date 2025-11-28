"""
Kokoro Flow Chatter 上下文构建器

该模块负责从 S4U 移植的所有上下文模块，为 KFC 提供"全知"Prompt所需的完整情境感知能力。
包含：
- 关系信息 (relation_info)
- 记忆块 (memory_block)
- 表达习惯 (expression_habits)
- 知识库 (knowledge)
- 跨上下文 (cross_context)
- 日程信息 (schedule)
- 通知块 (notice)
- 历史消息构建 (history)
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

from src.common.logger import get_logger
from src.config.config import global_config
from src.person_info.person_info import get_person_info_manager, PersonInfoManager

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream
    from src.common.data_models.message_manager_data_model import StreamContext
    from src.config.config import BotConfig  # 用于类型提示

logger = get_logger("kfc_context_builder")


# 类型断言辅助函数
def _get_config():
    """获取全局配置（带类型断言）"""
    assert global_config is not None, "global_config 未初始化"
    return global_config


class KFCContextBuilder:
    """
    KFC 上下文构建器
    
    从 S4U 的 DefaultReplyer 移植所有上下文构建能力，
    为 KFC 的"超融合"Prompt 提供完整的情境感知数据。
    """
    
    def __init__(self, chat_stream: "ChatStream"):
        """
        初始化上下文构建器
        
        Args:
            chat_stream: 当前聊天流
        """
        self.chat_stream = chat_stream
        self.chat_id = chat_stream.stream_id
        self.platform = chat_stream.platform
        self.is_group_chat = bool(chat_stream.group_info)
        
        # 延迟初始化的组件
        self._tool_executor: Any = None
        self._expression_selector: Any = None
    
    @property
    def tool_executor(self) -> Any:
        """延迟初始化工具执行器"""
        if self._tool_executor is None:
            from src.plugin_system.core.tool_use import ToolExecutor
            self._tool_executor = ToolExecutor(chat_id=self.chat_id)
        return self._tool_executor
    
    async def build_all_context(
        self,
        sender_name: str,
        target_message: str,
        context: Optional["StreamContext"] = None,
    ) -> dict[str, str]:
        """
        并行构建所有上下文模块
        
        Args:
            sender_name: 发送者名称
            target_message: 目标消息内容
            context: 聊天流上下文（可选）
            
        Returns:
            dict: 包含所有上下文块的字典
        """
        # 获取历史消息用于构建各种上下文
        chat_history = await self._get_chat_history_text(context)
        
        # 并行执行所有上下文构建任务
        tasks = {
            "relation_info": self._build_relation_info(sender_name, target_message),
            "memory_block": self._build_memory_block(chat_history, target_message),
            "expression_habits": self._build_expression_habits(chat_history, target_message),
            "schedule": self._build_schedule_block(),
            "time": self._build_time_block(),
        }
        
        results = {}
        try:
            task_results = await asyncio.gather(
                *[self._wrap_task(name, coro) for name, coro in tasks.items()],
                return_exceptions=True
            )
            
            for result in task_results:
                if isinstance(result, tuple):
                    name, value = result
                    results[name] = value
                else:
                    logger.warning(f"上下文构建任务异常: {result}")
        except Exception as e:
            logger.error(f"并行构建上下文失败: {e}")
        
        return results
    
    async def _wrap_task(self, name: str, coro) -> tuple[str, str]:
        """包装任务以返回名称和结果"""
        try:
            result = await coro
            return (name, result or "")
        except Exception as e:
            logger.error(f"构建 {name} 失败: {e}")
            return (name, "")
    
    async def _get_chat_history_text(
        self,
        context: Optional["StreamContext"] = None,
        limit: int = 20,
    ) -> str:
        """
        获取聊天历史文本
        
        Args:
            context: 聊天流上下文
            limit: 最大消息数量
            
        Returns:
            str: 格式化的聊天历史
        """
        if context is None:
            return ""
        
        try:
            from src.chat.utils.chat_message_builder import build_readable_messages
            
            messages = context.get_messages(limit=limit, include_unread=True)
            if not messages:
                return ""
            
            # 转换为字典格式
            msg_dicts = [msg.flatten() for msg in messages]
            
            return await build_readable_messages(
                msg_dicts,
                replace_bot_name=True,
                timestamp_mode="relative",
                truncate=True,
            )
        except Exception as e:
            logger.error(f"获取聊天历史失败: {e}")
            return ""
    
    async def _build_relation_info(self, sender_name: str, target_message: str) -> str:
        """
        构建关系信息块
        
        从 S4U 的 build_relation_info 移植
        
        Args:
            sender_name: 发送者名称
            target_message: 目标消息
            
        Returns:
            str: 格式化的关系信息
        """
        config = _get_config()
        
        # 检查是否是Bot自己的消息
        if sender_name == f"{config.bot.nickname}(你)":
            return "你将要回复的是你自己发送的消息。"
        
        person_info_manager = get_person_info_manager()
        person_id = await person_info_manager.get_person_id_by_person_name(sender_name)
        
        if not person_id:
            logger.debug(f"未找到用户 {sender_name} 的ID")
            return f"你完全不认识{sender_name}，这是你们的第一次互动。"
        
        try:
            from src.person_info.relationship_fetcher import relationship_fetcher_manager
            
            relationship_fetcher = relationship_fetcher_manager.get_fetcher(self.chat_id)
            
            # 构建用户关系信息（包含别名、偏好关键词等字段）
            user_relation_info = await relationship_fetcher.build_relation_info(person_id, points_num=5)
            
            # 构建聊天流印象信息（群聊/私聊的整体印象）
            stream_impression = await relationship_fetcher.build_chat_stream_impression(self.chat_id)
            
            # 组合信息
            parts = []
            if user_relation_info:
                parts.append(f"### 你与 {sender_name} 的关系\n{user_relation_info}")
            if stream_impression:
                scene_type = "这个群" if self.is_group_chat else "你们的私聊"
                parts.append(f"### 你对{scene_type}的印象\n{stream_impression}")
            
            if parts:
                return "\n\n".join(parts)
            else:
                return f"你与{sender_name}还没有建立深厚的关系，这是早期的互动阶段。"
                
        except Exception as e:
            logger.error(f"获取关系信息失败: {e}")
            return self._build_fallback_relation_info(sender_name, person_id)
    
    def _build_fallback_relation_info(self, sender_name: str, person_id: str) -> str:
        """降级的关系信息构建"""
        return f"你与{sender_name}是普通朋友关系。"
    
    async def _build_memory_block(self, chat_history: str, target_message: str) -> str:
        """
        构建记忆块
        
        从 S4U 的 build_memory_block 移植，使用三层记忆系统
        
        Args:
            chat_history: 聊天历史
            target_message: 目标消息
            
        Returns:
            str: 格式化的记忆信息
        """
        config = _get_config()
        
        if not (config.memory and config.memory.enable):
            return ""
        
        try:
            from src.memory_graph.manager_singleton import get_unified_memory_manager
            from src.memory_graph.utils.three_tier_formatter import memory_formatter
            
            unified_manager = get_unified_memory_manager()
            if not unified_manager:
                logger.debug("[三层记忆] 管理器未初始化")
                return ""
            
            # 使用统一管理器的智能检索
            search_result = await unified_manager.search_memories(
                query_text=target_message,
                use_judge=True,
                recent_chat_history=chat_history,
            )
            
            if not search_result:
                return ""
            
            # 分类记忆块
            perceptual_blocks = search_result.get("perceptual_blocks", [])
            short_term_memories = search_result.get("short_term_memories", [])
            long_term_memories = search_result.get("long_term_memories", [])
            
            # 使用三级记忆格式化器
            formatted_memories = await memory_formatter.format_all_tiers(
                perceptual_blocks=perceptual_blocks,
                short_term_memories=short_term_memories,
                long_term_memories=long_term_memories
            )
            
            total_count = len(perceptual_blocks) + len(short_term_memories) + len(long_term_memories)
            if total_count > 0 and formatted_memories.strip():
                logger.info(
                    f"[三层记忆] 检索到 {total_count} 条记忆 "
                    f"(感知:{len(perceptual_blocks)}, 短期:{len(short_term_memories)}, 长期:{len(long_term_memories)})"
                )
                return f"### 🧠 相关记忆\n\n{formatted_memories}"
            
            return ""
            
        except Exception as e:
            logger.error(f"[三层记忆] 检索失败: {e}")
            return ""
    
    async def _build_expression_habits(self, chat_history: str, target_message: str) -> str:
        """
        构建表达习惯块
        
        从 S4U 的 build_expression_habits 移植
        
        Args:
            chat_history: 聊天历史
            target_message: 目标消息
            
        Returns:
            str: 格式化的表达习惯
        """
        config = _get_config()
        
        # 检查是否允许使用表达
        use_expression, _, _ = config.expression.get_expression_config_for_chat(self.chat_id)
        if not use_expression:
            return ""
        
        try:
            from src.chat.express.expression_selector import expression_selector
            
            style_habits = []
            grammar_habits = []
            
            # 使用统一的表达方式选择
            selected_expressions = await expression_selector.select_suitable_expressions(
                chat_id=self.chat_id,
                chat_history=chat_history,
                target_message=target_message,
                max_num=8,
                min_num=2
            )
            
            if selected_expressions:
                for expr in selected_expressions:
                    if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                        expr_type = expr.get("type", "style")
                        habit_str = f"当{expr['situation']}时，使用 {expr['style']}"
                        if expr_type == "grammar":
                            grammar_habits.append(habit_str)
                        else:
                            style_habits.append(habit_str)
            
            # 构建表达习惯块
            parts = []
            if style_habits:
                parts.append("**语言风格习惯**：\n" + "\n".join(f"- {h}" for h in style_habits))
            if grammar_habits:
                parts.append("**句法习惯**：\n" + "\n".join(f"- {h}" for h in grammar_habits))
            
            if parts:
                return "### 💬 你的表达习惯\n\n" + "\n\n".join(parts)
            
            return ""
            
        except Exception as e:
            logger.error(f"构建表达习惯失败: {e}")
            return ""
    
    async def _build_schedule_block(self) -> str:
        """
        构建日程信息块
        
        从 S4U 移植
        
        Returns:
            str: 格式化的日程信息
        """
        config = _get_config()
        
        if not config.planning_system.schedule_enable:
            return ""
        
        try:
            from src.schedule.schedule_manager import schedule_manager
            
            activity_info = schedule_manager.get_current_activity()
            if not activity_info:
                return ""
            
            activity = activity_info.get("activity")
            time_range = activity_info.get("time_range")
            now = datetime.now()
            
            if time_range:
                try:
                    start_str, end_str = time_range.split("-")
                    start_time = datetime.strptime(start_str.strip(), "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day
                    )
                    end_time = datetime.strptime(end_str.strip(), "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day
                    )
                    
                    if end_time < start_time:
                        end_time += timedelta(days=1)
                    if now < start_time:
                        now += timedelta(days=1)
                    
                    duration_minutes = (now - start_time).total_seconds() / 60
                    remaining_minutes = (end_time - now).total_seconds() / 60
                    
                    return (
                        f"你当前正在进行「{activity}」，"
                        f"从{start_time.strftime('%H:%M')}开始，预计{end_time.strftime('%H:%M')}结束。"
                        f"已进行{duration_minutes:.0f}分钟，还剩约{remaining_minutes:.0f}分钟。"
                    )
                except (ValueError, AttributeError):
                    pass
            
            return f"你当前正在进行「{activity}」。"
            
        except Exception as e:
            logger.error(f"构建日程块失败: {e}")
            return ""
    
    async def _build_time_block(self) -> str:
        """构建时间信息块"""
        now = datetime.now()
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekdays[now.weekday()]
        
        return f"{now.strftime('%Y年%m月%d日')} {weekday} {now.strftime('%H:%M:%S')}"
    
    async def build_s4u_style_history(
        self,
        context: "StreamContext",
        max_read: int = 10,
        max_unread: int = 10,
    ) -> tuple[str, str]:
        """
        构建 S4U 风格的已读/未读历史消息
        
        从 S4U 的 build_s4u_chat_history_prompts 移植
        
        Args:
            context: 聊天流上下文
            max_read: 最大已读消息数
            max_unread: 最大未读消息数
            
        Returns:
            tuple[str, str]: (已读历史, 未读历史)
        """
        try:
            from src.chat.utils.chat_message_builder import build_readable_messages, replace_user_references_async
            
            # 确保历史消息已初始化
            await context.ensure_history_initialized()
            
            read_messages = context.history_messages
            unread_messages = context.get_unread_messages()
            
            # 构建已读历史
            read_history = ""
            if read_messages:
                read_dicts = [msg.flatten() for msg in read_messages[-max_read:]]
                read_content = await build_readable_messages(
                    read_dicts,
                    replace_bot_name=True,
                    timestamp_mode="normal_no_YMD",
                    truncate=True,
                )
                read_history = f"### 📜 已读历史消息\n{read_content}"
            
            # 构建未读历史
            unread_history = ""
            if unread_messages:
                unread_lines = []
                for msg in unread_messages[-max_unread:]:
                    msg_time = time.strftime("%H:%M:%S", time.localtime(msg.time))
                    msg_content = msg.processed_plain_text or ""
                    
                    # 获取发送者名称
                    sender_name = await self._get_sender_name(msg)
                    
                    # 处理消息内容中的用户引用
                    if msg_content:
                        msg_content = await replace_user_references_async(
                            msg_content,
                            self.platform,
                            replace_bot_name=True
                        )
                    
                    unread_lines.append(f"{msg_time} {sender_name}: {msg_content}")
                
                unread_history = f"### 📬 未读历史消息\n" + "\n".join(unread_lines)
            
            return read_history, unread_history
            
        except Exception as e:
            logger.error(f"构建S4U风格历史失败: {e}")
            return "", ""
    
    async def _get_sender_name(self, msg) -> str:
        """获取消息发送者名称"""
        config = _get_config()
        
        try:
            user_info = getattr(msg, "user_info", {})
            platform = getattr(user_info, "platform", "") or getattr(msg, "platform", "")
            user_id = getattr(user_info, "user_id", "") or getattr(msg, "user_id", "")
            
            if not (platform and user_id):
                return "未知用户"
            
            person_id = PersonInfoManager.get_person_id(platform, user_id)
            person_info_manager = get_person_info_manager()
            sender_name = await person_info_manager.get_value(person_id, "person_name") or "未知用户"
            
            # 如果是Bot自己，标记为(你)
            if user_id == str(config.bot.qq_account):
                sender_name = f"{config.bot.nickname}(你)"
            
            return sender_name
            
        except Exception:
            return "未知用户"


# 模块级便捷函数
async def build_kfc_context(
    chat_stream: "ChatStream",
    sender_name: str,
    target_message: str,
    context: Optional["StreamContext"] = None,
) -> dict[str, str]:
    """
    便捷函数：构建KFC所需的所有上下文
    
    Args:
        chat_stream: 聊天流
        sender_name: 发送者名称
        target_message: 目标消息
        context: 聊天流上下文
        
    Returns:
        dict: 包含所有上下文块的字典
    """
    builder = KFCContextBuilder(chat_stream)
    return await builder.build_all_context(sender_name, target_message, context)
