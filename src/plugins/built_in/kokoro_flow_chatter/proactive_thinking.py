"""
Kokoro Flow Chatter 主动思考引擎 (V2)

私聊专属的主动思考系统，实现"主动找话题、主动关心用户"的能力。
这是KFC区别于AFC的核心特性之一。

触发机制：
1. 长时间沉默检测 - 当对话沉默超过阈值时主动发起话题
2. 关键记忆触发 - 基于重要日期、事件的主动关心
3. 情绪状态触发 - 当情感参数达到阈值时主动表达
4. 好感度驱动 - 根据与用户的关系深度调整主动程度

设计理念：
- 不是"有事才找你"，而是"想你了就找你"
- 主动思考应该符合人设和情感状态
- 避免过度打扰，保持适度的边界感
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.base.component_types import ActionInfo

from .models import KokoroSession, MentalLogEntry, MentalLogEventType, SessionStatus

if TYPE_CHECKING:
    from .action_executor import ActionExecutor
    from .prompt_generator import PromptGenerator

logger = get_logger("kokoro_proactive_thinking")


class ProactiveThinkingTrigger(Enum):
    """主动思考触发类型"""
    SILENCE_TIMEOUT = "silence_timeout"      # 长时间沉默 - 她感到挂念
    TIME_BASED = "time_based"                # 时间触发（早安/晚安）- 自然的问候契机


@dataclass
class ProactiveThinkingConfig:
    """
    主动思考配置
    
    设计哲学：主动行为源于内部状态和外部环境的自然反应，而非机械的限制。
    她的主动是因为挂念、因为关心、因为想问候，而不是因为"任务"。
    """
    # 是否启用主动思考
    enabled: bool = True
    
    # 1. 沉默触发器：当感到长久的沉默时，她可能会想说些什么
    silence_threshold_seconds: int = 7200  # 2小时无互动触发
    silence_check_interval: int = 300  # 每5分钟检查一次
    
    # 2. 关系门槛：她不会对不熟悉的人过于主动
    min_affinity_for_proactive: float = 0.3  # 最低好感度才会主动
    
    # 3. 频率呼吸：为了避免打扰，她的关心总是有间隔的
    min_interval_between_proactive: int = 1800  # 两次主动思考至少间隔30分钟
    
    # 4. 自然问候：在特定的时间，她会像朋友一样送上问候
    enable_morning_greeting: bool = True  # 早安问候 (8:00-9:00)
    enable_night_greeting: bool = True    # 晚安问候 (22:00-23:00)
    
    # 随机性（让行为更自然）
    random_delay_range: tuple[int, int] = (60, 300)  # 触发后随机延迟1-5分钟
    
    @classmethod
    def from_global_config(cls) -> "ProactiveThinkingConfig":
        """从 global_config.kokoro_flow_chatter.proactive_thinking 创建配置"""
        if global_config and hasattr(global_config, 'kokoro_flow_chatter'):
            kfc = global_config.kokoro_flow_chatter
            proactive = kfc.proactive_thinking
            return cls(
                enabled=proactive.enabled,
                silence_threshold_seconds=proactive.silence_threshold_seconds,
                silence_check_interval=300,  # 固定值
                min_affinity_for_proactive=proactive.min_affinity_for_proactive,
                min_interval_between_proactive=proactive.min_interval_between_proactive,
                enable_morning_greeting=proactive.enable_morning_greeting,
                enable_night_greeting=proactive.enable_night_greeting,
                random_delay_range=(60, 300),  # 固定值
            )
        return cls()


@dataclass
class ProactiveThinkingState:
    """主动思考状态 - 记录她的主动关心历史"""
    last_proactive_time: float = 0.0
    last_morning_greeting_date: str = ""  # 上次早安的日期
    last_night_greeting_date: str = ""    # 上次晚安的日期
    pending_triggers: list[ProactiveThinkingTrigger] = field(default_factory=list)
    
    def can_trigger(self, config: ProactiveThinkingConfig) -> bool:
        """
        检查是否满足主动思考的基本条件
        
        注意：这里不使用每日限制，而是基于间隔来自然控制频率
        """
        # 检查间隔限制 - 她的关心有呼吸感，不会太频繁
        if time.time() - self.last_proactive_time < config.min_interval_between_proactive:
            return False
        
        return True
    
    def record_trigger(self) -> None:
        """记录一次触发"""
        self.last_proactive_time = time.time()
    
    def record_morning_greeting(self) -> None:
        """记录今天的早安"""
        self.last_morning_greeting_date = time.strftime("%Y-%m-%d")
        self.record_trigger()
    
    def record_night_greeting(self) -> None:
        """记录今天的晚安"""
        self.last_night_greeting_date = time.strftime("%Y-%m-%d")
        self.record_trigger()
    
    def has_greeted_morning_today(self) -> bool:
        """今天是否已经问候过早安"""
        return self.last_morning_greeting_date == time.strftime("%Y-%m-%d")
    
    def has_greeted_night_today(self) -> bool:
        """今天是否已经问候过晚安"""
        return self.last_night_greeting_date == time.strftime("%Y-%m-%d")


class ProactiveThinkingEngine:
    """
    主动思考引擎
    
    负责检测触发条件并生成主动思考内容。
    这是一个"内在动机驱动"而非"机械限制"的系统。
    
    她的主动源于：
    - 长时间的沉默让她感到挂念
    - 与用户的好感度决定了她愿意多主动
    - 特定的时间点给了她自然的问候契机
    """
    
    def __init__(
        self,
        stream_id: str,
        config: ProactiveThinkingConfig | None = None,
    ):
        """
        初始化主动思考引擎
        
        Args:
            stream_id: 聊天流ID
            config: 配置对象
        """
        self.stream_id = stream_id
        self.config = config or ProactiveThinkingConfig()
        self.state = ProactiveThinkingState()
        
        # 回调函数
        self._on_proactive_trigger: Optional[Callable] = None
        
        # 后台任务
        self._check_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.debug(f"[ProactiveThinking] 初始化完成: stream_id={stream_id}")
    
    def set_proactive_callback(
        self,
        callback: Callable[[KokoroSession, ProactiveThinkingTrigger], Any]
    ) -> None:
        """
        设置主动思考触发回调
        
        Args:
            callback: 当触发主动思考时调用的函数
        """
        self._on_proactive_trigger = callback
    
    async def start(self) -> None:
        """启动主动思考引擎"""
        if self._running:
            return
        
        self._running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info(f"[ProactiveThinking] 引擎已启动: stream_id={self.stream_id}")
    
    async def stop(self) -> None:
        """停止主动思考引擎"""
        self._running = False
        
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            self._check_task = None
        
        logger.info(f"[ProactiveThinking] 引擎已停止: stream_id={self.stream_id}")
    
    async def _check_loop(self) -> None:
        """后台检查循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.silence_check_interval)
                
                if not self.config.enabled:
                    continue
                
                # 这里需要获取session来检查，但我们在引擎层面不直接持有session
                # 实际的检查逻辑通过 check_triggers 方法被外部调用
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ProactiveThinking] 检查循环出错: {e}")
    
    async def check_triggers(
        self,
        session: KokoroSession,
    ) -> Optional[ProactiveThinkingTrigger]:
        """
        检查触发条件 - 基于内在动机而非机械限制
        
        综合考虑：
        1. 她与用户的好感度是否足够（关系门槛）
        2. 距离上次主动是否有足够间隔（频率呼吸）
        3. 是否有自然的触发契机（沉默/时间问候）
        
        Args:
            session: 当前会话
            
        Returns:
            触发类型，如果没有触发则返回None
        """
        if not self.config.enabled:
            return None
        
        # 关系门槛：她不会对不熟悉的人过于主动
        relationship_warmth = session.emotional_state.relationship_warmth
        if relationship_warmth < self.config.min_affinity_for_proactive:
            logger.debug(
                f"[ProactiveThinking] 好感度不足，不主动: "
                f"{relationship_warmth:.2f} < {self.config.min_affinity_for_proactive}"
            )
            return None
        
        # 频率呼吸：检查间隔
        if not self.state.can_trigger(self.config):
            return None
        
        # 只有在 IDLE 或 WAITING 状态才考虑主动
        if session.status not in (SessionStatus.IDLE, SessionStatus.WAITING):
            return None
        
        # 按优先级检查触发契机
        
        # 1. 时间问候（早安/晚安）- 自然的问候契机
        trigger = self._check_time_greeting_trigger()
        if trigger:
            return trigger
        
        # 2. 沉默触发 - 她感到挂念
        trigger = self._check_silence_trigger(session)
        if trigger:
            return trigger
        
        return None
    
    def _check_time_greeting_trigger(self) -> Optional[ProactiveThinkingTrigger]:
        """检查时间问候触发（早安/晚安）"""
        current_hour = time.localtime().tm_hour
        
        # 早安问候 (8:00 - 9:00)
        if self.config.enable_morning_greeting:
            if 8 <= current_hour < 9 and not self.state.has_greeted_morning_today():
                logger.debug("[ProactiveThinking] 早安问候时间")
                return ProactiveThinkingTrigger.TIME_BASED
        
        # 晚安问候 (22:00 - 23:00)
        if self.config.enable_night_greeting:
            if 22 <= current_hour < 23 and not self.state.has_greeted_night_today():
                logger.debug("[ProactiveThinking] 晚安问候时间")
                return ProactiveThinkingTrigger.TIME_BASED
        
        return None
    
    def _check_silence_trigger(
        self,
        session: KokoroSession,
    ) -> Optional[ProactiveThinkingTrigger]:
        """检查沉默触发 - 长时间的沉默让她感到挂念"""
        # 获取最后互动时间
        last_interaction = session.waiting_since or session.last_activity_at
        if not last_interaction:
            # 使用session创建时间
            last_interaction = session.mental_log[0].timestamp if session.mental_log else time.time()
        
        silence_duration = time.time() - last_interaction
        
        if silence_duration >= self.config.silence_threshold_seconds:
            logger.debug(f"[ProactiveThinking] 沉默触发: 已沉默 {silence_duration:.0f} 秒，她感到挂念")
            return ProactiveThinkingTrigger.SILENCE_TIMEOUT
        
        return None
    
    async def generate_proactive_prompt(
        self,
        session: KokoroSession,
        trigger: ProactiveThinkingTrigger,
        prompt_generator: "PromptGenerator",
        available_actions: dict[str, ActionInfo] | None = None,
    ) -> tuple[str, str]:
        """
        生成主动思考的提示词
        
        Args:
            session: 当前会话
            trigger: 触发类型
            prompt_generator: 提示词生成器
            available_actions: 可用动作
            
        Returns:
            (system_prompt, user_prompt) 元组
        """
        # 根据触发类型生成上下文
        trigger_context = self._build_trigger_context(session, trigger)
        
        # 使用prompt_generator生成主动思考提示词
        system_prompt, user_prompt = prompt_generator.generate_proactive_thinking_prompt(
            session=session,
            trigger_type=trigger.value,
            trigger_context=trigger_context,
            available_actions=available_actions,
        )
        
        return system_prompt, user_prompt
    
    def _build_trigger_context(
        self,
        session: KokoroSession,
        trigger: ProactiveThinkingTrigger,
    ) -> str:
        """
        构建触发上下文 - 描述她主动联系的内在动机
        """
        emotional_state = session.emotional_state
        current_hour = time.localtime().tm_hour
        
        if trigger == ProactiveThinkingTrigger.TIME_BASED:
            # 时间问候 - 自然的问候契机
            if 8 <= current_hour < 12:
                return (
                    f"早上好！新的一天开始了。"
                    f"我的心情是「{emotional_state.mood}」。"
                    f"我想和对方打个招呼，开启美好的一天。"
                )
            else:
                return (
                    f"夜深了，已经{current_hour}点了。"
                    f"我的心情是「{emotional_state.mood}」。"
                    f"我想关心一下对方，送上晚安。"
                )
        
        else:  # SILENCE_TIMEOUT
            # 沉默触发 - 她感到挂念
            last_time = session.waiting_since or session.last_activity_at or time.time()
            silence_hours = (time.time() - last_time) / 3600
            return (
                f"我们已经有 {silence_hours:.1f} 小时没有聊天了。"
                f"我有些挂念对方。"
                f"我现在的心情是「{emotional_state.mood}」。"
                f"对方给我的印象是：{emotional_state.impression_of_user or '还不太了解'}"
            )
    
    async def execute_proactive_action(
        self,
        session: KokoroSession,
        trigger: ProactiveThinkingTrigger,
        action_executor: "ActionExecutor",
        prompt_generator: "PromptGenerator",
        llm_call: Callable[[str, str], Any],
    ) -> dict[str, Any]:
        """
        执行主动思考流程
        
        Args:
            session: 当前会话
            trigger: 触发类型
            action_executor: 动作执行器
            prompt_generator: 提示词生成器
            llm_call: LLM调用函数（可以是同步或异步）
            
        Returns:
            执行结果
        """
        try:
            # 1. 加载可用动作
            available_actions = await action_executor.load_actions()
            
            # 2. 生成提示词
            system_prompt, user_prompt = await self.generate_proactive_prompt(
                session, trigger, prompt_generator, available_actions
            )
            
            # 3. 添加随机延迟（更自然）
            delay = random.randint(*self.config.random_delay_range)
            logger.debug(f"[ProactiveThinking] 延迟 {delay} 秒后执行")
            await asyncio.sleep(delay)
            
            # 4. 调用LLM（支持同步和异步）
            result = llm_call(system_prompt, user_prompt)
            if asyncio.iscoroutine(result):
                llm_response = await result
            else:
                llm_response = result
            
            # 5. 解析响应
            parsed_response = action_executor.parse_llm_response(llm_response)
            
            # 6. 记录主动思考事件
            entry = MentalLogEntry(
                event_type=MentalLogEventType.CONTINUOUS_THINKING,
                timestamp=time.time(),
                thought=f"[主动思考-{trigger.value}] {parsed_response.thought}",
                content="",
                emotional_snapshot=session.emotional_state.to_dict(),
                metadata={
                    "trigger_type": trigger.value,
                    "proactive": True,
                },
            )
            session.add_mental_log_entry(entry)
            
            # 7. 执行动作
            from src.chat.message_receive.chat_stream import get_chat_manager
            chat_manager = get_chat_manager()
            chat_stream = await chat_manager.get_stream(self.stream_id) if chat_manager else None
            
            result = await action_executor.execute_actions(
                parsed_response,
                session,
                chat_stream
            )
            
            # 8. 记录触发（根据触发类型决定记录方式）
            if trigger == ProactiveThinkingTrigger.TIME_BASED:
                # 时间问候需要单独记录，防止同一天重复问候
                current_hour = time.localtime().tm_hour
                if 6 <= current_hour < 12:
                    self.state.record_morning_greeting()
                else:
                    self.state.record_night_greeting()
            else:
                self.state.record_trigger()
            
            # 9. 如果发送了消息，更新会话状态
            if result.get("has_reply"):
                session.start_waiting(
                    expected_reaction=parsed_response.expected_user_reaction,
                    max_wait=parsed_response.max_wait_seconds
                )
            
            return {
                "success": True,
                "trigger": trigger.value,
                "result": result,
            }
            
        except Exception as e:
            logger.error(f"[ProactiveThinking] 执行失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "trigger": trigger.value,
                "error": str(e),
            }
    
    def get_state(self) -> dict[str, Any]:
        """获取当前状态"""
        return {
            "enabled": self.config.enabled,
            "last_proactive_time": self.state.last_proactive_time,
            "last_morning_greeting_date": self.state.last_morning_greeting_date,
            "last_night_greeting_date": self.state.last_night_greeting_date,
            "running": self._running,
        }


# 全局引擎实例管理
_engines: dict[str, ProactiveThinkingEngine] = {}


def get_proactive_thinking_engine(
    stream_id: str,
    config: ProactiveThinkingConfig | None = None,
) -> ProactiveThinkingEngine:
    """
    获取主动思考引擎实例
    
    Args:
        stream_id: 聊天流ID
        config: 配置对象（如果为None，则从global_config加载）
        
    Returns:
        ProactiveThinkingEngine实例
    """
    if stream_id not in _engines:
        # 如果没有提供config，从global_config加载
        if config is None:
            config = ProactiveThinkingConfig.from_global_config()
        _engines[stream_id] = ProactiveThinkingEngine(stream_id, config)
    return _engines[stream_id]


async def cleanup_engines() -> None:
    """清理所有引擎实例"""
    for engine in _engines.values():
        await engine.stop()
    _engines.clear()
