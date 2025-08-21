# mmc/src/schedule/plan_generator.py

import json
import random
from typing import List
from src.config.config import global_config, model_config
from src.llm_models.model_client.base_client import client_registry
from src.llm_models.payload_content.message import Message, RoleType
from src.llm_models.payload_content.resp_format import RespFormat, RespFormatType
from src.common.logger import get_logger

logger = get_logger("plan_generator")

class PlanGenerator:
    """
    负责生成月度计划。
    """

    def __init__(self):
        self.bot_personality = self._get_bot_personality()

    def _get_bot_personality(self) -> str:
        """
        从全局配置中获取Bot的人设描述。
        """
        core = global_config.personality.personality_core or ""
        side = global_config.personality.personality_side or ""
        identity = global_config.personality.identity or ""
        return f"核心人设: {core}\n侧面人设: {side}\n身份设定: {identity}"

    def _build_prompt(self, year: int, month: int, count: int) -> str:
        """
        构建用于生成月度计划的Prompt。
        """
        prompt_template = f"""
        你是一个富有想象力的助手，你的任务是为一位虚拟角色生成月度计划。
        
        **角色设定:**
        ---
        {self.bot_personality}
        ---

        请为即将到来的 **{year}年{month}月** 设计 **{count}** 个符合该角色身份的、独立的、积极向上的月度计划或小目标。

        **要求:**
        1.  每个计划都应简短、清晰，用一两句话描述。
        2.  语言风格必须自然、口语化，严格符合角色的性格设定。
        3.  计划内容要具有创造性，避免陈词滥调。
        4.  请以严格的JSON格式返回，格式为：{{"plans": ["计划一", "计划二", ...]}}
        5.  除了JSON对象，不要包含任何额外的解释、注释或前后导语。
        """
        return prompt_template.strip()

    async def generate_plans(self, year: int, month: int, count: int) -> List[str]:
        """
        调用LLM生成指定月份的计划。

        :param year: 年份
        :param month: 月份
        :param count: 需要生成的计划数量
        :return: 生成的计划文本列表
        """
        try:
            # 1. 获取模型任务配置
            task_config = model_config.model_task_config.get_task("monthly_plan_generator")
            
            # 2. 随机选择一个模型
            model_name = random.choice(task_config.model_list)
            model_info = model_config.get_model_info(model_name)
            api_provider = model_config.get_provider(model_info.api_provider)
            
            # 3. 获取客户端实例
            llm_client = client_registry.get_client_class_instance(api_provider)
            
            # 4. 构建Prompt和消息体
            prompt = self._build_prompt(year, month, count)
            message_list = [Message(role=RoleType.User, content=prompt)]
            
            logger.info(f"正在使用模型 '{model_name}' 为 {year}-{month} 生成 {count} 个月度计划...")
            
            # 5. 调用LLM
            response = await llm_client.get_response(
                model_info=model_info,
                message_list=message_list,
                temperature=task_config.temperature,
                max_tokens=task_config.max_tokens,
                response_format=RespFormat(format_type=RespFormatType.JSON_OBJ) # 请求JSON输出
            )
            
            if not response or not response.content:
                logger.error("LLM未能返回有效的计划内容。")
                return []

            # 6. 解析LLM返回的JSON
            try:
                # 移除可能的Markdown代码块标记
                clean_content = response.content.strip()
                if clean_content.startswith("```json"):
                    clean_content = clean_content[7:]
                if clean_content.endswith("```"):
                    clean_content = clean_content[:-3]

                data = json.loads(clean_content.strip())
                plans = data.get("plans", [])
                
                if isinstance(plans, list) and all(isinstance(p, str) for p in plans):
                    logger.info(f"成功生成并解析了 {len(plans)} 个月度计划。")
                    return plans
                else:
                    logger.error(f"LLM返回的JSON格式不正确或'plans'键不是字符串列表: {response.content}")
                    return []
            except json.JSONDecodeError:
                logger.error(f"无法解析LLM返回的JSON: {response.content}")
                return []

        except Exception as e:
            logger.error(f"调用LLM生成月度计划时发生未知错误: {e}", exc_info=True)
            return []