"""
Kokoro Flow Chatter (心流聊天器) 插件

一个专为私聊场景设计的AI聊天插件，实现从"消息响应者"到"对话体验者"的转变。
核心特点：
- 心理状态驱动的交互模型
- 连续的时间观念和等待体验
- 深度情感连接和长期关系维护
"""

from src.plugin_system.base.plugin_metadata import PluginMetadata

from .plugin import KokoroFlowChatterPlugin

__plugin_meta__ = PluginMetadata(
    name="Kokoro Flow Chatter",
    description="专为私聊设计的深度情感交互处理器，实现心理状态驱动的对话体验",
    usage="在私聊场景中自动启用，可通过 [kokoro_flow_chatter].enable 配置开关",
    version="3.0.0",
    author="MoFox",
    keywords=["chatter", "kokoro", "private", "emotional", "narrative"],
    categories=["Chat", "AI", "Emotional"],
    extra={"is_built_in": True, "chat_type": "private"},
)

__all__ = ["KokoroFlowChatterPlugin", "__plugin_meta__"]
