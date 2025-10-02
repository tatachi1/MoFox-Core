from typing import Optional

from maim_message import UserInfo

from src.chat.memory_system.memory_manager import MemoryManager
from src.common.logger import get_logger
from src.plugin_system.apis import chat_api, person_api, schedule_api, send_api, llm_api

logger = get_logger(__name__)


class ProactiveThinkerExecutor:
    """
    主动思考执行器，负责生成并发送主动消息。
    """

    def __init__(self):
        self.memory_manager = MemoryManager()

    async def _generate_prompt(self, stream_id: str) -> Optional[str]:
        """
        根据聊天流信息，生成包含记忆、日程和个人信息的提示词。
        """
        # 1. 获取用户信息
        stream = chat_api.get_stream_by_stream_id(stream_id)
        if not stream:
            logger.warning(f"无法找到 stream_id 为 {stream_id} 的聊天流")
            return None

        user_info = stream.user_info
        person_id = person_api.get_person_id(user_info.platform, int(user_info.user_id))

        # 2. 获取记忆
        memories = await self.memory_manager.get_memories(person_id)
        memory_context = "\n".join([f"- {m.content}" for m in memories])

        # 3. 获取日程
        schedules = await schedule_api.get_today_schedule(person_id)
        schedule_context = "\n".join([f"- {s.title} ({s.start_time}-{s.end_time})" for s in schedules])

        # 4. 构建提示词
        prompt = f"""
        # Context
        ## Memory
        {memory_context}

        ## Schedule
        {schedule_context}

        # Task
        You are a proactive assistant. Based on the user's memory and schedule, initiate a conversation.
        """
        return prompt

    async def execute_cold_start(self, user_info: UserInfo):
        """
        为新用户执行“破冰”操作。
        """
        logger.info(f"为新用户 {user_info.user_id} 执行“破冰”操作")
        prompt = f"You are a proactive assistant. Initiate a conversation with a new friend named {user_info.user_nickname}."
        
        response = await llm_api.generate(prompt)
        await send_api.send_message(user_info.platform, user_info.user_id, response)

    async def execute_wakeup(self, stream_id: str):
        """
        为已冷却的聊天执行“唤醒”操作。
        """
        logger.info(f"为聊天流 {stream_id} 执行“唤醒”操作")
        prompt = await self._generate_prompt(stream_id)
        if not prompt:
            return

        response = await llm_api.generate(prompt)
        
        stream = chat_api.get_stream_by_stream_id(stream_id)
        await send_api.send_message(stream.user_info.platform, stream.user_info.user_id, response)
