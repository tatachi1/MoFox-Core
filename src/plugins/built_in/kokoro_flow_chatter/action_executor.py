"""
Kokoro Flow Chatter 动作执行器 (V2)

融合AFC的动态动作发现机制，支持所有注册的Action组件。
负责解析LLM返回的动作列表并通过ChatterActionManager执行。

V2升级要点：
1. 动态动作支持 - 使用ActionManager发现所有可用动作
2. 统一执行接口 - 通过ChatterActionManager.execute_action()执行所有动作
3. 保留KFC特有功能 - 内部状态更新、心理日志等
4. 支持复合动作 - 如 sing_a_song + image_sender + tts_voice_action

V5升级要点：
1. 动态情感更新 - 根据thought字段的情感倾向微调EmotionalState
"""

import asyncio
import json
import re
import time
from typing import TYPE_CHECKING, Any, Optional

from src.chat.planner_actions.action_manager import ChatterActionManager
from src.common.logger import get_logger
from src.plugin_system.base.component_types import ActionInfo

from .models import (
    ActionModel,
    EmotionalState,
    KokoroSession,
    LLMResponseModel,
    MentalLogEntry,
    MentalLogEventType,
)

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream

logger = get_logger("kokoro_action_executor")

# ========== 情感分析关键词映射 ==========
# 正面情感关键词（提升mood_intensity和engagement_level）
POSITIVE_KEYWORDS = [
    "开心", "高兴", "快乐", "喜欢", "爱", "好奇", "期待", "惊喜",
    "感动", "温暖", "舒服", "放松", "满足", "欣慰", "感激", "兴奋",
    "有趣", "好玩", "可爱", "太棒了", "哈哈", "嘻嘻", "hiahia",
]

# 负面情感关键词（降低mood_intensity，可能提升anxiety_level）
NEGATIVE_KEYWORDS = [
    "难过", "伤心", "失望", "沮丧", "担心", "焦虑", "害怕", "紧张",
    "生气", "烦躁", "无聊", "疲惫", "累", "困", "不开心", "不高兴",
    "委屈", "尴尬", "迷茫", "困惑", "郁闷",
]

# 亲密关键词（提升relationship_warmth）
INTIMATE_KEYWORDS = [
    "喜欢你", "想你", "想念", "在乎", "关心", "信任", "依赖",
    "亲爱的", "宝贝", "朋友", "陪伴", "一起", "我们",
]

# 疏远关键词（降低relationship_warmth）
DISTANT_KEYWORDS = [
    "讨厌", "烦人", "无聊", "不想理", "走开", "别烦",
    "算了", "随便", "不在乎",
]


