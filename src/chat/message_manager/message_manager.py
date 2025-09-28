"""
消息管理模块
管理每个聊天流的上下文信息，包含历史记录和未读消息，定期检查并处理新消息
"""

import asyncio
import random
import time
import traceback
from typing import Dict, Optional, Any, TYPE_CHECKING

from src.common.logger import get_logger
from src.common.data_models.database_data_model import DatabaseMessages
from src.common.data_models.message_manager_data_model import StreamContext, MessageManagerStats, StreamStats
from src.chat.chatter_manager import ChatterManager
from src.chat.planner_actions.action_manager import ChatterActionManager
from .sleep_manager.sleep_manager import SleepManager
from .sleep_manager.wakeup_manager import WakeUpManager
from src.config.config import global_config
from src.plugin_system.apis.chat_api import get_chat_manager

if TYPE_CHECKING:
    from src.common.data_models.message_manager_data_model import StreamContext

logger = get_logger("message_manager")


class MessageManager:
    """消息管理器"""

    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval  # 检查间隔（秒）
        self.is_running = False
        self.manager_task: Optional[asyncio.Task] = None

        # 统计信息
        self.stats = MessageManagerStats()

        # 初始化chatter manager
        self.action_manager = ChatterActionManager()
        self.chatter_manager = ChatterManager(self.action_manager)

        # 初始化睡眠和唤醒管理器
        self.sleep_manager = SleepManager()
        self.wakeup_manager = WakeUpManager(self.sleep_manager)

        # 不再需要全局上下文管理器，直接通过 ChatManager 访问各个 ChatStream 的 context_manager

    async def start(self):
        """启动消息管理器"""
        if self.is_running:
            logger.warning("消息管理器已经在运行")
            return

        self.is_running = True
        self.manager_task = asyncio.create_task(self._manager_loop())
        await self.wakeup_manager.start()
        # await self.context_manager.start()  # 已删除，需要重构
        logger.info("消息管理器已启动")

    async def stop(self):
        """停止消息管理器"""
        if not self.is_running:
            return

        self.is_running = False

        # 停止所有流处理任务
        # 注意：context_manager 会自己清理任务
        if self.manager_task and not self.manager_task.done():
            self.manager_task.cancel()

        await self.wakeup_manager.stop()
        # await self.context_manager.stop()  # 已删除，需要重构

        logger.info("消息管理器已停止")

    async def add_message(self, stream_id: str, message: DatabaseMessages):
        """添加消息到指定聊天流"""
        try:
            chat_manager = get_chat_manager()
            chat_stream = chat_manager.get_stream(stream_id)
            if not chat_stream:
                logger.warning(f"MessageManager.add_message: 聊天流 {stream_id} 不存在")
                return
            success = await chat_stream.context_manager.add_message(message)
            if success:
                logger.debug(f"添加消息到聊天流 {stream_id}: {message.message_id}")
            else:
                logger.warning(f"添加消息到聊天流 {stream_id} 失败")
        except Exception as e:
            logger.error(f"添加消息到聊天流 {stream_id} 时发生错误: {e}")

    async def update_message(
        self,
        stream_id: str,
        message_id: str,
        interest_value: float = None,
        actions: list = None,
        should_reply: bool = None,
    ):
        """更新消息信息"""
        try:
            chat_manager = get_chat_manager()
            chat_stream = chat_manager.get_stream(stream_id)
            if not chat_stream:
                logger.warning(f"MessageManager.update_message: 聊天流 {stream_id} 不存在")
                return
            updates = {}
            if interest_value is not None:
                updates["interest_value"] = interest_value
            if actions is not None:
                updates["actions"] = actions
            if should_reply is not None:
                updates["should_reply"] = should_reply
            if updates:
                success = await chat_stream.context_manager.update_message(message_id, updates)
                if success:
                    logger.debug(f"更新消息 {message_id} 成功")
                else:
                    logger.warning(f"更新消息 {message_id} 失败")
        except Exception as e:
            logger.error(f"更新消息 {message_id} 时发生错误: {e}")

    async def add_action(self, stream_id: str, message_id: str, action: str):
        """添加动作到消息"""
        try:
            chat_manager = get_chat_manager()
            chat_stream = chat_manager.get_stream(stream_id)
            if not chat_stream:
                logger.warning(f"MessageManager.add_action: 聊天流 {stream_id} 不存在")
                return
            success = await chat_stream.context_manager.update_message(
                message_id, {"actions": [action]}
            )
            if success:
                logger.debug(f"为消息 {message_id} 添加动作 {action} 成功")
            else:
                logger.warning(f"为消息 {message_id} 添加动作 {action} 失败")
        except Exception as e:
            logger.error(f"为消息 {message_id} 添加动作时发生错误: {e}")

    async def _manager_loop(self):
        """管理器主循环 - 独立聊天流分发周期版本"""
        while self.is_running:
            try:
                # 更新睡眠状态
                await self.sleep_manager.update_sleep_state(self.wakeup_manager)

                # 执行独立分发周期的检查
                await self._check_streams_with_individual_intervals()

                # 计算下次检查时间（使用最小间隔或固定间隔）
                if global_config.chat.dynamic_distribution_enabled:
                    next_check_delay = self._calculate_next_manager_delay()
                else:
                    next_check_delay = self.check_interval

                await asyncio.sleep(next_check_delay)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"消息管理器循环出错: {e}")
                traceback.print_exc()

    async def _check_all_streams(self):
        """检查所有聊天流"""
        active_streams = 0
        total_unread = 0

        # 通过 ChatManager 获取所有活跃的流
        try:
            chat_manager = get_chat_manager()
            active_stream_ids = list(chat_manager.streams.keys())

            for stream_id in active_stream_ids:
                chat_stream = chat_manager.get_stream(stream_id)
                if not chat_stream:
                    continue

                # 检查流是否活跃
                context = chat_stream.stream_context
                if not context.is_active:
                    continue

                active_streams += 1

                # 检查是否有未读消息
                unread_messages = chat_stream.context_manager.get_unread_messages()
                if unread_messages:
                    total_unread += len(unread_messages)

                    # 如果没有处理任务，创建一个
                    if not hasattr(context, 'processing_task') or not context.processing_task or context.processing_task.done():
                        context.processing_task = asyncio.create_task(self._process_stream_messages(stream_id))

            # 更新统计
            self.stats.active_streams = active_streams
            self.stats.total_unread_messages = total_unread

        except Exception as e:
            logger.error(f"检查所有聊天流时发生错误: {e}")

    async def _process_stream_messages(self, stream_id: str):
        """处理指定聊天流的消息"""
        try:
            # 通过 ChatManager 获取 ChatStream
            chat_manager = get_chat_manager()
            chat_stream = chat_manager.get_stream(stream_id)
            if not chat_stream:
                logger.warning(f"处理消息失败: 聊天流 {stream_id} 不存在")
                return

            context = chat_stream.stream_context

            # 获取未读消息
            unread_messages = chat_stream.context_manager.get_unread_messages()
            if not unread_messages:
                return

            # 检查是否需要打断现有处理
            await self._check_and_handle_interruption(context, stream_id)

            # --- 睡眠状态检查 ---
            if self.sleep_manager.is_sleeping():
                logger.info(f"Bot正在睡觉，检查聊天流 {stream_id} 是否有唤醒触发器。")

                was_woken_up = False
                is_private = context.is_private_chat()

                for message in unread_messages:
                    is_mentioned = message.is_mentioned or False
                    if not is_mentioned and not is_private:
                        bot_names = [global_config.bot.nickname] + global_config.bot.alias_names
                        if any(name in message.processed_plain_text for name in bot_names):
                            is_mentioned = True
                            logger.debug(f"通过关键词 '{next((name for name in bot_names if name in message.processed_plain_text), '')}' 匹配将消息标记为 'is_mentioned'")
                    
                    if is_private or is_mentioned:
                        if self.wakeup_manager.add_wakeup_value(is_private, is_mentioned, chat_id=stream_id):
                            was_woken_up = True
                            break  # 一旦被吵醒，就跳出循环并处理消息

                if not was_woken_up:
                    logger.debug(f"聊天流 {stream_id} 中没有唤醒触发器，保持消息未读状态。")
                    return  # 退出，不处理消息

                logger.info(f"Bot被聊天流 {stream_id} 中的消息吵醒，继续处理。")
            elif self.sleep_manager.is_woken_up():
                angry_chat_id = self.wakeup_manager.angry_chat_id
                if stream_id != angry_chat_id:
                    logger.debug(f"Bot处于WOKEN_UP状态，但当前流 {stream_id} 不是触发唤醒的流 {angry_chat_id}，跳过处理。")
                    return # 退出，不处理此流的消息
                logger.info(f"Bot处于WOKEN_UP状态，处理触发唤醒的流 {stream_id}。")
            # --- 睡眠状态检查结束 ---

            logger.debug(f"开始处理聊天流 {stream_id} 的 {len(unread_messages)} 条未读消息")

            # 直接使用StreamContext对象进行处理
            if unread_messages:
                try:
                    # 记录当前chat type用于调试
                    logger.debug(f"聊天流 {stream_id} 检测到的chat type: {context.chat_type.value}")

                    # 发送到chatter manager，传递StreamContext对象
                    results = await self.chatter_manager.process_stream_context(stream_id, context)

                    # 处理结果，标记消息为已读
                    if results.get("success", False):
                        self._clear_all_unread_messages(stream_id)
                        logger.debug(f"聊天流 {stream_id} 处理成功，清除了 {len(unread_messages)} 条未读消息")
                    else:
                        logger.warning(f"聊天流 {stream_id} 处理失败: {results.get('error_message', '未知错误')}")

                except Exception as e:
                    logger.error(f"处理聊天流 {stream_id} 时发生异常，将清除所有未读消息: {e}")
                    # 出现异常时也清除未读消息，避免重复处理
                    self._clear_all_unread_messages(stream_id)
                    raise

            logger.debug(f"聊天流 {stream_id} 消息处理完成")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"处理聊天流 {stream_id} 消息时出错: {e}")
            traceback.print_exc()

    def deactivate_stream(self, stream_id: str):
        """停用聊天流"""
        try:
            # 通过 ChatManager 获取 ChatStream
            chat_manager = get_chat_manager()
            chat_stream = chat_manager.get_stream(stream_id)
            if not chat_stream:
                logger.warning(f"停用流失败: 聊天流 {stream_id} 不存在")
                return

            context = chat_stream.stream_context
            context.is_active = False

            # 取消处理任务
            if hasattr(context, 'processing_task') and context.processing_task and not context.processing_task.done():
                context.processing_task.cancel()

            logger.info(f"停用聊天流: {stream_id}")

        except Exception as e:
            logger.error(f"停用聊天流 {stream_id} 时发生错误: {e}")

    def activate_stream(self, stream_id: str):
        """激活聊天流"""
        try:
            # 通过 ChatManager 获取 ChatStream
            chat_manager = get_chat_manager()
            chat_stream = chat_manager.get_stream(stream_id)
            if not chat_stream:
                logger.warning(f"激活流失败: 聊天流 {stream_id} 不存在")
                return

            context = chat_stream.stream_context
            context.is_active = True
            logger.info(f"激活聊天流: {stream_id}")

        except Exception as e:
            logger.error(f"激活聊天流 {stream_id} 时发生错误: {e}")

    def get_stream_stats(self, stream_id: str) -> Optional[StreamStats]:
        """获取聊天流统计"""
        try:
            # 通过 ChatManager 获取 ChatStream
            chat_manager = get_chat_manager()
            chat_stream = chat_manager.get_stream(stream_id)
            if not chat_stream:
                return None

            context = chat_stream.stream_context
            unread_count = len(chat_stream.context_manager.get_unread_messages())

            return StreamStats(
                stream_id=stream_id,
                is_active=context.is_active,
                unread_count=unread_count,
                history_count=len(context.history_messages),
                last_check_time=context.last_check_time,
                has_active_task=bool(hasattr(context, 'processing_task') and context.processing_task and not context.processing_task.done()),
            )

        except Exception as e:
            logger.error(f"获取聊天流 {stream_id} 统计时发生错误: {e}")
            return None

    def get_manager_stats(self) -> Dict[str, Any]:
        """获取管理器统计"""
        return {
            "total_streams": self.stats.total_streams,
            "active_streams": self.stats.active_streams,
            "total_unread_messages": self.stats.total_unread_messages,
            "total_processed_messages": self.stats.total_processed_messages,
            "uptime": self.stats.uptime,
            "start_time": self.stats.start_time,
        }

    async def cleanup_inactive_streams(self, max_inactive_hours: int = 24):
        """清理不活跃的聊天流"""
        try:
            chat_manager = get_chat_manager()
            current_time = time.time()
            max_inactive_seconds = max_inactive_hours * 3600
            inactive_streams = []
            for stream_id, chat_stream in chat_manager.streams.items():
                if current_time - chat_stream.last_active_time > max_inactive_seconds:
                    inactive_streams.append(stream_id)
            for stream_id in inactive_streams:
                try:
                    await chat_stream.context_manager.clear_context()
                    del chat_manager.streams[stream_id]
                    logger.info(f"清理不活跃聊天流: {stream_id}")
                except Exception as e:
                    logger.error(f"清理聊天流 {stream_id} 失败: {e}")
            if inactive_streams:
                logger.info(f"已清理 {len(inactive_streams)} 个不活跃聊天流")
            else:
                logger.debug("没有需要清理的不活跃聊天流")
        except Exception as e:
            logger.error(f"清理不活跃聊天流时发生错误: {e}")

    async def _check_and_handle_interruption(self, context: StreamContext, stream_id: str):
        """检查并处理消息打断"""
        if not global_config.chat.interruption_enabled:
            return

        # 检查是否有正在进行的处理任务
        if context.processing_task and not context.processing_task.done():
            # 计算打断概率
            interruption_probability = context.calculate_interruption_probability(
                global_config.chat.interruption_max_limit, global_config.chat.interruption_probability_factor
            )

            # 检查是否已达到最大打断次数
            if context.interruption_count >= global_config.chat.interruption_max_limit:
                logger.debug(
                    f"聊天流 {stream_id} 已达到最大打断次数 {context.interruption_count}/{global_config.chat.interruption_max_limit}，跳过打断检查"
                )
                return

            # 根据概率决定是否打断
            if random.random() < interruption_probability:
                logger.info(f"聊天流 {stream_id} 触发消息打断，打断概率: {interruption_probability:.2f}")

                # 取消现有任务
                context.processing_task.cancel()
                try:
                    await context.processing_task
                except asyncio.CancelledError:
                    pass

                # 增加打断计数并应用afc阈值降低
                context.increment_interruption_count()
                context.apply_interruption_afc_reduction(global_config.chat.interruption_afc_reduction)

                # 检查是否已达到最大次数
                if context.interruption_count >= global_config.chat.interruption_max_limit:
                    logger.warning(
                        f"聊天流 {stream_id} 已达到最大打断次数 {context.interruption_count}/{global_config.chat.interruption_max_limit}，后续消息将不再打断"
                    )
                else:
                    logger.info(
                        f"聊天流 {stream_id} 已打断，当前打断次数: {context.interruption_count}/{global_config.chat.interruption_max_limit}, afc阈值调整: {context.get_afc_threshold_adjustment()}"
                    )
            else:
                logger.debug(f"聊天流 {stream_id} 未触发打断，打断概率: {interruption_probability:.2f}")

    def _calculate_stream_distribution_interval(self, context: StreamContext) -> float:
        """计算单个聊天流的分发周期 - 使用重构后的能量管理器"""
        if not global_config.chat.dynamic_distribution_enabled:
            return self.check_interval  # 使用固定间隔

        try:
            from src.chat.energy_system import energy_manager
            from src.plugin_system.apis.chat_api import get_chat_manager

            # 获取聊天流和能量
            chat_stream = get_chat_manager().get_stream(context.stream_id)
            if chat_stream:
                focus_energy = chat_stream.focus_energy
                # 使用能量管理器获取分发周期
                interval = energy_manager.get_distribution_interval(focus_energy)
                logger.debug(f"流 {context.stream_id} 分发周期: {interval:.2f}s (能量: {focus_energy:.3f})")
                return interval
            else:
                # 默认间隔
                return self.check_interval

        except Exception as e:
            logger.error(f"计算分发周期失败: {e}")
            return self.check_interval

    def _calculate_next_manager_delay(self) -> float:
        """计算管理器下次检查的延迟时间"""
        current_time = time.time()
        min_delay = float("inf")

        # 找到最近需要检查的流
        try:
            chat_manager = get_chat_manager()
            for _stream_id, chat_stream in chat_manager.streams.items():
                context = chat_stream.stream_context
                if not context or not context.is_active:
                    continue

                time_until_check = context.next_check_time - current_time
                if time_until_check > 0:
                    min_delay = min(min_delay, time_until_check)
                else:
                    min_delay = 0.1  # 立即检查
                    break

            # 如果没有活跃流，使用默认间隔
            if min_delay == float("inf"):
                return self.check_interval

            # 确保最小延迟
            return max(0.1, min(min_delay, self.check_interval))

        except Exception as e:
            logger.error(f"计算下次检查延迟时发生错误: {e}")
            return self.check_interval

    async def _check_streams_with_individual_intervals(self):
        """检查所有达到检查时间的聊天流"""
        current_time = time.time()
        processed_streams = 0

        # 通过 ChatManager 获取活跃的流
        try:
            chat_manager = get_chat_manager()
            for stream_id, chat_stream in chat_manager.streams.items():
                context = chat_stream.stream_context
                if not context or not context.is_active:
                    continue

                # 检查是否达到检查时间
                if current_time >= context.next_check_time:
                    # 更新检查时间
                    context.last_check_time = current_time

                    # 计算下次检查时间和分发周期
                    if global_config.chat.dynamic_distribution_enabled:
                        context.distribution_interval = self._calculate_stream_distribution_interval(context)
                    else:
                        context.distribution_interval = self.check_interval

                    # 设置下次检查时间
                    context.next_check_time = current_time + context.distribution_interval

                    # 检查未读消息
                    unread_messages = chat_stream.context_manager.get_unread_messages()
                    if unread_messages:
                        processed_streams += 1
                        self.stats.total_unread_messages = len(unread_messages)

                        # 如果没有处理任务，创建一个
                        if not context.processing_task or context.processing_task.done():
                            focus_energy = chat_stream.focus_energy

                            # 根据优先级记录日志
                            if focus_energy >= 0.7:
                                logger.info(
                                    f"高优先级流 {stream_id} 开始处理 | "
                                    f"focus_energy: {focus_energy:.3f} | "
                                    f"分发周期: {context.distribution_interval:.2f}s | "
                                    f"未读消息: {len(unread_messages)}"
                                )
                            else:
                                logger.debug(
                                    f"流 {stream_id} 开始处理 | "
                                    f"focus_energy: {focus_energy:.3f} | "
                                    f"分发周期: {context.distribution_interval:.2f}s"
                                )

                            context.processing_task = asyncio.create_task(self._process_stream_messages(stream_id))

        except Exception as e:
            logger.error(f"检查独立分发周期的聊天流时发生错误: {e}")

        # 更新活跃流计数
        try:
            chat_manager = get_chat_manager()
            active_count = len([s for s in chat_manager.streams.values() if s.stream_context.is_active])
            self.stats.active_streams = active_count

            if processed_streams > 0:
                logger.debug(f"本次循环处理了 {processed_streams} 个流 | 活跃流总数: {active_count}")
        except Exception as e:
            logger.error(f"更新活跃流计数时发生错误: {e}")

    async def _check_all_streams_with_priority(self):
        """按优先级检查所有聊天流，高focus_energy的流优先处理"""
        try:
            chat_manager = get_chat_manager()
            if not chat_manager.streams:
                return

            # 获取活跃的聊天流并按focus_energy排序
            active_streams = []
            for stream_id, chat_stream in chat_manager.streams.items():
                context = chat_stream.stream_context
                if not context or not context.is_active:
                    continue

                # 获取focus_energy
                focus_energy = chat_stream.focus_energy

                # 计算流优先级分数
                priority_score = self._calculate_stream_priority(context, focus_energy)
                active_streams.append((priority_score, stream_id, context))

        except Exception as e:
            logger.error(f"获取活跃流列表时发生错误: {e}")
            return

        # 按优先级降序排序
        active_streams.sort(reverse=True, key=lambda x: x[0])

        # 处理排序后的流
        active_stream_count = 0
        total_unread = 0

        for priority_score, stream_id, context in active_streams:
            active_stream_count += 1

            # 检查是否有未读消息
            try:
                chat_stream = chat_manager.get_stream(stream_id)
                if not chat_stream:
                    continue

                unread_messages = chat_stream.context_manager.get_unread_messages()
                if unread_messages:
                    total_unread += len(unread_messages)

                    # 如果没有处理任务，创建一个
                    if not hasattr(context, 'processing_task') or not context.processing_task or context.processing_task.done():
                        context.processing_task = asyncio.create_task(self._process_stream_messages(stream_id))

                        # 高优先级流的额外日志
                        if priority_score > 0.7:
                            logger.info(
                                f"高优先级流 {stream_id} 开始处理 | "
                                f"优先级: {priority_score:.3f} | "
                                f"未读消息: {len(unread_messages)}"
                            )
            except Exception as e:
                logger.error(f"处理流 {stream_id} 的未读消息时发生错误: {e}")
                continue

        # 更新统计
        self.stats.active_streams = active_stream_count
        self.stats.total_unread_messages = total_unread

    def _calculate_stream_priority(self, context: StreamContext, focus_energy: float) -> float:
        """计算聊天流的优先级分数 - 简化版本，主要使用focus_energy"""
        # 使用重构后的能量管理器，主要依赖focus_energy
        base_priority = focus_energy

        # 简单的未读消息加权
        unread_count = len(context.get_unread_messages())
        message_bonus = min(unread_count * 0.05, 0.2)  # 最多20%加成

        # 简单的时间加权
        current_time = time.time()
        time_since_active = current_time - context.last_check_time
        time_bonus = max(0, 1.0 - time_since_active / 7200.0) * 0.1  # 2小时内衰减

        final_priority = base_priority + message_bonus + time_bonus
        return max(0.0, min(1.0, final_priority))

    def _clear_all_unread_messages(self, stream_id: str):
        """清除指定上下文中的所有未读消息，防止意外情况导致消息一直未读"""
        try:
            # 通过 ChatManager 获取 ChatStream
            chat_manager = get_chat_manager()
            chat_stream = chat_manager.get_stream(stream_id)
            if not chat_stream:
                logger.warning(f"清除消息失败: 聊天流 {stream_id} 不存在")
                return

            # 获取未读消息
            unread_messages = chat_stream.context_manager.get_unread_messages()
            if not unread_messages:
                return

            logger.warning(f"正在清除 {len(unread_messages)} 条未读消息")

            # 将所有未读消息标记为已读
            message_ids = [msg.message_id for msg in unread_messages]
            success = chat_stream.context_manager.mark_messages_as_read(message_ids)

            if success:
                self.stats.total_processed_messages += len(unread_messages)
                logger.debug(f"强制清除 {len(unread_messages)} 条消息，标记为已读")
            else:
                logger.error("标记未读消息为已读失败")

        except Exception as e:
            logger.error(f"清除未读消息时发生错误: {e}")


# 创建全局消息管理器实例
message_manager = MessageManager()
