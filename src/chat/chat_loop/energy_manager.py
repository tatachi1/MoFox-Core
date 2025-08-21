import asyncio
import time
from typing import Optional
from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.base.component_types import ChatMode
from .hfc_context import HfcContext

logger = get_logger("hfc.energy")

class EnergyManager:
    def __init__(self, context: HfcContext):
        self.context = context
        self._energy_task: Optional[asyncio.Task] = None
        self.last_energy_log_time = 0
        self.energy_log_interval = 90

    async def start(self):
        if self.context.running and not self._energy_task:
            self._energy_task = asyncio.create_task(self._energy_loop())
            self._energy_task.add_done_callback(self._handle_energy_completion)
            logger.info(f"{self.context.log_prefix} 能量管理器已启动")

    async def stop(self):
        if self._energy_task and not self._energy_task.done():
            self._energy_task.cancel()
            await asyncio.sleep(0)
            logger.info(f"{self.context.log_prefix} 能量管理器已停止")

    def _handle_energy_completion(self, task: asyncio.Task):
        try:
            if exception := task.exception():
                logger.error(f"{self.context.log_prefix} 能量循环异常: {exception}")
            else:
                logger.info(f"{self.context.log_prefix} 能量循环正常结束")
        except asyncio.CancelledError:
            logger.info(f"{self.context.log_prefix} 能量循环被取消")

    async def _energy_loop(self):
        while self.context.running:
            await asyncio.sleep(10)

            if not self.context.chat_stream:
                continue

            is_group_chat = self.context.chat_stream.group_info is not None
            if is_group_chat and global_config.chat.group_chat_mode != "auto":
                if global_config.chat.group_chat_mode == "focus":
                    self.context.loop_mode = ChatMode.FOCUS
                    self.context.energy_value = 35
                elif global_config.chat.group_chat_mode == "normal":
                    self.context.loop_mode = ChatMode.NORMAL
                    self.context.energy_value = 15
                continue

            if self.context.loop_mode == ChatMode.NORMAL:
                self.context.energy_value -= 0.3
                self.context.energy_value = max(self.context.energy_value, 0.3)
            if self.context.loop_mode == ChatMode.FOCUS:
                self.context.energy_value -= 0.6
                self.context.energy_value = max(self.context.energy_value, 0.3)
            
            self._log_energy_change("能量值衰减")

    def _should_log_energy(self) -> bool:
        current_time = time.time()
        if current_time - self.last_energy_log_time >= self.energy_log_interval:
            self.last_energy_log_time = current_time
            return True
        return False

    def _log_energy_change(self, action: str, reason: str = ""):
        if self._should_log_energy():
            log_message = f"{self.context.log_prefix} {action}，当前能量值：{self.context.energy_value:.1f}"
            if reason:
                log_message = f"{self.context.log_prefix} {action}，{reason}，当前能量值：{self.context.energy_value:.1f}"
            logger.info(log_message)
        else:
            log_message = f"{self.context.log_prefix} {action}，当前能量值：{self.context.energy_value:.1f}"
            if reason:
                log_message = f"{self.context.log_prefix} {action}，{reason}，当前能量值：{self.context.energy_value:.1f}"
            logger.debug(log_message)