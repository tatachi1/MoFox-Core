import random
from typing import Tuple
from collections import deque

# 导入新插件系统
from src.plugin_system import BaseAction, ActionActivationType, ChatMode

# 导入依赖的系统组件
from src.common.logger import get_logger

# 导入API模块 - 标准Python包方式
from src.plugin_system.apis import llm_api, message_api
from src.chat.emoji_system.emoji_manager import get_emoji_manager
from src.chat.utils.utils_image import image_path_to_base64
from src.config.config import global_config


logger = get_logger("emoji")


class EmojiAction(BaseAction):
    """表情动作 - 发送表情包"""

    # --- 类级别属性 ---
    # 激活设置
    if global_config.emoji.emoji_activate_type == "llm":
        activation_type = ActionActivationType.LLM_JUDGE
        random_activation_probability = 0
    else:
        activation_type = ActionActivationType.RANDOM
        random_activation_probability = global_config.emoji.emoji_chance
    mode_enable = ChatMode.ALL
    parallel_action = True

    # 动作基本信息
    action_name = "emoji"
    action_description = "发送表情包辅助表达情绪"
    
    # 最近发送表情的历史记录
    _sent_emoji_history = deque(maxlen=4)

    # LLM判断提示词
    llm_judge_prompt = """
    判定是否需要使用表情动作的条件：
    1. 用户明确要求使用表情包
    2. 这是一个适合表达情绪的场合
    3. 发表情包能使当前对话更有趣
    4. 不要发送太多表情包，如果你已经发送过多个表情包则回答"否"
    
    请回答"是"或"否"。
    """

    # 动作参数定义
    action_parameters = {}

    # 动作使用场景
    action_require = [
        "发送表情包辅助表达情绪",
        "表达情绪时可以选择使用",
        "不要连续发送，如果你已经发过[表情包]，就不要选择此动作",
    ]

    # 关联类型
    associated_types = ["emoji"]

    async def execute(self) -> Tuple[bool, str]:
        """执行表情动作"""
        logger.info(f"{self.log_prefix} 决定发送表情")

        try:
            # 1. 获取发送表情的原因
            reason = self.action_data.get("reason", "表达当前情绪")
            logger.info(f"{self.log_prefix} 发送表情原因: {reason}")

            # 2. 获取所有表情包
            emoji_manager = get_emoji_manager()
            all_emojis_obj = [e for e in emoji_manager.emoji_objects if not e.is_deleted]
            if not all_emojis_obj:
                logger.warning(f"{self.log_prefix} 无法获取任何表情包")
                return False, "无法获取任何表情包"

            # 3. 准备情感数据和后备列表
            emotion_map = {}
            all_emojis_data = [] 
            
            for emoji in all_emojis_obj:
                b64 = image_path_to_base64(emoji.full_path)
                if not b64:
                    continue
                
                desc = emoji.description
                emotions = emoji.emotion
                # 使用 emoji 对象的 hash 作为唯一标识符
                all_emojis_data.append((b64, desc, emoji.hash))

                for emo in emotions:
                    if emo not in emotion_map:
                        emotion_map[emo] = []
                    emotion_map[emo].append((b64, desc, emoji.hash))

            if not all_emojis_data:
                logger.warning(f"{self.log_prefix} 无法加载任何有效的表情包数据")
                return False, "无法加载任何有效的表情包数据"

            available_emotions = list(emotion_map.keys())
            
            chosen_emoji_b64, chosen_emoji_desc, chosen_emoji_hash = None, None, None

            if not available_emotions:
                logger.warning(f"{self.log_prefix} 获取到的表情包均无情感标签, 将随机发送")
                # 随机选择一个不在历史记录中的表情
                selectable_emojis = [e for e in all_emojis_data if e[2] not in self._sent_emoji_history]
                if not selectable_emojis: # 如果都发过了，就从全部里面随机选
                    selectable_emojis = all_emojis_data
                chosen_emoji_b64, chosen_emoji_desc, chosen_emoji_hash = random.choice(selectable_emojis)
            else:
                # 获取最近的5条消息内容用于判断
                recent_messages = message_api.get_recent_messages(chat_id=self.chat_id, limit=5)
                messages_text = ""
                if recent_messages:
                    messages_text = message_api.build_readable_messages(
                        messages=recent_messages,
                        timestamp_mode="normal_no_YMD",
                        truncate=False,
                        show_actions=False,
                    )

                # 4. 构建prompt让LLM选择多个情感
                prompt = f"""
                你是一个正在进行聊天的网友，你需要根据一个理由和最近的聊天记录，从一个情感标签列表中选择最匹配的 **3个** 情感标签，并按匹配度从高到低排序。
                这是最近的聊天记录：
                {messages_text}
                
                这是理由：“{reason}”
                这里是可用的情感标签：{available_emotions}
                请直接返回一个包含3个最匹配情感标签的有序列表，例如：["开心", "激动", "有趣"]，不要进行任何解释或添加其他多余的文字。
                """

                # 5. 调用LLM
                models = llm_api.get_available_models()
                chat_model_config = models.get("planner")
                if not chat_model_config:
                    logger.error(f"{self.log_prefix} 未找到 'planner' 模型配置，无法调用LLM")
                    return False, "未找到 'planner' 模型配置"

                success, chosen_emotions_str, _, _ = await llm_api.generate_with_model(
                    prompt, model_config=chat_model_config, request_type="emoji_selection"
                )

                selected_emoji_info = None
                if success:
                    try:
                        # 解析LLM返回的列表
                        import json
                        chosen_emotions = json.loads(chosen_emotions_str)
                        if isinstance(chosen_emotions, list):
                            logger.info(f"{self.log_prefix} LLM选择的情感候选项: {chosen_emotions}")
                            # 遍历候选项，找到第一个不在历史记录中的表情
                            for emotion in chosen_emotions:
                                matched_key = next((key for key in emotion_map if emotion in key), None)
                                if matched_key:
                                    # 从匹配到的表情中，随机选一个不在历史记录的
                                    candidate_emojis = [e for e in emotion_map[matched_key] if e[2] not in self._sent_emoji_history]
                                    if candidate_emojis:
                                        selected_emoji_info = random.choice(candidate_emojis)
                                        break # 找到后立即跳出循环
                        else:
                            logger.warning(f"{self.log_prefix} LLM返回的不是一个列表: {chosen_emotions_str}")
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"{self.log_prefix} 解析LLM返回的情感列表失败: {chosen_emotions_str}")

                if selected_emoji_info:
                    chosen_emoji_b64, chosen_emoji_desc, chosen_emoji_hash = selected_emoji_info
                    logger.info(f"{self.log_prefix} 从候选项中选择表情: {chosen_emoji_desc}")
                else:
                    if not success:
                        logger.warning(f"{self.log_prefix} LLM调用失败, 将随机选择一个表情包")
                    else:
                        logger.warning(f"{self.log_prefix} 所有候选项均在最近发送历史中, 将随机选择")
                    
                    selectable_emojis = [e for e in all_emojis_data if e[2] not in self._sent_emoji_history]
                    if not selectable_emojis:
                        selectable_emojis = all_emojis_data
                    chosen_emoji_b64, chosen_emoji_desc, chosen_emoji_hash = random.choice(selectable_emojis)

            # 7. 发送表情包并更新历史记录
            if chosen_emoji_b64 and chosen_emoji_hash:
                success = await self.send_emoji(chosen_emoji_b64)
                if success:
                    self._sent_emoji_history.append(chosen_emoji_hash)
                    logger.info(f"{self.log_prefix} 表情包发送成功: {chosen_emoji_desc}")
                    logger.debug(f"{self.log_prefix} 最近表情历史: {list(self._sent_emoji_history)}")
                    return True, f"发送表情包: {chosen_emoji_desc}"

            logger.error(f"{self.log_prefix} 表情包发送失败")
            return False, "表情包发送失败"

        except Exception as e:
            logger.error(f"{self.log_prefix} 表情动作执行失败: {e}", exc_info=True)
            return False, f"表情发送失败: {str(e)}"
