"""
Kokoro Flow Chatter 模块化提示词组件

将提示词拆分为独立的模块，每个模块负责特定的内容生成：
1. 核心身份模块 - 人设、人格、世界观
2. 行为准则模块 - 规则、安全边界
3. 情境上下文模块 - 时间、场景、关系、记忆
4. 动作能力模块 - 可用动作的描述
5. 输出格式模块 - JSON格式要求

设计理念：
- 每个模块只负责自己的部分，互不干扰
- 回复相关内容（人设、上下文）与动作定义分离
- 方便独立调试和优化每个部分
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import orjson

from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.base.component_types import ActionInfo

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream

from .models import EmotionalState, KokoroSession

logger = get_logger("kfc_prompt_modules")


# ============================================================
# 模块1: 核心身份 - 人设/人格/背景
# ============================================================

def build_identity_module() -> str:
    """
    构建核心身份模块
    
    包含：人格核心、人格细节、外貌身份、世界观背景
    这些是回复内容的基础，决定了"你是谁"
    """
    if global_config is None:
        raise RuntimeError("global_config 未初始化")
    
    personality_cfg = global_config.personality
    
    personality_core = personality_cfg.personality_core or "你是一个温暖、真诚的对话伙伴。"
    personality_side = personality_cfg.personality_side or ""
    identity = personality_cfg.identity or ""
    background_story = personality_cfg.background_story or ""
    
    parts = ["## 1. 你是谁", personality_core]
    
    if personality_side:
        parts.append(f"\n{personality_side}")
    
    if identity:
        parts.append(f"\n{identity}")
    
    if background_story:
        parts.append(f"\n### 背景故事\n{background_story}")
    
    return "\n".join(parts)


# ============================================================
# 模块2: 行为准则 - 规则/边界/KFC特有准则
# ============================================================

def build_rules_module() -> str:
    """
    构建行为准则模块
    
    包含：安全规则 + KFC 通用准则
    这些是行为的边界，决定了"什么能做什么不能做"
    """
    if global_config is None:
        raise RuntimeError("global_config 未初始化")
    
    safety_guidelines = global_config.personality.safety_guidelines or []
    if isinstance(safety_guidelines, list):
        safety_guidelines_str = "\n".join(f"- {rule}" for rule in safety_guidelines)
    else:
        safety_guidelines_str = str(safety_guidelines)
    
    # KFC 特有准则（简洁自然版）
    kfc_rules = """### 你的行为原则
- 你是真实的人，有自己的生活、情绪和想法
- 说话自然、口语化，像发微信一样随意
- 有自己的边界感，不会无条件迎合
- 称呼对方时用自然的昵称或简称，别念复杂的用户名

### 格式注意
- 聊天记录中的"[表情包：描述]"是系统识别转述，不是你发的
- 想发表情包要用 emoji 动作，不要在回复里写"[表情包：xxx]"这种格式"""
    
    return f"""## 2. 行为准则
{safety_guidelines_str}

{kfc_rules}"""


# ============================================================
# 模块3: 情境上下文 - 时间/场景/内在状态/关系/记忆
# ============================================================

def build_context_module(
    session: KokoroSession,
    chat_stream: Optional["ChatStream"] = None,
    context_data: Optional[dict[str, str]] = None,
) -> str:
    """
    构建情境上下文模块
    
    包含：当前时间、聊天场景、内在状态、关系信息、记忆
    这些是回复的上下文，决定了"当前在什么情况下"
    
    Args:
        session: 当前会话
        chat_stream: 聊天流（判断群聊/私聊）
        context_data: S4U 上下文数据
    """
    context_data = context_data or {}
    
    # 时间和场景
    current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    is_group_chat = bool(chat_stream and chat_stream.group_info)
    chat_scene = "你在群里聊天" if is_group_chat else "你在和对方私聊"
    
    # 日程（如果有）- 只是背景，不主动提及
    schedule_block = context_data.get("schedule", "")
    
    # 内在状态（简化版，更自然）
    es = session.emotional_state
    inner_state = f"""### 你现在的状态
- 心情：{es.mood}
- 你们的关系：{es.impression_of_user or "刚认识，还在慢慢了解"}
- 你的投入度：{'聊得挺起劲' if es.engagement_level > 0.6 else '一般般' if es.engagement_level > 0.3 else '有点心不在焉'}"""
    
    # 关系信息
    relation_info = context_data.get("relation_info", "")
    
    # 记忆
    memory_block = context_data.get("memory_block", "")
    
    parts = [
        "## 3. 当前情境",
        f"**现在是** {current_time}",
        f"**{chat_scene}**",
    ]
    
    # 日程是你的当前状态，但不要主动提及
    if schedule_block:
        parts.append(f"""### 你的当前状态（重要：不要主动提及）
{schedule_block}
⚠️ 这是你当前正在做的事，作为你的背景状态存在。除非对方主动问你"在干嘛"、"忙不忙"等问题，否则**绝对不要在回复中主动提起**。就像真人聊天一样，没人会无缘无故说"我正在XX"。""")
    
    parts.append("")
    parts.append(inner_state)
    
    if relation_info:
        parts.append("")
        parts.append("## 4. 你和对方的关系")
        parts.append(relation_info)
    
    if memory_block:
        parts.append("")
        parts.append(memory_block)
    
    return "\n".join(parts)


# ============================================================
# 模块4: 动作能力 - 可用动作的描述
# ============================================================

def build_actions_module(available_actions: Optional[dict[str, ActionInfo]] = None) -> str:
    """
    构建动作能力模块
    
    包含：所有可用动作的描述、参数、示例
    这部分与回复内容分离，只描述"能做什么"
    
    Args:
        available_actions: 可用动作字典
    """
    if not available_actions:
        actions_block = _get_default_actions_block()
    else:
        actions_block = _format_available_actions(available_actions)
    
    return f"""## 5. 你能做的事情

