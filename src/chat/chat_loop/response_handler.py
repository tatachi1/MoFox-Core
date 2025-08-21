import time
import random
import traceback
from typing import Optional, Dict, Any, List, Tuple

from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.apis import generator_api, send_api, message_api, database_api
from src.person_info.person_info import get_person_info_manager
from .hfc_context import HfcContext

logger = get_logger("hfc.response")

class ResponseHandler:
    def __init__(self, context: HfcContext):
        self.context = context

    async def generate_and_send_reply(
        self,
        response_set,
        reply_to_str,
        loop_start_time,
        action_message,
        cycle_timers: Dict[str, float],
        thinking_id,
        plan_result,
    ) -> Tuple[Dict[str, Any], str, Dict[str, float]]:
        reply_text = await self._send_response(response_set, reply_to_str, loop_start_time, action_message)

        person_info_manager = get_person_info_manager()
        
        platform = "default"
        if self.context.chat_stream:
            platform = (
                action_message.get("chat_info_platform") or action_message.get("user_platform") or self.context.chat_stream.platform
            )

        user_id = action_message.get("user_id", "")
        person_id = person_info_manager.get_person_id(platform, user_id)
        person_name = await person_info_manager.get_value(person_id, "person_name")
        action_prompt_display = f"你对{person_name}进行了回复：{reply_text}"

        await database_api.store_action_info(
            chat_stream=self.context.chat_stream,
            action_build_into_prompt=False,
            action_prompt_display=action_prompt_display,
            action_done=True,
            thinking_id=thinking_id,
            action_data={"reply_text": reply_text, "reply_to": reply_to_str},
            action_name="reply",
        )

        loop_info: Dict[str, Any] = {
            "loop_plan_info": {
                "action_result": plan_result.get("action_result", {}),
            },
            "loop_action_info": {
                "action_taken": True,
                "reply_text": reply_text,
                "command": "",
                "taken_time": time.time(),
            },
        }

        return loop_info, reply_text, cycle_timers

    async def _send_response(self, reply_set, reply_to, thinking_start_time, message_data) -> str:
        current_time = time.time()
        new_message_count = message_api.count_new_messages(
            chat_id=self.context.stream_id, start_time=thinking_start_time, end_time=current_time
        )
        platform = message_data.get("user_platform", "")
        user_id = message_data.get("user_id", "")
        reply_to_platform_id = f"{platform}:{user_id}"

        need_reply = new_message_count >= random.randint(2, 4)

        reply_text = ""
        is_proactive_thinking = message_data.get("message_type") == "proactive_thinking"

        first_replied = False
        for reply_seg in reply_set:
            # 调试日志：验证reply_seg的格式
            logger.debug(f"Processing reply_seg type: {type(reply_seg)}, content: {reply_seg}")
            
            # 修正：正确处理元组格式 (格式为: (type, content))
            if isinstance(reply_seg, tuple) and len(reply_seg) >= 2:
                reply_type, data = reply_seg
            else:
                # 向下兼容：如果已经是字符串，则直接使用
                data = str(reply_seg)
                reply_type = "text"
            
            reply_text += data

            if is_proactive_thinking and data.strip() == "沉默":
                logger.info(f"{self.context.log_prefix} 主动思考决定保持沉默，不发送消息")
                continue

            if not first_replied:
                if need_reply:
                    await send_api.text_to_stream(
                        text=data,
                        stream_id=self.context.stream_id,
                        reply_to=reply_to,
                        reply_to_platform_id=reply_to_platform_id,
                        typing=False,
                    )
                else:
                    await send_api.text_to_stream(
                        text=data,
                        stream_id=self.context.stream_id,
                        reply_to_platform_id=reply_to_platform_id,
                        typing=False,
                    )
                first_replied = True
            else:
                await send_api.text_to_stream(
                    text=data,
                    stream_id=self.context.stream_id,
                    reply_to_platform_id=reply_to_platform_id,
                    typing=True,
                )

        return reply_text

    async def generate_response(
        self,
        message_data: dict,
        available_actions: Optional[Dict[str, Any]],
        reply_to: str,
        request_type: str = "chat.replyer.normal",
    ) -> Optional[list]:
        try:
            success, reply_set, _ = await generator_api.generate_reply(
                chat_stream=self.context.chat_stream,
                reply_to=reply_to,
                available_actions=available_actions,
                enable_tool=global_config.tool.enable_tool,
                request_type=request_type,
                from_plugin=False,
            )

            if not success or not reply_set:
                logger.info(f"对 {message_data.get('processed_plain_text')} 的回复生成失败")
                return None

            return reply_set

        except Exception as e:
            logger.error(f"{self.context.log_prefix}回复生成出现错误：{str(e)} {traceback.format_exc()}")
            return None