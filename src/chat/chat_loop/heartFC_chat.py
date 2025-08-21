import asyncio
import time
import traceback
from typing import Optional

from src.common.logger import get_logger
from src.config.config import global_config
from src.chat.message_receive.chat_stream import get_chat_manager
from src.person_info.relationship_builder_manager import relationship_builder_manager
from src.chat.express.expression_learner import expression_learner_manager
from src.plugin_system.base.component_types import ChatMode
from src.manager.schedule_manager import schedule_manager
from src.plugin_system.apis import message_api

from .hfc_context import HfcContext
from .energy_manager import EnergyManager
from .proactive_thinker import ProactiveThinker
from .cycle_processor import CycleProcessor
from .response_handler import ResponseHandler
from .normal_mode_handler import NormalModeHandler
from .cycle_tracker import CycleTracker

logger = get_logger("hfc")

class HeartFChatting:
    def __init__(self, chat_id: str):
        self.context = HfcContext(chat_id)
        
        self.cycle_tracker = CycleTracker(self.context)
        self.response_handler = ResponseHandler(self.context)
        self.cycle_processor = CycleProcessor(self.context, self.response_handler, self.cycle_tracker)
        self.energy_manager = EnergyManager(self.context)
        self.proactive_thinker = ProactiveThinker(self.context, self.cycle_processor)
        self.normal_mode_handler = NormalModeHandler(self.context, self.cycle_processor)
        
        self._loop_task: Optional[asyncio.Task] = None
        
        self._initialize_chat_mode()
        logger.info(f"{self.context.log_prefix} HeartFChatting 初始化完成")

    def _initialize_chat_mode(self):
        is_group_chat = self.context.chat_stream.group_info is not None if self.context.chat_stream else False
        if is_group_chat and global_config.chat.group_chat_mode != "auto":
            if global_config.chat.group_chat_mode == "focus":
                self.context.loop_mode = ChatMode.FOCUS
                self.context.energy_value = 35
            elif global_config.chat.group_chat_mode == "normal":
                self.context.loop_mode = ChatMode.NORMAL
                self.context.energy_value = 15

    async def start(self):
        if self.context.running:
            return
        self.context.running = True
        
        self.context.relationship_builder = relationship_builder_manager.get_or_create_builder(self.context.stream_id)
        self.context.expression_learner = expression_learner_manager.get_expression_learner(self.context.stream_id)

        await self.energy_manager.start()
        await self.proactive_thinker.start()
        
        self._loop_task = asyncio.create_task(self._main_chat_loop())
        self._loop_task.add_done_callback(self._handle_loop_completion)
        logger.info(f"{self.context.log_prefix} HeartFChatting 启动完成")

    async def stop(self):
        if not self.context.running:
            return
        self.context.running = False
        
        await self.energy_manager.stop()
        await self.proactive_thinker.stop()
        
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            await asyncio.sleep(0)
        logger.info(f"{self.context.log_prefix} HeartFChatting 已停止")

    def _handle_loop_completion(self, task: asyncio.Task):
        try:
            if exception := task.exception():
                logger.error(f"{self.context.log_prefix} HeartFChatting: 脱离了聊天(异常): {exception}")
                logger.error(traceback.format_exc())
            else:
                logger.info(f"{self.context.log_prefix} HeartFChatting: 脱离了聊天 (外部停止)")
        except asyncio.CancelledError:
            logger.info(f"{self.context.log_prefix} HeartFChatting: 结束了聊天")

    async def _main_chat_loop(self):
        try:
            while self.context.running:
                await self._loop_body()
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info(f"{self.context.log_prefix} 麦麦已关闭聊天")
        except Exception:
            logger.error(f"{self.context.log_prefix} 麦麦聊天意外错误，将于3s后尝试重新启动")
            print(traceback.format_exc())
            await asyncio.sleep(3)
            self._loop_task = asyncio.create_task(self._main_chat_loop())
        logger.error(f"{self.context.log_prefix} 结束了当前聊天循环")

    async def _loop_body(self):
        if schedule_manager.is_sleeping():
            return

        recent_messages = message_api.get_messages_by_time_in_chat(
            chat_id=self.context.stream_id,
            start_time=self.context.last_read_time,
            end_time=time.time(),
            limit=10,
            limit_mode="latest",
            filter_mai=True,
            filter_command=True,
        )
        
        if recent_messages:
            self.context.last_message_time = time.time()
            self.context.last_read_time = time.time()

        if self.context.loop_mode == ChatMode.FOCUS:
            if recent_messages:
                await self.cycle_processor.observe()
            self._check_focus_exit()
        elif self.context.loop_mode == ChatMode.NORMAL:
            self._check_focus_entry(len(recent_messages))
            if recent_messages:
                for message in recent_messages:
                    await self.normal_mode_handler.handle_message(message)

    def _check_focus_exit(self):
        is_private_chat = self.context.chat_stream.group_info is None if self.context.chat_stream else False
        is_group_chat = not is_private_chat

        if global_config.chat.force_focus_private and is_private_chat:
            if self.context.energy_value <= 1:
                self.context.energy_value = 5
            return

        if is_group_chat and global_config.chat.group_chat_mode == "focus":
            return

        if self.context.energy_value <= 1:
            self.context.energy_value = 1
            self.context.loop_mode = ChatMode.NORMAL

    def _check_focus_entry(self, new_message_count: int):
        is_private_chat = self.context.chat_stream.group_info is None if self.context.chat_stream else False
        is_group_chat = not is_private_chat

        if global_config.chat.force_focus_private and is_private_chat:
            self.context.loop_mode = ChatMode.FOCUS
            self.context.energy_value = 10
            return

        if is_group_chat and global_config.chat.group_chat_mode == "normal":
            return
        
        if global_config.chat.focus_value != 0:
            if new_message_count > 3 / pow(global_config.chat.focus_value, 0.5):
                self.context.loop_mode = ChatMode.FOCUS
                self.context.energy_value = 10 + (new_message_count / (3 / pow(global_config.chat.focus_value, 0.5))) * 10
                return

            if self.context.energy_value >= 30:
                self.context.loop_mode = ChatMode.FOCUS
