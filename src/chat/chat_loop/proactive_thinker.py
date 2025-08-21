import asyncio
import time
import traceback
from typing import Optional, Dict, Any, TYPE_CHECKING

from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.base.component_types import ChatMode
from .hfc_context import HfcContext

if TYPE_CHECKING:
    from .cycle_processor import CycleProcessor

logger = get_logger("hfc.proactive")

class ProactiveThinker:
    def __init__(self, context: HfcContext, cycle_processor: "CycleProcessor"):
        self.context = context
        self.cycle_processor = cycle_processor
        self._proactive_thinking_task: Optional[asyncio.Task] = None
        
        self.proactive_thinking_prompts = {
            "private": """现在你和你朋友的私聊里面已经隔了{time}没有发送消息了，请你结合上下文以及你和你朋友之前聊过的话题和你的人设来决定要不要主动发送消息，你可以选择：

            1. 继续保持沉默（当{time}以前已经结束了一个话题并且你不想挑起新话题时）
            2. 选择回复（当{time}以前你发送了一条消息且没有人回复你时、你想主动挑起一个话题时）

            请根据当前情况做出选择。如果选择回复，请直接发送你想说的内容；如果选择保持沉默，请只回复"沉默"（注意：这个词不会被发送到群聊中）。""",
            "group": """现在群里面已经隔了{time}没有人发送消息了，请你结合上下文以及群聊里面之前聊过的话题和你的人设来决定要不要主动发送消息，你可以选择：

            1. 继续保持沉默（当{time}以前已经结束了一个话题并且你不想挑起新话题时）
            2. 选择回复（当{time}以前你发送了一条消息且没有人回复你时、你想主动挑起一个话题时）

            请根据当前情况做出选择。如果选择回复，请直接发送你想说的内容；如果选择保持沉默，请只回复"沉默"（注意：这个词不会被发送到群聊中）。""",
        }

    async def start(self):
        if self.context.running and not self._proactive_thinking_task and global_config.chat.enable_proactive_thinking:
            self._proactive_thinking_task = asyncio.create_task(self._proactive_thinking_loop())
            self._proactive_thinking_task.add_done_callback(self._handle_proactive_thinking_completion)
            logger.info(f"{self.context.log_prefix} 主动思考器已启动")

    async def stop(self):
        if self._proactive_thinking_task and not self._proactive_thinking_task.done():
            self._proactive_thinking_task.cancel()
            await asyncio.sleep(0)
            logger.info(f"{self.context.log_prefix} 主动思考器已停止")

    def _handle_proactive_thinking_completion(self, task: asyncio.Task):
        try:
            if exception := task.exception():
                logger.error(f"{self.context.log_prefix} 主动思考循环异常: {exception}")
            else:
                logger.info(f"{self.context.log_prefix} 主动思考循环正常结束")
        except asyncio.CancelledError:
            logger.info(f"{self.context.log_prefix} 主动思考循环被取消")

    async def _proactive_thinking_loop(self):
        while self.context.running:
            await asyncio.sleep(15)

            if self.context.loop_mode != ChatMode.FOCUS:
                continue
            
            if not self._should_enable_proactive_thinking():
                continue

            current_time = time.time()
            silence_duration = current_time - self.context.last_message_time

            target_interval = self._get_dynamic_thinking_interval()
            
            if silence_duration >= target_interval:
                try:
                    await self._execute_proactive_thinking(silence_duration)
                    self.context.last_message_time = current_time
                except Exception as e:
                    logger.error(f"{self.context.log_prefix} 主动思考执行出错: {e}")
                    logger.error(traceback.format_exc())
    
    def _should_enable_proactive_thinking(self) -> bool:
        if not self.context.chat_stream:
            return False

        try:
            chat_id = int(self.context.stream_id.split(':')[-1])
        except (ValueError, IndexError):
            chat_id = None
        
        proactive_thinking_ids = getattr(global_config.chat, 'proactive_thinking_enable_ids', [])
        if proactive_thinking_ids and (chat_id is None or chat_id not in proactive_thinking_ids):
            return False
        
        is_group_chat = self.context.chat_stream.group_info is not None
        
        if is_group_chat and not global_config.chat.proactive_thinking_in_group:
            return False
        if not is_group_chat and not global_config.chat.proactive_thinking_in_private:
            return False
            
        return True
    
    def _get_dynamic_thinking_interval(self) -> float:
        try:
            from src.utils.timing_utils import get_normal_distributed_interval
            
            base_interval = global_config.chat.proactive_thinking_interval
            delta_sigma = getattr(global_config.chat, 'delta_sigma', 120)
            
            if base_interval < 0:
                base_interval = abs(base_interval)
            if delta_sigma < 0:
                delta_sigma = abs(delta_sigma)
            
            if base_interval == 0 and delta_sigma == 0:
                return 300
            elif base_interval == 0:
                sigma_percentage = delta_sigma / 1000
                return get_normal_distributed_interval(0, sigma_percentage, 1, 86400, use_3sigma_rule=True)
            elif delta_sigma == 0:
                return base_interval
            
            sigma_percentage = delta_sigma / base_interval
            return get_normal_distributed_interval(base_interval, sigma_percentage, 1, 86400, use_3sigma_rule=True)
            
        except ImportError:
            logger.warning(f"{self.context.log_prefix} timing_utils不可用，使用固定间隔")
            return max(300, abs(global_config.chat.proactive_thinking_interval))
        except Exception as e:
            logger.error(f"{self.context.log_prefix} 动态间隔计算出错: {e}，使用固定间隔")
            return max(300, abs(global_config.chat.proactive_thinking_interval))
    
    def _format_duration(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分")
        if secs > 0 or not parts:
            parts.append(f"{secs}秒")

        return "".join(parts)

    async def _execute_proactive_thinking(self, silence_duration: float):
        formatted_time = self._format_duration(silence_duration)
        logger.info(f"{self.context.log_prefix} 触发主动思考，已沉默{formatted_time}")

        try:
            proactive_prompt = self._get_proactive_prompt(formatted_time)

            thinking_message = {
                "processed_plain_text": proactive_prompt,
                "user_id": "system_proactive_thinking",
                "user_platform": "system",
                "timestamp": time.time(),
                "message_type": "proactive_thinking",
                "user_nickname": "系统主动思考",
                "chat_info_platform": "system",
                "message_id": f"proactive_{int(time.time())}",
            }

            logger.info(f"{self.context.log_prefix} 开始主动思考...")
            await self.cycle_processor.observe(message_data=thinking_message)
            logger.info(f"{self.context.log_prefix} 主动思考完成")

        except Exception as e:
            logger.error(f"{self.context.log_prefix} 主动思考执行异常: {e}")
            logger.error(traceback.format_exc())

    def _get_proactive_prompt(self, formatted_time: str) -> str:
        if hasattr(global_config.chat, 'proactive_thinking_prompt_template') and global_config.chat.proactive_thinking_prompt_template.strip():
            return global_config.chat.proactive_thinking_prompt_template.format(time=formatted_time)
        
        chat_type = "group" if self.context.chat_stream and self.context.chat_stream.group_info else "private"
        prompt_template = self.proactive_thinking_prompts.get(chat_type, self.proactive_thinking_prompts["group"])
        return prompt_template.format(time=formatted_time)