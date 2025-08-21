import asyncio
import time
import traceback
from typing import Optional, Dict, Any

from src.common.logger import get_logger
from src.config.config import global_config
from src.chat.utils.timer_calculator import Timer
from src.chat.planner_actions.planner import ActionPlanner
from src.chat.planner_actions.action_modifier import ActionModifier
from src.plugin_system.core import events_manager
from src.plugin_system.base.component_types import EventType, ChatMode
from src.mais4u.mai_think import mai_thinking_manager
from src.mais4u.constant_s4u import ENABLE_S4U
from src.chat.chat_loop.hfc_utils import send_typing, stop_typing
from .hfc_context import HfcContext
from .response_handler import ResponseHandler
from .cycle_tracker import CycleTracker

logger = get_logger("hfc.processor")

class CycleProcessor:
    def __init__(self, context: HfcContext, response_handler: ResponseHandler, cycle_tracker: CycleTracker):
        self.context = context
        self.response_handler = response_handler
        self.cycle_tracker = cycle_tracker
        self.action_planner = ActionPlanner(chat_id=self.context.stream_id, action_manager=self.context.action_manager)
        self.action_modifier = ActionModifier(action_manager=self.context.action_manager, chat_id=self.context.stream_id)

    async def observe(self, message_data: Optional[Dict[str, Any]] = None) -> bool:
        if not message_data:
            message_data = {}
        
        cycle_timers, thinking_id = self.cycle_tracker.start_cycle()
        logger.info(f"{self.context.log_prefix} 开始第{self.context.cycle_counter}次思考[模式：{self.context.loop_mode}]")

        if ENABLE_S4U:
            await send_typing()

        loop_start_time = time.time()
        
        try:
            await self.action_modifier.modify_actions()
            available_actions = self.context.action_manager.get_using_actions()
        except Exception as e:
            logger.error(f"{self.context.log_prefix} 动作修改失败: {e}")
            available_actions = {}

        is_mentioned_bot = message_data.get("is_mentioned", False)
        at_bot_mentioned = (global_config.chat.mentioned_bot_inevitable_reply and is_mentioned_bot) or \
                           (global_config.chat.at_bot_inevitable_reply and is_mentioned_bot)

        if self.context.loop_mode == ChatMode.FOCUS and at_bot_mentioned and "no_reply" in available_actions:
            available_actions = {k: v for k, v in available_actions.items() if k != "no_reply"}

        skip_planner = False
        if self.context.loop_mode == ChatMode.NORMAL:
            non_reply_actions = {k: v for k, v in available_actions.items() if k not in ["reply", "no_reply", "no_action"]}
            if not non_reply_actions:
                skip_planner = True
                plan_result = self._get_direct_reply_plan(loop_start_time)
                target_message = message_data

        gen_task = None
        if not skip_planner and self.context.loop_mode == ChatMode.NORMAL:
            reply_to_str = await self._build_reply_to_str(message_data)
            gen_task = asyncio.create_task(
                self.response_handler.generate_response(
                    message_data=message_data,
                    available_actions=available_actions,
                    reply_to=reply_to_str,
                    request_type="chat.replyer.normal",
                )
            )

        if not skip_planner:
            plan_result, target_message = await self.action_planner.plan(mode=self.context.loop_mode)

        action_result = plan_result.get("action_result", {}) if isinstance(plan_result, dict) else {}
        if not isinstance(action_result, dict):
            action_result = {}
        action_type = action_result.get("action_type", "error")
        action_data = action_result.get("action_data", {})
        reasoning = action_result.get("reasoning", "未提供理由")
        is_parallel = action_result.get("is_parallel", True)
        action_data["loop_start_time"] = loop_start_time

        is_private_chat = self.context.chat_stream.group_info is None if self.context.chat_stream else False
        if self.context.loop_mode == ChatMode.FOCUS and is_private_chat and action_type == "no_reply":
            action_type = "reply"

        if action_type == "reply":
            await self._handle_reply_action(
                message_data, available_actions, gen_task, loop_start_time, cycle_timers, thinking_id, plan_result
            )
        else:
            await self._handle_other_actions(
                action_type, reasoning, action_data, is_parallel, gen_task, target_message or message_data,
                cycle_timers, thinking_id, plan_result, loop_start_time
            )

        if ENABLE_S4U:
            await stop_typing()
        
        return True

    async def _handle_reply_action(self, message_data, available_actions, gen_task, loop_start_time, cycle_timers, thinking_id, plan_result):
        if self.context.loop_mode == ChatMode.NORMAL:
            if not gen_task:
                reply_to_str = await self._build_reply_to_str(message_data)
                gen_task = asyncio.create_task(
                    self.response_handler.generate_response(
                        message_data=message_data,
                        available_actions=available_actions,
                        reply_to=reply_to_str,
                        request_type="chat.replyer.normal",
                    )
                )
            try:
                response_set = await asyncio.wait_for(gen_task, timeout=global_config.chat.thinking_timeout)
            except asyncio.TimeoutError:
                response_set = None
        else:
            reply_to_str = await self._build_reply_to_str(message_data)
            response_set = await self.response_handler.generate_response(
                message_data=message_data,
                available_actions=available_actions,
                reply_to=reply_to_str,
                request_type="chat.replyer.focus",
            )

        if response_set:
            loop_info, _, _ = await self.response_handler.generate_and_send_reply(
                response_set, reply_to_str, loop_start_time, message_data, cycle_timers, thinking_id, plan_result
            )
            self.cycle_tracker.end_cycle(loop_info, cycle_timers)

    async def _handle_other_actions(self, action_type, reasoning, action_data, is_parallel, gen_task, action_message, cycle_timers, thinking_id, plan_result, loop_start_time):
        background_reply_task = None
        if self.context.loop_mode == ChatMode.NORMAL and is_parallel and gen_task:
            background_reply_task = asyncio.create_task(self._handle_parallel_reply(gen_task, loop_start_time, action_message, cycle_timers, thinking_id, plan_result))

        background_action_task = asyncio.create_task(self._handle_action(action_type, reasoning, action_data, cycle_timers, thinking_id, action_message))

        reply_loop_info, action_success, action_reply_text, action_command = None, False, "", ""
        
        if background_reply_task:
            results = await asyncio.gather(background_reply_task, background_action_task, return_exceptions=True)
            reply_result, action_result_val = results
            if not isinstance(reply_result, BaseException) and reply_result is not None:
                reply_loop_info, _, _ = reply_result
            else:
                reply_loop_info = None
                
            if not isinstance(action_result_val, BaseException) and action_result_val is not None:
                action_success, action_reply_text, action_command = action_result_val
            else:
                action_success, action_reply_text, action_command = False, "", ""
        else:
            results = await asyncio.gather(background_action_task, return_exceptions=True)
            if results and len(results) > 0:
                action_result_val = results[0]  # Get the actual result from the tuple
            else:
                action_result_val = (False, "", "")
            
            if not isinstance(action_result_val, BaseException) and action_result_val is not None:
                action_success, action_reply_text, action_command = action_result_val
            else:
                action_success, action_reply_text, action_command = False, "", ""

        loop_info = self._build_final_loop_info(reply_loop_info, action_success, action_reply_text, action_command, plan_result)
        self.cycle_tracker.end_cycle(loop_info, cycle_timers)

    async def _handle_parallel_reply(self, gen_task, loop_start_time, action_message, cycle_timers, thinking_id, plan_result):
        try:
            response_set = await asyncio.wait_for(gen_task, timeout=global_config.chat.thinking_timeout)
        except asyncio.TimeoutError:
            return None, "", {}
        
        if not response_set:
            return None, "", {}

        reply_to_str = await self._build_reply_to_str(action_message)
        return await self.response_handler.generate_and_send_reply(
            response_set, reply_to_str, loop_start_time, action_message, cycle_timers, thinking_id, plan_result
        )

    async def _handle_action(self, action, reasoning, action_data, cycle_timers, thinking_id, action_message) -> tuple[bool, str, str]:
        if not self.context.chat_stream:
            return False, "", ""
        try:
            action_handler = self.context.action_manager.create_action(
                action_name=action,
                action_data=action_data,
                reasoning=reasoning,
                cycle_timers=cycle_timers,
                thinking_id=thinking_id,
                chat_stream=self.context.chat_stream,
                log_prefix=self.context.log_prefix,
                action_message=action_message,
            )
            if not action_handler:
                return False, "", ""
            
            success, reply_text = await action_handler.handle_action()
            return success, reply_text, ""
        except Exception as e:
            logger.error(f"{self.context.log_prefix} 处理{action}时出错: {e}")
            traceback.print_exc()
            return False, "", ""

    def _get_direct_reply_plan(self, loop_start_time):
        return {
            "action_result": {
                "action_type": "reply",
                "action_data": {"loop_start_time": loop_start_time},
                "reasoning": "",
                "timestamp": time.time(),
                "is_parallel": False,
            },
            "action_prompt": "",
        }

    async def _build_reply_to_str(self, message_data: dict):
        from src.person_info.person_info import get_person_info_manager
        person_info_manager = get_person_info_manager()
        platform = message_data.get("chat_info_platform") or message_data.get("user_platform") or (self.context.chat_stream.platform if self.context.chat_stream else "default")
        user_id = message_data.get("user_id", "")
        person_id = person_info_manager.get_person_id(platform, user_id)
        person_name = await person_info_manager.get_value(person_id, "person_name")
        return f"{person_name}:{message_data.get('processed_plain_text')}"

    def _build_final_loop_info(self, reply_loop_info, action_success, action_reply_text, action_command, plan_result):
        if reply_loop_info:
            loop_info = reply_loop_info
            loop_info["loop_action_info"].update({
                "action_taken": action_success,
                "command": action_command,
                "taken_time": time.time(),
            })
        else:
            loop_info = {
                "loop_plan_info": {"action_result": plan_result.get("action_result", {})},
                "loop_action_info": {
                    "action_taken": action_success,
                    "reply_text": action_reply_text,
                    "command": action_command,
                    "taken_time": time.time(),
                },
            }
        return loop_info