class ActionExecutor:
    """
    Kokoro Flow Chatter 动作执行器 (V2)
    
    职责：
    1. 解析LLM返回的JSON响应
    2. 动态验证动作格式和参数（基于ActionManager的动作注册）
    3. 通过ChatterActionManager执行各类动作
    4. 处理KFC特有的内部状态更新
    5. 记录执行结果到心理日志
    
    V2特性：
    - 支持所有通过插件系统注册的Action
    - 自动从ActionManager获取可用动作列表
    - 支持复合动作组合执行
    - 区分"回复类动作"和"其他动作"的执行顺序
    """
    
    # KFC内置的特殊动作（不通过ActionManager执行）
    INTERNAL_ACTIONS = {
        "update_internal_state": {
            "required": [], 
            "optional": ["mood", "mood_intensity", "relationship_warmth", "impression_of_user", "anxiety_level", "engagement_level"]
        },
        "do_nothing": {"required": [], "optional": []},
    }
    
    def __init__(self, stream_id: str):
        """
        初始化动作执行器
        
        Args:
            stream_id: 聊天流ID
        """
        self.stream_id = stream_id
        self._action_manager = ChatterActionManager()
        self._available_actions: dict[str, ActionInfo] = {}
        self._execution_stats = {
            "total_executed": 0,
            "successful": 0,
            "failed": 0,
            "by_type": {},
        }
    
    async def load_actions(self) -> dict[str, ActionInfo]:
        """
        加载当前可用的动作列表
        
        Returns:
            dict[str, ActionInfo]: 可用动作字典
        """
        await self._action_manager.load_actions(self.stream_id)
        self._available_actions = self._action_manager.get_using_actions()
        logger.debug(f"KFC ActionExecutor 加载了 {len(self._available_actions)} 个可用动作: {list(self._available_actions.keys())}")
        return self._available_actions
    
    def get_available_actions(self) -> dict[str, ActionInfo]:
        """获取当前可用的动作列表"""
        return self._available_actions.copy()
    
    def is_action_available(self, action_type: str) -> bool:
        """
        检查动作是否可用
        
        Args:
            action_type: 动作类型名称
            
        Returns:
            bool: 动作是否可用
        """
        # 内置动作总是可用
        if action_type in self.INTERNAL_ACTIONS:
            return True
        # 检查动态注册的动作
        return action_type in self._available_actions
    
    def parse_llm_response(self, response_text: str) -> LLMResponseModel:
        """
        解析LLM的JSON响应
        
        Args:
            response_text: LLM返回的原始文本
            
        Returns:
            LLMResponseModel: 解析后的响应模型
            
        Raises:
            ValueError: 如果解析失败
        """
        # 尝试提取JSON块
        json_str = self._extract_json(response_text)
        
        if not json_str:
            logger.warning(f"无法从LLM响应中提取JSON: {response_text[:200]}...")
            return LLMResponseModel.create_error_response("无法解析响应格式")
        
        try:
            data = json.loads(json_str)
            return self._validate_and_create_response(data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}, 原始文本: {json_str[:200]}...")
            return LLMResponseModel.create_error_response(f"JSON解析错误: {e}")
    
    def _extract_json(self, text: str) -> Optional[str]:
        """
        从文本中提取JSON块
        
        支持以下格式：
        1. 纯JSON字符串
        2. ```json ... ``` 代码块
        3. 文本中嵌入的JSON对象
        """
        text = text.strip()
        
        # 尝试1：直接解析（如果整个文本就是JSON）
        if text.startswith("{"):
            # 找到匹配的结束括号
            brace_count = 0
            for i, char in enumerate(text):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return text[:i + 1]
        
        # 尝试2：提取 ```json ... ``` 代码块
        json_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
        matches = re.findall(json_block_pattern, text)
        for match in matches:
            match = match.strip()
            if match.startswith("{"):
                try:
                    json.loads(match)
                    return match
                except json.JSONDecodeError:
                    continue
        
        # 尝试3：寻找文本中的JSON对象
        json_pattern = r"\{[\s\S]*\}"
        matches = re.findall(json_pattern, text)
        for match in matches:
            try:
                json.loads(match)
                return match
            except json.JSONDecodeError:
                continue
        
        return None
    
    def _validate_and_create_response(self, data: dict[str, Any]) -> LLMResponseModel:
        """
        验证并创建响应模型（V2：支持动态动作验证）
        
        Args:
            data: 解析后的字典数据
            
        Returns:
            LLMResponseModel: 验证后的响应模型
        """
        # 验证必需字段
        if "thought" not in data:
            data["thought"] = ""
            logger.warning("LLM响应缺少'thought'字段")
        
        if "expected_user_reaction" not in data:
            data["expected_user_reaction"] = ""
            logger.warning("LLM响应缺少'expected_user_reaction'字段")
        
        if "max_wait_seconds" not in data:
            data["max_wait_seconds"] = 300
            logger.warning("LLM响应缺少'max_wait_seconds'字段，使用默认值300")
        else:
            # 确保在合理范围内
            try:
                wait_seconds = int(data["max_wait_seconds"])
                data["max_wait_seconds"] = max(60, min(wait_seconds, 600))
            except (ValueError, TypeError):
                data["max_wait_seconds"] = 300
        
        if "actions" not in data or not data["actions"]:
            data["actions"] = [{"type": "do_nothing"}]
            logger.warning("LLM响应缺少'actions'字段，添加默认的do_nothing动作")
        
        # 验证每个动作（V2：使用动态验证）
        validated_actions = []
        for action_data in data["actions"]:
            if not isinstance(action_data, dict):
                logger.warning(f"无效的动作格式: {action_data}")
                continue
            
            action_type = action_data.get("type", "")
            
            # 检查是否是已注册的动作
            if not self.is_action_available(action_type):
                logger.warning(f"不支持的动作类型: {action_type}，可用动作: {list(self._available_actions.keys()) + list(self.INTERNAL_ACTIONS.keys())}")
                continue
            
            # 对于内置动作，验证参数
            if action_type in self.INTERNAL_ACTIONS:
                required_params = self.INTERNAL_ACTIONS[action_type]["required"]
                missing_params = [p for p in required_params if p not in action_data]
                if missing_params:
                    logger.warning(f"动作 '{action_type}' 缺少必需参数: {missing_params}")
                    continue
            
            # 对于动态注册的动作，仅记录参数信息（不强制验证）
            # 注意：action_require 是"使用场景描述"，不是必需参数！
            # 必需参数应该在 action_parameters 中定义
            elif action_type in self._available_actions:
                action_info = self._available_actions[action_type]
                # 仅记录调试信息，不阻止执行
                if action_info.action_parameters:
                    provided_params = set(action_data.keys()) - {"type", "reason"}
                    expected_params = set(action_info.action_parameters.keys())
                    if expected_params and not provided_params.intersection(expected_params):
                        logger.debug(f"动作 '{action_type}' 期望参数: {list(expected_params)}，实际提供: {list(provided_params)}")
            
            validated_actions.append(action_data)
        
        if not validated_actions:
            validated_actions = [{"type": "do_nothing"}]
        
        data["actions"] = validated_actions
        
        return LLMResponseModel.from_dict(data)
    
    async def execute_actions(
        self,
        response: LLMResponseModel,
        session: KokoroSession,
        chat_stream: Optional["ChatStream"] = None,
    ) -> dict[str, Any]:
        """
        执行动作列表（V2：通过ActionManager执行动态动作）
        
        执行策略（参考AFC的plan_executor）：
        1. 先执行所有"回复类"动作（reply, respond等）
        2. 再执行"其他"动作（send_reaction, sing_a_song等）
        3. 内部动作（update_internal_state, do_nothing）由KFC直接处理
        
        Args:
            response: LLM响应模型
            session: 当前会话
            chat_stream: 聊天流对象（用于发送消息）
            
        Returns:
            dict: 执行结果
        """
        results = []
        has_reply = False
        reply_content = ""
        
        # INFO日志：打印所有解析出的动作（可观测性增强）
        for action in response.actions:
            logger.info(
                f"Parsed action for execution: type={action.type}, params={action.params}"
            )
        
        # 分类动作：回复类 vs 其他类 vs 内部类
        reply_actions = []  # reply, respond
        other_actions = []  # 其他注册的动作
        internal_actions = []  # update_internal_state, do_nothing
        
        for action in response.actions:
            action_type = action.type
            if action_type in self.INTERNAL_ACTIONS:
                internal_actions.append(action)
            elif action_type in ("reply", "respond"):
                reply_actions.append(action)
            else:
                other_actions.append(action)
        
        # 第1步：执行回复类动作
        for action in reply_actions:
            try:
                result = await self._execute_via_action_manager(
                    action, session, chat_stream
                )
                results.append(result)
                
                if result.get("success"):
                    self._execution_stats["successful"] += 1
                    has_reply = True
                    reply_content = action.params.get("content", "") or result.get("reply_text", "")
                else:
                    self._execution_stats["failed"] += 1
                    
            except Exception as e:
                logger.error(f"执行回复动作 '{action.type}' 失败: {e}")
                results.append({
                    "action_type": action.type,
                    "success": False,
                    "error": str(e),
                })
                self._execution_stats["failed"] += 1
            
            self._update_stats(action.type)
        
        # 第2步：并行执行其他动作（参考AFC的_execute_other_actions）
        if other_actions:
            other_tasks = []
            for action in other_actions:
                task = asyncio.create_task(
                    self._execute_via_action_manager(action, session, chat_stream)
                )
                other_tasks.append((action, task))
            
            for action, task in other_tasks:
                try:
                    result = await task
                    results.append(result)
                    if result.get("success"):
                        self._execution_stats["successful"] += 1
                    else:
                        self._execution_stats["failed"] += 1
                except Exception as e:
                    logger.error(f"执行动作 '{action.type}' 失败: {e}")
                    results.append({
                        "action_type": action.type,
                        "success": False,
                        "error": str(e),
                    })
                    self._execution_stats["failed"] += 1
                
                self._update_stats(action.type)
        
        # 第3步：执行内部动作
        for action in internal_actions:
            try:
                result = await self._execute_internal_action(action, session)
                results.append(result)
                self._execution_stats["successful"] += 1
            except Exception as e:
                logger.error(f"执行内部动作 '{action.type}' 失败: {e}")
                results.append({
                    "action_type": action.type,
                    "success": False,
                    "error": str(e),
                })
                self._execution_stats["failed"] += 1
            
            self._update_stats(action.type)
        
        # 添加Bot行动日志
        if has_reply or other_actions:
            entry = MentalLogEntry(
                event_type=MentalLogEventType.BOT_ACTION,
                timestamp=time.time(),
                thought=response.thought,
                content=reply_content or f"执行了 {len(other_actions)} 个动作",
                emotional_snapshot=session.emotional_state.to_dict(),
                metadata={
                    "actions": [a.to_dict() for a in response.actions],
                    "results_summary": {
                        "total": len(results),
                        "successful": sum(1 for r in results if r.get("success")),
                    },
                },
            )
            session.add_mental_log_entry(entry)
            if reply_content:
                session.last_bot_message = reply_content
        
        # V5：动态情感更新 - 根据thought分析情感倾向并微调EmotionalState
        await self._update_emotional_state_from_thought(response.thought, session)
        
        return {
            "success": all(r.get("success", False) for r in results),
            "results": results,
            "has_reply": has_reply,
            "reply_content": reply_content,
            "thought": response.thought,
            "expected_user_reaction": response.expected_user_reaction,
            "max_wait_seconds": response.max_wait_seconds,
        }
    
    def _update_stats(self, action_type: str) -> None:
        """更新执行统计"""
        self._execution_stats["total_executed"] += 1
        if action_type not in self._execution_stats["by_type"]:
            self._execution_stats["by_type"][action_type] = 0
        self._execution_stats["by_type"][action_type] += 1
    
    async def _execute_via_action_manager(
        self,
        action: ActionModel,
        session: KokoroSession,
        chat_stream: Optional["ChatStream"],
    ) -> dict[str, Any]:
        """
        通过ActionManager执行动作
        
        Args:
            action: 动作模型
            session: 当前会话
            chat_stream: 聊天流对象
            
        Returns:
            dict: 执行结果
        """
        action_type = action.type
        params = action.params
        
        logger.debug(f"通过ActionManager执行动作: {action_type}, 参数: {params}")
        
        if not chat_stream:
            return {
                "action_type": action_type,
                "success": False,
                "error": "无法获取聊天流",
            }
        
        try:
            # 准备动作数据
            action_data = params.copy()
            
            # 对于reply动作，需要处理content字段
            if action_type in ("reply", "respond") and "content" in action_data:
                # ActionManager的reply期望的是生成回复而不是直接内容
                # 但KFC已经决定了内容，所以我们直接发送
                return await self._execute_reply_directly(action_data, chat_stream)
            
            # 使用ActionManager执行其他动作
            result = await self._action_manager.execute_action(
                action_name=action_type,
                chat_id=self.stream_id,
                target_message=None,  # KFC模式不需要target_message
                reasoning=f"KFC决策: {action_type}",
                action_data=action_data,
                thinking_id=None,
                log_prefix="[KFC]",
            )
            
            return {
                "action_type": action_type,
                "success": result.get("success", False),
                "reply_text": result.get("reply_text", ""),
                "result": result,
            }
            
        except Exception as e:
            logger.error(f"ActionManager执行失败: {action_type}, 错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "action_type": action_type,
                "success": False,
                "error": str(e),
            }
    
    async def _execute_reply_directly(
        self,
        params: dict[str, Any],
        chat_stream: "ChatStream",
    ) -> dict[str, Any]:
        """
        直接执行回复动作（KFC决定的内容直接发送）
        
        V4升级：集成全局后处理流程（错别字、消息分割）
        
        Args:
            params: 动作参数，包含content
            chat_stream: 聊天流对象
            
        Returns:
            dict: 执行结果
        """
        from src.plugin_system.apis import send_api
        from .response_post_processor import process_reply_content
        
        content = params.get("content", "")
        reply_to = params.get("reply_to")
        should_quote = params.get("should_quote_reply", False)
        
        if not content:
            return {
                "action_type": "reply",
                "success": False,
                "error": "回复内容为空",
            }
        
        try:
            # 【关键步骤】调用全局后处理器（错别字生成、消息分割）
            processed_messages = await process_reply_content(content)
            logger.info(f"[KFC] 后处理完成，原始内容长度={len(content)}，分割为 {len(processed_messages)} 条消息")
            
            all_success = True
            first_message = True
            
            for msg in processed_messages:
                success = await send_api.text_to_stream(
                    text=msg,
                    stream_id=self.stream_id,
                    reply_to_message=reply_to if first_message else None,
                    set_reply=should_quote if first_message else False,
                    typing=True,
                )
                if not success:
                    all_success = False
                first_message = False
            
            return {
                "action_type": "reply",
                "success": all_success,
                "reply_text": content,
                "processed_messages": processed_messages,
            }
            
        except Exception as e:
            logger.error(f"直接发送回复失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "action_type": "reply",
                "success": False,
                "error": str(e),
            }
    
    async def _execute_internal_action(
        self,
        action: ActionModel,
        session: KokoroSession,
    ) -> dict[str, Any]:
        """
        执行KFC内部动作
        
        Args:
            action: 动作模型
            session: 当前会话
            
        Returns:
            dict: 执行结果
        """
        action_type = action.type
        params = action.params
        
        if action_type == "update_internal_state":
            return await self._execute_update_state(params, session)
        
        elif action_type == "do_nothing":
            return await self._execute_do_nothing()
        
        else:
            return {
                "action_type": action_type,
                "success": False,
                "error": f"未知的内部动作类型: {action_type}",
            }
    
    async def _execute_update_state(
        self,
        params: dict[str, Any],
        session: KokoroSession,
    ) -> dict[str, Any]:
        """
        执行内部状态更新动作
        
        这个动作用于实现情感闭环，让AI可以主动更新自己的情感状态
        """
        updated_fields = []
        emotional_state = session.emotional_state
        
        if "mood" in params:
            emotional_state.mood = params["mood"]
            updated_fields.append("mood")
        
        if "mood_intensity" in params:
            try:
                intensity = float(params["mood_intensity"])
                emotional_state.mood_intensity = max(0.0, min(1.0, intensity))
                updated_fields.append("mood_intensity")
            except (ValueError, TypeError):
                pass
        
        if "relationship_warmth" in params:
            try:
                warmth = float(params["relationship_warmth"])
                emotional_state.relationship_warmth = max(0.0, min(1.0, warmth))
                updated_fields.append("relationship_warmth")
            except (ValueError, TypeError):
                pass
        
        if "impression_of_user" in params:
            emotional_state.impression_of_user = str(params["impression_of_user"])
            updated_fields.append("impression_of_user")
        
        if "anxiety_level" in params:
            try:
                anxiety = float(params["anxiety_level"])
                emotional_state.anxiety_level = max(0.0, min(1.0, anxiety))
                updated_fields.append("anxiety_level")
            except (ValueError, TypeError):
                pass
        
        if "engagement_level" in params:
            try:
                engagement = float(params["engagement_level"])
                emotional_state.engagement_level = max(0.0, min(1.0, engagement))
                updated_fields.append("engagement_level")
            except (ValueError, TypeError):
                pass
        
        emotional_state.last_update_time = time.time()
        
        logger.debug(f"更新情感状态: {updated_fields}")
        
        return {
            "action_type": "update_internal_state",
            "success": True,
            "updated_fields": updated_fields,
        }
    
    async def _execute_do_nothing(self) -> dict[str, Any]:
        """执行"什么都不做"动作"""
        logger.debug("执行 do_nothing 动作")
        return {
            "action_type": "do_nothing",
            "success": True,
        }
    
    def get_execution_stats(self) -> dict[str, Any]:
        """获取执行统计信息"""
        return self._execution_stats.copy()
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._execution_stats = {
            "total_executed": 0,
            "successful": 0,
            "failed": 0,
            "by_type": {},
        }
    
    async def _update_emotional_state_from_thought(
        self,
        thought: str,
        session: KokoroSession,
    ) -> None:
        """
        V5：根据thought字段的情感倾向动态更新EmotionalState
        
        分析策略：
        1. 统计正面/负面/亲密/疏远关键词出现次数
        2. 根据关键词比例计算情感调整值
        3. 应用平滑的情感微调（每次变化不超过±0.1）
        
        Args:
            thought: LLM返回的内心独白
            session: 当前会话
        """
        if not thought:
            return
        
        thought_lower = thought.lower()
        emotional_state = session.emotional_state
        
        # 统计关键词
        positive_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in thought_lower)
        negative_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in thought_lower)
        intimate_count = sum(1 for kw in INTIMATE_KEYWORDS if kw in thought_lower)
        distant_count = sum(1 for kw in DISTANT_KEYWORDS if kw in thought_lower)
        
        # 计算情感倾向分数 (-1.0 到 1.0)
        total_mood = positive_count + negative_count
        if total_mood > 0:
            mood_score = (positive_count - negative_count) / total_mood
        else:
            mood_score = 0.0
        
        total_relation = intimate_count + distant_count
        if total_relation > 0:
            relation_score = (intimate_count - distant_count) / total_relation
        else:
            relation_score = 0.0
        
        # 应用情感微调（每次最多变化±0.05）
        adjustment_rate = 0.05
        
        # 更新 mood_intensity
        if mood_score != 0:
            old_intensity = emotional_state.mood_intensity
            new_intensity = old_intensity + (mood_score * adjustment_rate)
            emotional_state.mood_intensity = max(0.0, min(1.0, new_intensity))
            
            # 更新 mood 文字描述
            if mood_score > 0.3:
                emotional_state.mood = "开心"
            elif mood_score < -0.3:
                emotional_state.mood = "低落"
            # 小于0.3的变化不改变mood文字
        
        # 更新 anxiety_level（负面情绪增加焦虑）
        if negative_count > 0 and negative_count > positive_count:
            old_anxiety = emotional_state.anxiety_level
            new_anxiety = old_anxiety + (adjustment_rate * 0.5)
            emotional_state.anxiety_level = max(0.0, min(1.0, new_anxiety))
        elif positive_count > negative_count * 2:
            # 非常积极时降低焦虑
            old_anxiety = emotional_state.anxiety_level
            new_anxiety = old_anxiety - (adjustment_rate * 0.3)
            emotional_state.anxiety_level = max(0.0, min(1.0, new_anxiety))
        
        # 更新 relationship_warmth
        if relation_score != 0:
            old_warmth = emotional_state.relationship_warmth
            new_warmth = old_warmth + (relation_score * adjustment_rate)
            emotional_state.relationship_warmth = max(0.0, min(1.0, new_warmth))
        
        # 更新 engagement_level（有内容的thought表示高投入）
        if len(thought) > 50:
            old_engagement = emotional_state.engagement_level
            new_engagement = old_engagement + (adjustment_rate * 0.5)
            emotional_state.engagement_level = max(0.0, min(1.0, new_engagement))
        
        emotional_state.last_update_time = time.time()
        
        # 记录情感变化日志
        if positive_count + negative_count + intimate_count + distant_count > 0:
            logger.info(
                f"[KFC] 动态情感更新: "
                f"正面={positive_count}, 负面={negative_count}, "
                f"亲密={intimate_count}, 疏远={distant_count} | "
                f"mood_intensity={emotional_state.mood_intensity:.2f}, "
                f"relationship_warmth={emotional_state.relationship_warmth:.2f}, "
                f"anxiety_level={emotional_state.anxiety_level:.2f}"
            )
