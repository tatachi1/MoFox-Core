"""
智能提示词参数模块 - 优化参数结构
简化SmartPromptParameters，减少冗余和重复
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Literal


@dataclass
class SmartPromptParameters:
    """简化的智能提示词参数系统"""

    # 基础参数
    chat_id: str = ""
    is_group_chat: bool = False
    sender: str = ""
    target: str = ""
    reply_to: str = ""
    extra_info: str = ""
    prompt_mode: Literal["s4u", "normal", "minimal"] = "s4u"

    # 功能开关
    enable_tool: bool = True
    enable_memory: bool = True
    enable_expression: bool = True
    enable_relation: bool = True
    enable_cross_context: bool = True
    enable_knowledge: bool = True

    # 性能控制
    max_context_messages: int = 50

    # 调试选项
    debug_mode: bool = False

    # 聊天历史和上下文
    chat_target_info: Optional[Dict[str, Any]] = None
    message_list_before_now_long: List[Dict[str, Any]] = field(default_factory=list)
    message_list_before_short: List[Dict[str, Any]] = field(default_factory=list)
    chat_talking_prompt_short: str = ""
    target_user_info: Optional[Dict[str, Any]] = None

    # 已构建的内容块
    expression_habits_block: str = ""
    relation_info_block: str = ""
    memory_block: str = ""
    tool_info_block: str = ""
    knowledge_prompt: str = ""
    cross_context_block: str = ""

    # 其他内容块
    keywords_reaction_prompt: str = ""
    extra_info_block: str = ""
    time_block: str = ""
    identity_block: str = ""
    schedule_block: str = ""
    moderation_prompt_block: str = ""
    reply_target_block: str = ""
    mood_prompt: str = ""
    action_descriptions: str = ""

    # 可用动作信息
    available_actions: Optional[Dict[str, Any]] = None

    def validate(self) -> List[str]:
        """统一的参数验证"""
        errors = []
        if not self.chat_id:
            errors.append("chat_id不能为空")
        if self.prompt_mode not in ["s4u", "normal", "minimal"]:
            errors.append("prompt_mode必须是's4u'、'normal'或'minimal'")
        if self.max_context_messages <= 0:
            errors.append("max_context_messages必须大于0")
        return errors

    def get_needed_build_tasks(self) -> List[str]:
        """获取需要执行的任务列表"""
        tasks = []

        if self.enable_expression and not self.expression_habits_block:
            tasks.append("expression_habits")

        if self.enable_memory and not self.memory_block:
            tasks.append("memory_block")

        if self.enable_relation and not self.relation_info_block:
            tasks.append("relation_info")

        if self.enable_tool and not self.tool_info_block:
            tasks.append("tool_info")

        if self.enable_knowledge and not self.knowledge_prompt:
            tasks.append("knowledge_info")

        if self.enable_cross_context and not self.cross_context_block:
            tasks.append("cross_context")

        return tasks

    @classmethod
    def from_legacy_params(cls, **kwargs) -> "SmartPromptParameters":
        """
        从旧版参数创建新参数对象

        Args:
            **kwargs: 旧版参数

        Returns:
            SmartPromptParameters: 新参数对象
        """
        return cls(
            # 基础参数
            chat_id=kwargs.get("chat_id", ""),
            is_group_chat=kwargs.get("is_group_chat", False),
            sender=kwargs.get("sender", ""),
            target=kwargs.get("target", ""),
            reply_to=kwargs.get("reply_to", ""),
            extra_info=kwargs.get("extra_info", ""),
            prompt_mode=kwargs.get("current_prompt_mode", "s4u"),
            # 功能开关
            enable_tool=kwargs.get("enable_tool", True),
            enable_memory=kwargs.get("enable_memory", True),
            enable_expression=kwargs.get("enable_expression", True),
            enable_relation=kwargs.get("enable_relation", True),
            enable_cross_context=kwargs.get("enable_cross_context", True),
            enable_knowledge=kwargs.get("enable_knowledge", True),
            # 性能控制
            max_context_messages=kwargs.get("max_context_messages", 50),
            debug_mode=kwargs.get("debug_mode", False),
            # 聊天历史和上下文
            chat_target_info=kwargs.get("chat_target_info"),
            message_list_before_now_long=kwargs.get("message_list_before_now_long", []),
            message_list_before_short=kwargs.get("message_list_before_short", []),
            chat_talking_prompt_short=kwargs.get("chat_talking_prompt_short", ""),
            target_user_info=kwargs.get("target_user_info"),
            # 已构建的内容块
            expression_habits_block=kwargs.get("expression_habits_block", ""),
            relation_info_block=kwargs.get("relation_info", ""),
            memory_block=kwargs.get("memory_block", ""),
            tool_info_block=kwargs.get("tool_info", ""),
            knowledge_prompt=kwargs.get("knowledge_prompt", ""),
            cross_context_block=kwargs.get("cross_context_block", ""),
            # 其他内容块
            keywords_reaction_prompt=kwargs.get("keywords_reaction_prompt", ""),
            extra_info_block=kwargs.get("extra_info_block", ""),
            time_block=kwargs.get("time_block", ""),
            identity_block=kwargs.get("identity_block", ""),
            schedule_block=kwargs.get("schedule_block", ""),
            moderation_prompt_block=kwargs.get("moderation_prompt_block", ""),
            reply_target_block=kwargs.get("reply_target_block", ""),
            mood_prompt=kwargs.get("mood_prompt", ""),
            action_descriptions=kwargs.get("action_descriptions", ""),
            # 可用动作信息
            available_actions=kwargs.get("available_actions", None),
        )