{actions_block}"""


def _format_available_actions(available_actions: dict[str, ActionInfo]) -> str:
    """格式化可用动作列表（简洁版）"""
    action_blocks = []
    
    for action_name, action_info in available_actions.items():
        description = action_info.description or f"执行 {action_name}"
        
        # 构建动作块（简洁格式）
        action_block = f"### `{action_name}` - {description}"
        
        # 参数说明（如果有）
        if action_info.action_parameters:
            params_lines = [f"  - `{name}`: {desc}" for name, desc in action_info.action_parameters.items()]
            action_block += f"\n参数:\n{chr(10).join(params_lines)}"
        
        # 使用场景（如果有）
        if action_info.action_require:
            require_lines = [f"  - {req}" for req in action_info.action_require]
            action_block += f"\n使用场景:\n{chr(10).join(require_lines)}"
        
        # 简洁示例
        example_params = ""
        if action_info.action_parameters:
            param_examples = [f'"{name}": "..."' for name in action_info.action_parameters.keys()]
            example_params = ", " + ", ".join(param_examples)
        
        action_block += f'\n```json\n{{"type": "{action_name}"{example_params}}}\n```'
        
        action_blocks.append(action_block)
    
    return "\n\n".join(action_blocks)


def _get_default_actions_block() -> str:
    """获取默认的内置动作描述块"""
    return """### `reply` - 发消息
发送文字回复
```json
{"type": "reply", "content": "你要说的话"}
```

### `poke_user` - 戳一戳
戳对方一下
```json
{"type": "poke_user"}
```

### `update_internal_state` - 更新你的状态
更新你的心情和对对方的印象
```json
{"type": "update_internal_state", "mood": "开心", "impression_of_user": "挺有趣的人"}
```

### `do_nothing` - 不做任何事
想了想，决定现在不说话
```json
{"type": "do_nothing"}
```"""


# ============================================================
# 模块5: 表达与输出格式 - 回复风格 + JSON格式
# ============================================================

def build_output_module(
    context_data: Optional[dict[str, str]] = None,
) -> str:
    """
    构建输出格式模块
    
    包含：表达风格、表达习惯、JSON 输出格式要求
    这部分定义了"怎么说"和"输出什么格式"
    
    Args:
        context_data: S4U 上下文数据（包含 expression_habits）
    """
    if global_config is None:
        raise RuntimeError("global_config 未初始化")
    
    context_data = context_data or {}
    
    reply_style = global_config.personality.reply_style or ""
    expression_habits = context_data.get("expression_habits", "")
    
    # JSON 输出格式说明 - 简洁版
    json_format = """### 输出格式
用 JSON 输出你的想法和决策：

```json
{
  "thought": "你的内心想法，想说什么就说什么",
  "expected_user_reaction": "你觉得对方会怎么回应",
  "max_wait_seconds": 等待秒数（60-900），不想等就填0,
  "actions": [
    {"type": "reply", "content": "你要发送的消息"},
    {"type": "其他动作", ...}
  ]
}
```

说明：
- `thought`：你脑子里在想什么，越自然越好
- `actions`：你要做的事，可以组合多个动作
- `max_wait_seconds`：设定一个时间，对方没回的话你会再想想要不要说点什么
- 即使什么都不想做，也放一个 `{"type": "do_nothing"}`"""
    
    parts = ["## 6. 你的表达方式"]
    
    if reply_style:
        parts.append(reply_style)
    
    if expression_habits:
        parts.append("")
        parts.append(expression_habits)
    
    parts.append("")
    parts.append(json_format)
    
    return "\n".join(parts)


# ============================================================
# 组装完整的 System Prompt
# ============================================================

def build_system_prompt(
    session: KokoroSession,
    available_actions: Optional[dict[str, ActionInfo]] = None,
    context_data: Optional[dict[str, str]] = None,
    chat_stream: Optional["ChatStream"] = None,
) -> str:
    """
    组装完整的系统提示词
    
    按模块顺序组装：
    1. 角色框架（你是对话体验者）
    2. 核心身份（人设）
    3. 行为准则（规则）
    4. 情境上下文（时间/状态/关系）
    5. 动作能力（可用动作）
    6. 输出格式（表达风格 + JSON）
    
    Args:
        session: 当前会话
        available_actions: 可用动作字典
        context_data: S4U 上下文数据
        chat_stream: 聊天流
        
    Returns:
        完整的系统提示词
    """
    # 角色框架 - 简洁自然
    role_frame = '你不是AI助手，你是一个真实的人，有自己的生活、想法和情绪。聊天时就像平时发微信一样自然。'
    
    # 组装各模块
    modules = [
        role_frame,
        "",
        build_identity_module(),
        "",
        build_rules_module(),
        "",
        build_context_module(session, chat_stream, context_data),
        "",
        build_actions_module(available_actions),
        "",
        build_output_module(context_data),
    ]
    
    return "\n".join(modules)
