"""
Kokoro Flow Chatter Prompt生成器

根据会话状态动态构建LLM提示词，实现"体验-决策-行动"的交互模式。
支持两种主要场景：
1. 回应消息（Responding）：收到用户消息后的决策
2. 超时决策（Timeout Decision）：等待超时后的后续行动决策

V2 升级：
- 动态Action发现机制：从ActionManager获取可用Action列表
- 支持任意复杂参数的Action
- 与AFC的Action系统完全兼容

V5 超融合架构升级：
- 完整集成S4U的所有上下文模块
- 关系信息、记忆、表达习惯等全部融入
- 支持群聊/私聊场景动态切换
"""

import asyncio
import time
from typing import TYPE_CHECKING, Any, Optional

from src.common.logger import get_logger
from src.plugin_system.base.component_types import ActionInfo

from .models import (
    EmotionalState,
    KokoroSession,
    MentalLogEntry,
    MentalLogEventType,
)

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream
    from src.chat.planner_actions.action_manager import ChatterActionManager
    from src.common.data_models.message_manager_data_model import StreamContext

logger = get_logger("kokoro_prompt_generator")


class PromptGenerator:
    """
    Kokoro Flow Chatter 提示词生成器
    
    负责根据会话状态和场景生成不同的LLM提示词，
    引导AI以"体验者"的身份参与对话。
    
    V2 升级：支持动态Action发现，与AFC的Action系统完全兼容
    V4 升级：完整集成用户人设、世界观、表达风格和规则
    V5 超融合架构：集成S4U所有上下文模块（关系、记忆、表达习惯等）
    """
    
    # ========== 超融合架构 SYSTEM_PROMPT_TEMPLATE V7 ==========
    # 简洁自然版，参考 S4U 风格
    SYSTEM_PROMPT_TEMPLATE = """你不是 AI，你是一个真实的人，有自己的生活、想法和情绪。

## 1. 你是谁
{personality_core}

{personality_side}

{identity}

{background_story}

## 2. 规则
{safety_guidelines}

- 说话要自然，像平时发微信一样
- 有自己的边界感，不用无条件迎合
- 称呼对方用自然的昵称，别念复杂的用户名

## 3. 现在的情况
**时间**: {current_time}
**场景**: {chat_scene}
{schedule_block}

你现在的心情：{mood}
你对对方的印象：{impression_of_user}

## 4. 你和对方的关系
{relation_info_block}

{memory_block}

## 5. 你能做的事
{available_actions_block}

## 6. 怎么回复
{reply_style}

{expression_habits_block}

### 输出格式（JSON）
```json
{{
  "thought": "你在想什么",
  "expected_user_reaction": "你觉得对方会怎么回应",
  "max_wait_seconds": 等多久（60-900，不等就填0）,
  "actions": [
    {{"type": "reply", "content": "你要说的话"}}
  ]
}}
```

不想做任何事就用 `{{"type": "do_nothing"}}`"""

    # 回应消息场景的用户提示词模板（V7: 支持多条消息）
    RESPONDING_USER_PROMPT_TEMPLATE = """## 聊天记录
{narrative_history}

## 新消息
{incoming_messages}

---
看完这些消息，你想怎么回应？用 JSON 输出你的想法和决策。"""

    # 超时决策场景的用户提示词模板（V7重构：简洁自然）
    TIMEOUT_DECISION_USER_PROMPT_TEMPLATE = """## 聊天记录
{narrative_history}

## 现在的情况
你发了消息，等了 {wait_duration_seconds:.0f} 秒（{wait_duration_minutes:.1f} 分钟），对方还没回。
你之前觉得对方可能会：{expected_user_reaction}

{followup_warning}

你发的最后一条：{last_bot_message}

---
你拿起手机看了一眼，发现对方还没回复。你想怎么办？

选项：
1. **继续等** - 用 `do_nothing`，设个 `max_wait_seconds` 等一会儿再看
2. **发消息** - 用 `reply`，不过别太频繁追问
3. **算了不等了** - 用 `do_nothing`，`max_wait_seconds` 设为 0

用 JSON 输出你的想法和决策。"""

    # 连续思考场景的用户提示词模板
    CONTINUOUS_THINKING_USER_PROMPT_TEMPLATE = """## 聊天记录
{narrative_history}

## 现在的情况
你在等对方回复，已经等了 {wait_duration_seconds:.0f} 秒。
你之前觉得对方可能会：{expected_user_reaction}

你发的最后一条：{last_bot_message}

---
等待的时候你在想什么？用 JSON 输出，`actions` 留空就行。"""

    # 主动思考场景的用户提示词模板
    PROACTIVE_THINKING_USER_PROMPT_TEMPLATE = """## 聊天记录
{narrative_history}

## 现在的情况
现在是 {current_time}，距离你们上次聊天已经过了 {silence_duration}。

{relation_block}

{trigger_context}

---
你突然想起了对方。要不要联系一下？

说实话，不联系也完全没问题——不打扰也是一种温柔。
如果决定联系，想好说什么，要自然一点。

用 JSON 输出你的想法和决策。不想发消息就用 `do_nothing`。"""

    def __init__(self, persona_description: str = ""):
        """
        初始化提示词生成器
        
        Args:
            persona_description: 人设描述
        """
        self.persona_description = persona_description or self._get_default_persona()
    
    def _get_default_persona(self) -> str:
        """获取默认人设描述"""
        return """你是一个温暖、真诚的对话伙伴。
你有自己的情感和想法，会真实地表达内心的感受。
你关心与用户的关系，但也保持健康的边界。
你可以感到开心、好奇、担心、或者稍微沮丧，这些都是正常的。"""
    
    def set_persona(self, persona_description: str) -> None:
        """设置人设描述"""
        self.persona_description = persona_description
    
    def _format_emotional_state(self, state: EmotionalState) -> dict[str, str | float]:
        """格式化情感状态用于模板替换"""
        return {
            "mood": state.mood,
            "mood_intensity": state.mood_intensity,
            "relationship_warmth": state.relationship_warmth,
            "impression_of_user": state.impression_of_user or "还没有形成明确的印象",
            "anxiety_level": state.anxiety_level,
            "engagement_level": state.engagement_level,
        }
    
    def _format_narrative_history(
        self, 
        mental_log: list[MentalLogEntry],
        max_entries: int = 15,
    ) -> str:
        """
        将心理活动日志格式化为叙事历史
        
        Args:
            mental_log: 心理活动日志列表
            max_entries: 最大条目数
            
        Returns:
            str: 格式化的叙事历史文本
        """
        if not mental_log:
            return "（这是对话的开始，还没有历史记录）"
        
        # 获取最近的日志条目
        recent_entries = mental_log[-max_entries:]
        
        narrative_parts = []
        for entry in recent_entries:
            timestamp_str = time.strftime(
                "%Y-%m-%d %H:%M:%S", 
                time.localtime(entry.timestamp)
            )
            
            if entry.event_type == MentalLogEventType.USER_MESSAGE:
                narrative_parts.append(
                    f"[{timestamp_str}] 用户说：{entry.content}"
                )
            elif entry.event_type == MentalLogEventType.BOT_ACTION:
                if entry.thought:
                    narrative_parts.append(
                        f"[{timestamp_str}] （你的内心：{entry.thought}）"
                    )
                if entry.content:
                    narrative_parts.append(
                        f"[{timestamp_str}] 你回复：{entry.content}"
                    )
            elif entry.event_type == MentalLogEventType.WAITING_UPDATE:
                if entry.thought:
                    narrative_parts.append(
                        f"[{timestamp_str}] （等待中的想法：{entry.thought}）"
                    )
            elif entry.event_type == MentalLogEventType.CONTINUOUS_THINKING:
                if entry.thought:
                    narrative_parts.append(
                        f"[{timestamp_str}] （思绪飘过：{entry.thought}）"
                    )
            elif entry.event_type == MentalLogEventType.STATE_CHANGE:
                if entry.content:
                    narrative_parts.append(
                        f"[{timestamp_str}] {entry.content}"
                    )
        
        return "\n".join(narrative_parts)
    
    def _format_history_from_context(
        self,
        context: "StreamContext",
        mental_log: list[MentalLogEntry] | None = None,
    ) -> str:
        """
        从 StreamContext 的历史消息构建叙事历史
        
        这是实现"无缝融入"的关键：
        - 从同一个数据库读取历史消息（与AFC共享）
        - 遵循全局配置 [chat].max_context_size
        - 将消息渲染成KFC的叙事体格式
        
        Args:
            context: 聊天流上下文，包含共享的历史消息
            mental_log: 可选的心理活动日志，用于补充内心独白
            
        Returns:
            str: 格式化的叙事历史文本
        """
        from src.config.config import global_config
        
        # 从 StreamContext 获取历史消息，遵循全局上下文长度配置
        max_context = 25  # 默认值
        if global_config and hasattr(global_config, 'chat') and global_config.chat:
            max_context = getattr(global_config.chat, "max_context_size", 25)
        history_messages = context.get_messages(limit=max_context, include_unread=False)
        
        if not history_messages and not mental_log:
            return "（这是对话的开始，还没有历史记录）"
        
        # 获取Bot的用户ID用于判断消息来源
        bot_user_id = None
        if global_config and hasattr(global_config, 'bot') and global_config.bot:
            bot_user_id = str(getattr(global_config.bot, 'qq_account', ''))
        
        narrative_parts = []
        
        # 首先，将数据库历史消息转换为叙事格式
        for msg in history_messages:
            timestamp_str = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(msg.time or time.time())
            )
            
            # 判断是用户消息还是Bot消息
            msg_user_id = str(msg.user_info.user_id) if msg.user_info else ""
            is_bot_message = bot_user_id and msg_user_id == bot_user_id
            content = msg.processed_plain_text or msg.display_message or ""
            
            if is_bot_message:
                narrative_parts.append(f"[{timestamp_str}] 你回复：{content}")
            else:
                sender_name = msg.user_info.user_nickname if msg.user_info else "用户"
                narrative_parts.append(f"[{timestamp_str}] {sender_name}说：{content}")
        
        # 然后，补充 mental_log 中的内心独白（如果有）
        if mental_log:
            for entry in mental_log[-5:]:  # 只取最近5条心理活动
                timestamp_str = time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(entry.timestamp)
                )
                
                if entry.event_type == MentalLogEventType.BOT_ACTION and entry.thought:
                    narrative_parts.append(f"[{timestamp_str}] （你的内心：{entry.thought}）")
                elif entry.event_type == MentalLogEventType.CONTINUOUS_THINKING and entry.thought:
                    narrative_parts.append(f"[{timestamp_str}] （思绪飘过：{entry.thought}）")
        
        return "\n".join(narrative_parts)
    
    def _format_available_actions(
        self,
        available_actions: dict[str, ActionInfo],
    ) -> str:
        """
        格式化可用动作列表为提示词块
        
        Args:
            available_actions: 可用动作字典 {动作名: ActionInfo}
            
        Returns:
            str: 格式化的动作描述文本
        """
        if not available_actions:
            # 使用默认的内置动作
            return self._get_default_actions_block()
        
        action_blocks = []
        
        for action_name, action_info in available_actions.items():
            # 构建动作描述
            description = action_info.description or f"执行 {action_name} 动作"
            
            # 构建参数说明
            params_lines = []
            if action_info.action_parameters:
                for param_name, param_desc in action_info.action_parameters.items():
                    params_lines.append(f'    - `{param_name}`: {param_desc}')
            
            # 构建使用场景
            require_lines = []
            if action_info.action_require:
                for req in action_info.action_require:
                    require_lines.append(f"  - {req}")
            
            # 组装动作块
            action_block = f"""### `{action_name}`
**描述**: {description}"""
            
            if params_lines:
                action_block += f"""
**参数**:
{chr(10).join(params_lines)}"""
            else:
                action_block += "\n**参数**: 无"
            
            if require_lines:
                action_block += f"""
**使用场景**:
{chr(10).join(require_lines)}"""
            
            # 添加示例
            example_params = {}
            if action_info.action_parameters:
                for param_name, param_desc in action_info.action_parameters.items():
                    example_params[param_name] = f"<{param_desc}>"
            
            import orjson
            params_json = orjson.dumps(example_params, option=orjson.OPT_INDENT_2).decode('utf-8') if example_params else "{}"
            action_block += f"""
**示例**:
```json
{{
  "type": "{action_name}",
  "reason": "选择这个动作的原因",
  {params_json[1:-1] if params_json != '{}' else ''}
}}
```"""
            
            action_blocks.append(action_block)
        
        return "\n\n".join(action_blocks)
    
    def _get_default_actions_block(self) -> str:
        """获取默认的内置动作描述块"""
        return """### `reply`
**描述**: 发送文字回复给用户
**参数**:
    - `content`: 回复的文字内容（必须）
**示例**:
```json
{"type": "reply", "content": "你好呀！今天过得怎么样？"}
```

### `poke_user`
**描述**: 戳一戳用户，轻量级互动
**参数**: 无
**示例**:
```json
{"type": "poke_user", "reason": "想逗逗他"}
```

### `update_internal_state`
**描述**: 更新你的内部情感状态
**重要约束**：
⚠️ **情绪变化必须有明确的上下文理由**：
  - 只有当聊天内容中有明确触发情绪变化的事件时才更新情绪
  - 禁止无缘无故地变成负面情绪（如低落、沮丧、难过等）
  - 情绪应该保持相对稳定，除非聊天中发生了真正影响情绪的事情
  - 默认保持"平静"或当前情绪即可，不需要每次都更新

**参数**:
    - `mood`: 当前心情（如"平静"、"开心"、"好奇"等，避免负面情绪除非有明确理由）
    - `mood_intensity`: 心情强度（0.0-1.0，变化幅度不宜过大）
    - `impression_of_user`: 对用户的印象描述
    - `engagement_level`: 投入程度（0.0-1.0）
**示例**:
```json
{"type": "update_internal_state", "mood": "开心", "mood_intensity": 0.6, "reason": "对方分享了有趣的事情"}
```

### `do_nothing`
**描述**: 明确表示"思考后决定不作回应"
**参数**: 无
**示例**:
```json
{"type": "do_nothing", "reason": "现在不是说话的好时机"}
```"""
    
    def generate_system_prompt(
        self,
        session: KokoroSession,
        available_actions: Optional[dict[str, ActionInfo]] = None,
        context_data: Optional[dict[str, str]] = None,
        chat_stream: Optional["ChatStream"] = None,
    ) -> str:
        """
        生成系统提示词
        
        V6模块化升级：使用 prompt_modules 构建模块化的提示词
        - 每个模块独立构建，职责清晰
        - 回复相关（人设、上下文）与动作定义分离
        
        Args:
            session: 当前会话
            available_actions: 可用动作字典，如果为None则使用默认动作
            context_data: S4U上下文数据字典（包含relation_info, memory_block等）
            chat_stream: 聊天流（用于判断群聊/私聊场景）
            
        Returns:
            str: 系统提示词
        """
        from .prompt_modules import build_system_prompt
        
        return build_system_prompt(
            session=session,
            available_actions=available_actions,
            context_data=context_data,
            chat_stream=chat_stream,
        )
    
    def generate_responding_prompt(
        self,
        session: KokoroSession,
        message_content: str,
        sender_name: str,
        sender_id: str,
        message_time: Optional[float] = None,
        available_actions: Optional[dict[str, ActionInfo]] = None,
        context: Optional["StreamContext"] = None,
        context_data: Optional[dict[str, str]] = None,
        chat_stream: Optional["ChatStream"] = None,
        all_unread_messages: Optional[list] = None,  # V7: 支持多条消息
    ) -> tuple[str, str]:
        """
        生成回应消息场景的提示词
        
        V3 升级：支持从 StreamContext 读取共享的历史消息
        V5 超融合：集成S4U所有上下文模块
        V7 升级：支持多条消息（打断机制合并处理pending消息）
        
        Args:
            session: 当前会话
            message_content: 收到的主消息内容（兼容旧调用方式）
            sender_name: 发送者名称
            sender_id: 发送者ID
            message_time: 消息时间戳
            available_actions: 可用动作字典
            context: 聊天流上下文（可选），用于读取共享的历史消息
            context_data: S4U上下文数据字典（包含relation_info, memory_block等）
            chat_stream: 聊天流（用于判断群聊/私聊场景）
            all_unread_messages: 所有未读消息列表（V7新增，包含pending消息）
            
        Returns:
            tuple[str, str]: (系统提示词, 用户提示词)
        """
        system_prompt = self.generate_system_prompt(
            session, 
            available_actions,
            context_data=context_data,
            chat_stream=chat_stream,
        )
        
        # V3: 优先从 StreamContext 读取历史（与AFC共享同一数据源）
        if context:
            narrative_history = self._format_history_from_context(context, session.mental_log)
        else:
            # 回退到仅使用 mental_log（兼容旧调用方式）
            narrative_history = self._format_narrative_history(session.mental_log)
        
        # V7: 格式化收到的消息（支持多条）
        incoming_messages = self._format_incoming_messages(
            message_content=message_content,
            sender_name=sender_name,
            sender_id=sender_id,
            message_time=message_time,
            all_unread_messages=all_unread_messages,
        )
        
        user_prompt = self.RESPONDING_USER_PROMPT_TEMPLATE.format(
            narrative_history=narrative_history,
            incoming_messages=incoming_messages,
        )
        
        return system_prompt, user_prompt
    
    def _format_incoming_messages(
        self,
        message_content: str,
        sender_name: str,
        sender_id: str,
        message_time: Optional[float] = None,
        all_unread_messages: Optional[list] = None,
    ) -> str:
        """
        格式化收到的消息（V7新增）
        
        支持单条消息（兼容旧调用）和多条消息（打断合并场景）
        
        Args:
            message_content: 主消息内容
            sender_name: 发送者名称
            sender_id: 发送者ID
            message_time: 消息时间戳
            all_unread_messages: 所有未读消息列表
            
        Returns:
            str: 格式化的消息文本
        """
        if message_time is None:
            message_time = time.time()
        
        # 如果有多条消息，格式化为消息组
        if all_unread_messages and len(all_unread_messages) > 1:
            lines = [f"**用户连续发送了 {len(all_unread_messages)} 条消息：**\n"]
            
            for i, msg in enumerate(all_unread_messages, 1):
                msg_time = msg.time or time.time()
                msg_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(msg_time))
                msg_sender = msg.user_info.user_nickname if msg.user_info else sender_name
                msg_content = msg.processed_plain_text or msg.display_message or ""
                
                lines.append(f"[{i}] 来自：{msg_sender}")
                lines.append(f"    时间：{msg_time_str}")
                lines.append(f"    内容：{msg_content}")
                lines.append("")
            
            lines.append("**提示**：请综合理解这些消息的整体意图，不需要逐条回复。")
            return "\n".join(lines)
        
        # 单条消息（兼容旧格式）
        message_time_str = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(message_time)
        )
        return f"""来自：{sender_name}（用户ID: {sender_id}）
时间：{message_time_str}
内容：{message_content}"""
    
    def generate_timeout_decision_prompt(
        self,
        session: KokoroSession,
        available_actions: Optional[dict[str, ActionInfo]] = None,
    ) -> tuple[str, str]:
        """
        生成超时决策场景的提示词（V7：增加连续追问限制）
        
        Args:
            session: 当前会话
            available_actions: 可用动作字典
            
        Returns:
            tuple[str, str]: (系统提示词, 用户提示词)
        """
        system_prompt = self.generate_system_prompt(session, available_actions)
        
        narrative_history = self._format_narrative_history(session.mental_log)
        
        wait_duration = session.get_waiting_duration()
        
        # V7: 生成连续追问警告
        followup_count = session.consecutive_followup_count
        max_followups = session.max_consecutive_followups
        
        if followup_count >= max_followups:
            followup_warning = f"""⚠️ **重要提醒**：
你已经连续追问了 {followup_count} 次，对方都没有回复。
**强烈建议不要再发消息了**——继续追问会显得很缠人、很不尊重对方的空间。
对方可能真的在忙，或者暂时不想回复，这都是正常的。
请选择 `do_nothing` 继续等待，或者直接结束对话（设置 `max_wait_seconds: 0`）。"""
        elif followup_count > 0:
            followup_warning = f"""📝 提示：这已经是你第 {followup_count + 1} 次等待对方回复了。
如果对方持续没有回应，可能真的在忙或不方便，不需要急着追问。"""
        else:
            followup_warning = ""
        
        user_prompt = self.TIMEOUT_DECISION_USER_PROMPT_TEMPLATE.format(
            narrative_history=narrative_history,
            wait_duration_seconds=wait_duration,
            wait_duration_minutes=wait_duration / 60,
            expected_user_reaction=session.expected_user_reaction or "不确定",
            followup_warning=followup_warning,
            last_bot_message=session.last_bot_message or "（没有记录）",
        )
        
        return system_prompt, user_prompt
    
    def generate_continuous_thinking_prompt(
        self,
        session: KokoroSession,
        available_actions: Optional[dict[str, ActionInfo]] = None,
    ) -> tuple[str, str]:
        """
        生成连续思考场景的提示词
        
        Args:
            session: 当前会话
            available_actions: 可用动作字典
            
        Returns:
            tuple[str, str]: (系统提示词, 用户提示词)
        """
        system_prompt = self.generate_system_prompt(session, available_actions)
        
        narrative_history = self._format_narrative_history(
            session.mental_log, 
            max_entries=10  # 连续思考时使用较少的历史
        )
        
        wait_duration = session.get_waiting_duration()
        
        user_prompt = self.CONTINUOUS_THINKING_USER_PROMPT_TEMPLATE.format(
            narrative_history=narrative_history,
            wait_duration_seconds=wait_duration,
            wait_duration_minutes=wait_duration / 60,
            max_wait_seconds=session.max_wait_seconds,
            expected_user_reaction=session.expected_user_reaction or "不确定",
            last_bot_message=session.last_bot_message or "（没有记录）",
        )
        
        return system_prompt, user_prompt
    
    def generate_proactive_thinking_prompt(
        self,
        session: KokoroSession,
        trigger_context: str,
        available_actions: Optional[dict[str, ActionInfo]] = None,
        context_data: Optional[dict[str, str]] = None,
        chat_stream: Optional["ChatStream"] = None,
    ) -> tuple[str, str]:
        """
        生成主动思考场景的提示词
        
        这是私聊专属的功能，用于实现"主动找话题、主动关心用户"。
        主动思考不是"必须发消息"，而是"想一想要不要联系对方"。
        
        Args:
            session: 当前会话
            trigger_context: 触发上下文描述（如"沉默了2小时"）
            available_actions: 可用动作字典
            context_data: S4U上下文数据（包含全局关系信息）
            chat_stream: 聊天流
            
        Returns:
            tuple[str, str]: (系统提示词, 用户提示词)
        """
        from datetime import datetime
        import time
        
        # 生成系统提示词（使用 context_data 获取完整的关系和记忆信息）
        system_prompt = self.generate_system_prompt(
            session, 
            available_actions,
            context_data=context_data,
            chat_stream=chat_stream,
        )
        
        narrative_history = self._format_narrative_history(
            session.mental_log,
            max_entries=10,  # 主动思考时使用较少的历史
        )
        
        # 计算沉默时长
        silence_seconds = time.time() - session.last_activity_at
        if silence_seconds < 3600:
            silence_duration = f"{silence_seconds / 60:.0f}分钟"
        else:
            silence_duration = f"{silence_seconds / 3600:.1f}小时"
        
        # 当前时间
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        
        # 从 context_data 获取全局关系信息（这是正确的来源）
        relation_block = ""
        if context_data:
            relation_info = context_data.get("relation_info", "")
            if relation_info:
                relation_block = f"### 你与对方的关系\n{relation_info}"
        
        if not relation_block:
            # 回退：使用 session 的情感状态（不太准确但有总比没有好）
            es = session.emotional_state
            relation_block = f"""### 你与对方的关系
- 当前心情：{es.mood}
- 对对方的印象：{es.impression_of_user or "还在慢慢了解中"}"""
        
        user_prompt = self.PROACTIVE_THINKING_USER_PROMPT_TEMPLATE.format(
            narrative_history=narrative_history,
            current_time=current_time,
            silence_duration=silence_duration,
            relation_block=relation_block,
            trigger_context=trigger_context,
        )
        
        return system_prompt, user_prompt
    
    def build_messages_for_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        stream_id: str = "",
    ) -> list[dict[str, str]]:
        """
        构建LLM请求的消息列表
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            stream_id: 聊天流ID（用于日志）
            
        Returns:
            list[dict]: 消息列表
        """
        # INFO日志：打印完整的KFC提示词（可观测性增强）
        full_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"
        logger.info(
            f"Final KFC prompt constructed for stream {stream_id}:\n"
            f"--- PROMPT START ---\n"
            f"{full_prompt}\n"
            f"--- PROMPT END ---"
        )
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]


# 全局提示词生成器实例
_prompt_generator: Optional[PromptGenerator] = None


def get_prompt_generator(persona_description: str = "") -> PromptGenerator:
    """获取全局提示词生成器实例"""
    global _prompt_generator
    if _prompt_generator is None:
        _prompt_generator = PromptGenerator(persona_description)
    return _prompt_generator


def set_prompt_generator_persona(persona_description: str) -> None:
    """设置全局提示词生成器的人设"""
    generator = get_prompt_generator()
    generator.set_persona(persona_description)
