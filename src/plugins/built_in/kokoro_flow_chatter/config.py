"""
Kokoro Flow Chatter 插件配置

定义插件的配置项和默认值
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PersonaConfig:
    """人设配置"""
    description: str = """你是一个温暖、真诚的对话伙伴。
你有自己的情感和想法，会真实地表达内心的感受。
你关心与用户的关系，但也保持健康的边界。
你可以感到开心、好奇、担心、或者稍微沮丧，这些都是正常的。"""
    
    name: str = "心流助手"
    """AI的名字"""


@dataclass
class BehaviorConfig:
    """行为配置"""
    max_wait_seconds_default: int = 300
    """默认最大等待秒数"""
    
    min_wait_seconds: int = 60
    """最小等待秒数"""
    
    max_wait_seconds_limit: int = 600
    """最大等待秒数上限"""
    
    enable_continuous_thinking: bool = True
    """是否启用连续思考"""
    
    continuous_thinking_triggers: list[float] = field(
        default_factory=lambda: [0.3, 0.6, 0.85]
    )
    """连续思考触发点（等待进度百分比）"""
    
    scheduler_check_interval: float = 10.0
    """调度器检查间隔（秒）"""


@dataclass
class SessionConfig:
    """会话配置"""
    data_dir: str = "data/kokoro_flow_chatter/sessions"
    """会话数据存储目录"""
    
    max_session_age_days: int = 30
    """会话最大保留天数"""
    
    auto_save_interval: int = 300
    """自动保存间隔（秒）"""
    
    max_mental_log_size: int = 100
    """心理日志最大条目数"""


@dataclass
class LLMConfig:
    """LLM配置"""
    model_name: str = ""
    """使用的模型名称，留空则使用默认主模型"""
    
    max_tokens: int = 2048
    """最大生成token数"""
    
    temperature: float = 0.8
    """生成温度"""


@dataclass
class EmotionalConfig:
    """情感系统配置"""
    initial_mood: str = "neutral"
    """初始心情"""
    
    initial_mood_intensity: float = 0.5
    """初始心情强度"""
    
    initial_relationship_warmth: float = 0.5
    """初始关系热度"""
    
    anxiety_increase_rate: float = 0.5
    """焦虑增长率（平方根系数）"""


@dataclass
class KokoroFlowChatterConfig:
    """心流聊天器完整配置"""
    enabled: bool = True
    """是否启用插件"""
    
    persona: PersonaConfig = field(default_factory=PersonaConfig)
    """人设配置"""
    
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    """行为配置"""
    
    session: SessionConfig = field(default_factory=SessionConfig)
    """会话配置"""
    
    llm: LLMConfig = field(default_factory=LLMConfig)
    """LLM配置"""
    
    emotional: EmotionalConfig = field(default_factory=EmotionalConfig)
    """情感系统配置"""
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "persona": {
                "description": self.persona.description,
                "name": self.persona.name,
            },
            "behavior": {
                "max_wait_seconds_default": self.behavior.max_wait_seconds_default,
                "min_wait_seconds": self.behavior.min_wait_seconds,
                "max_wait_seconds_limit": self.behavior.max_wait_seconds_limit,
                "enable_continuous_thinking": self.behavior.enable_continuous_thinking,
                "continuous_thinking_triggers": self.behavior.continuous_thinking_triggers,
                "scheduler_check_interval": self.behavior.scheduler_check_interval,
            },
            "session": {
                "data_dir": self.session.data_dir,
                "max_session_age_days": self.session.max_session_age_days,
                "auto_save_interval": self.session.auto_save_interval,
                "max_mental_log_size": self.session.max_mental_log_size,
            },
            "llm": {
                "model_name": self.llm.model_name,
                "max_tokens": self.llm.max_tokens,
                "temperature": self.llm.temperature,
            },
            "emotional": {
                "initial_mood": self.emotional.initial_mood,
                "initial_mood_intensity": self.emotional.initial_mood_intensity,
                "initial_relationship_warmth": self.emotional.initial_relationship_warmth,
                "anxiety_increase_rate": self.emotional.anxiety_increase_rate,
            },
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KokoroFlowChatterConfig":
        """从字典创建配置"""
        config = cls()
        
        if "enabled" in data:
            config.enabled = data["enabled"]
        
        if "persona" in data:
            persona_data = data["persona"]
            config.persona.description = persona_data.get(
                "description", 
                config.persona.description
            )
            config.persona.name = persona_data.get(
                "name",
                config.persona.name
            )
        
        if "behavior" in data:
            behavior_data = data["behavior"]
            config.behavior.max_wait_seconds_default = behavior_data.get(
                "max_wait_seconds_default",
                config.behavior.max_wait_seconds_default
            )
            config.behavior.min_wait_seconds = behavior_data.get(
                "min_wait_seconds",
                config.behavior.min_wait_seconds
            )
            config.behavior.max_wait_seconds_limit = behavior_data.get(
                "max_wait_seconds_limit",
                config.behavior.max_wait_seconds_limit
            )
            config.behavior.enable_continuous_thinking = behavior_data.get(
                "enable_continuous_thinking",
                config.behavior.enable_continuous_thinking
            )
            config.behavior.continuous_thinking_triggers = behavior_data.get(
                "continuous_thinking_triggers",
                config.behavior.continuous_thinking_triggers
            )
            config.behavior.scheduler_check_interval = behavior_data.get(
                "scheduler_check_interval",
                config.behavior.scheduler_check_interval
            )
        
        if "session" in data:
            session_data = data["session"]
            config.session.data_dir = session_data.get(
                "data_dir",
                config.session.data_dir
            )
            config.session.max_session_age_days = session_data.get(
                "max_session_age_days",
                config.session.max_session_age_days
            )
            config.session.auto_save_interval = session_data.get(
                "auto_save_interval",
                config.session.auto_save_interval
            )
            config.session.max_mental_log_size = session_data.get(
                "max_mental_log_size",
                config.session.max_mental_log_size
            )
        
        if "llm" in data:
            llm_data = data["llm"]
            config.llm.model_name = llm_data.get(
                "model_name",
                config.llm.model_name
            )
            config.llm.max_tokens = llm_data.get(
                "max_tokens",
                config.llm.max_tokens
            )
            config.llm.temperature = llm_data.get(
                "temperature",
                config.llm.temperature
            )
        
        if "emotional" in data:
            emotional_data = data["emotional"]
            config.emotional.initial_mood = emotional_data.get(
                "initial_mood",
                config.emotional.initial_mood
            )
            config.emotional.initial_mood_intensity = emotional_data.get(
                "initial_mood_intensity",
                config.emotional.initial_mood_intensity
            )
            config.emotional.initial_relationship_warmth = emotional_data.get(
                "initial_relationship_warmth",
                config.emotional.initial_relationship_warmth
            )
            config.emotional.anxiety_increase_rate = emotional_data.get(
                "anxiety_increase_rate",
                config.emotional.anxiety_increase_rate
            )
        
        return config


# 默认配置实例
default_config = KokoroFlowChatterConfig()
