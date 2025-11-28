"""
Kokoro Flow Chatter 后台调度器

负责处理等待状态的计时和超时决策，实现"连续体验"的核心功能：
- 定期检查等待中的会话
- 触发连续思考更新
- 处理等待超时事件
"""

import asyncio
import time
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

from src.common.logger import get_logger

from .models import (
    KokoroSession,
    MentalLogEntry,
    MentalLogEventType,
    SessionStatus,
)
from .session_manager import get_session_manager

if TYPE_CHECKING:
    from .chatter import KokoroFlowChatter

logger = get_logger("kokoro_scheduler")


class BackgroundScheduler:
    """
    Kokoro Flow Chatter 后台调度器
    
    核心功能：
    1. 定期检查处于WAITING状态的会话
    2. 在特定时间点触发"连续思考"
    3. 处理等待超时并触发决策
    4. 管理后台任务的生命周期
    """
    
    # 连续思考触发点（等待进度的百分比）
    CONTINUOUS_THINKING_TRIGGERS = [0.3, 0.6, 0.85]
    
    def __init__(
        self,
        check_interval: float = 10.0,
        on_timeout_callback: Optional[Callable[[KokoroSession], Coroutine[Any, Any, None]]] = None,
        on_continuous_thinking_callback: Optional[Callable[[KokoroSession], Coroutine[Any, Any, None]]] = None,
    ):
        """
        初始化后台调度器
        
        Args:
            check_interval: 检查间隔（秒）
            on_timeout_callback: 超时回调函数
            on_continuous_thinking_callback: 连续思考回调函数
        """
        self.check_interval = check_interval
        self.on_timeout_callback = on_timeout_callback
        self.on_continuous_thinking_callback = on_continuous_thinking_callback
        
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        self._pending_tasks: set[asyncio.Task] = set()
        
        # 统计信息
        self._stats = {
            "total_checks": 0,
            "timeouts_triggered": 0,
            "continuous_thinking_triggered": 0,
            "last_check_time": 0.0,
        }
        
        logger.info("BackgroundScheduler 初始化完成")
    
    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            logger.warning("调度器已在运行中")
            return
        
        self._running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("BackgroundScheduler 已启动")
    
    async def stop(self) -> None:
        """停止调度器"""
        self._running = False
        
        # 取消主检查任务
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        
        # 取消所有待处理任务
        for task in self._pending_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._pending_tasks.clear()
        logger.info("BackgroundScheduler 已停止")
    
    async def _check_loop(self) -> None:
        """主检查循环"""
        while self._running:
            try:
                await self._check_waiting_sessions()
                self._stats["last_check_time"] = time.time()
                self._stats["total_checks"] += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"检查循环出错: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def _check_waiting_sessions(self) -> None:
        """检查所有等待中的会话"""
        session_manager = get_session_manager()
        waiting_sessions = await session_manager.get_all_waiting_sessions()
        
        if not waiting_sessions:
            return
        
        for session in waiting_sessions:
            try:
                await self._process_waiting_session(session)
            except Exception as e:
                logger.error(f"处理等待会话 {session.user_id} 时出错: {e}")
    
    async def _process_waiting_session(self, session: KokoroSession) -> None:
        """
        处理单个等待中的会话
        
        Args:
            session: 等待中的会话
        """
        if session.status != SessionStatus.WAITING:
            return
        
        if session.waiting_since is None:
            return
        
        wait_duration = session.get_waiting_duration()
        max_wait = session.max_wait_seconds
        
        # 检查是否超时
        if session.is_wait_timeout():
            logger.info(f"会话 {session.user_id} 等待超时，触发决策")
            await self._handle_timeout(session)
            return
        
        # 检查是否需要触发连续思考
        wait_progress = wait_duration / max_wait if max_wait > 0 else 0
        
        for trigger_point in self.CONTINUOUS_THINKING_TRIGGERS:
            # 检查是否刚刚经过这个触发点
            if self._should_trigger_continuous_thinking(
                session, 
                wait_progress, 
                trigger_point
            ):
                logger.debug(
                    f"会话 {session.user_id} 触发连续思考 "
                    f"(进度: {wait_progress:.1%}, 触发点: {trigger_point:.1%})"
                )
                await self._handle_continuous_thinking(session, wait_progress)
                break
    
    def _should_trigger_continuous_thinking(
        self,
        session: KokoroSession,
        current_progress: float,
        trigger_point: float,
    ) -> bool:
        """
        判断是否应该触发连续思考
        
        逻辑：
        - 当前进度刚刚超过触发点
        - 距离上次连续思考有足够间隔
        - 还没有达到该触发点对应的思考次数
        """
        # 已经超过了这个触发点
        if current_progress < trigger_point:
            return False
        
        # 计算当前应该触发的思考次数
        expected_count = sum(
            1 for tp in self.CONTINUOUS_THINKING_TRIGGERS 
            if current_progress >= tp
        )
        
        # 如果还没达到预期的思考次数，触发一次
        if session.continuous_thinking_count < expected_count:
            # 确保间隔足够（至少30秒）
            if session.last_continuous_thinking_at is None:
                return True
            
            time_since_last = time.time() - session.last_continuous_thinking_at
            return time_since_last >= 30.0
        
        return False
    
    async def _handle_timeout(self, session: KokoroSession) -> None:
        """
        处理等待超时
        
        Args:
            session: 超时的会话
        """
        self._stats["timeouts_triggered"] += 1
        
        # 更新会话状态
        session.status = SessionStatus.FOLLOW_UP_PENDING
        session.emotional_state.anxiety_level = 0.8  # 超时时焦虑程度较高
        
        # 添加超时日志
        timeout_entry = MentalLogEntry(
            event_type=MentalLogEventType.TIMEOUT_DECISION,
            timestamp=time.time(),
            thought=f"等了{session.max_wait_seconds}秒了，对方还是没有回复...",
            content="等待超时",
            emotional_snapshot=session.emotional_state.to_dict(),
        )
        session.add_mental_log_entry(timeout_entry)
        
        # 保存会话状态
        session_manager = get_session_manager()
        await session_manager.save_session(session.user_id)
        
        # 调用超时回调
        if self.on_timeout_callback:
            task = asyncio.create_task(self._run_callback_safe(
                self.on_timeout_callback, 
                session,
                "timeout"
            ))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
    
    async def _handle_continuous_thinking(
        self, 
        session: KokoroSession,
        wait_progress: float,
    ) -> None:
        """
        处理连续思考
        
        Args:
            session: 会话
            wait_progress: 等待进度
        """
        self._stats["continuous_thinking_triggered"] += 1
        
        # 更新焦虑程度
        session.emotional_state.update_anxiety_over_time(
            session.get_waiting_duration(),
            session.max_wait_seconds
        )
        
        # 更新连续思考计数
        session.continuous_thinking_count += 1
        session.last_continuous_thinking_at = time.time()
        
        # 生成基于进度的内心想法
        thought = self._generate_waiting_thought(session, wait_progress)
        
        # 添加连续思考日志
        thinking_entry = MentalLogEntry(
            event_type=MentalLogEventType.CONTINUOUS_THINKING,
            timestamp=time.time(),
            thought=thought,
            content="",
            emotional_snapshot=session.emotional_state.to_dict(),
            metadata={"wait_progress": wait_progress},
        )
        session.add_mental_log_entry(thinking_entry)
        
        # 保存会话状态
        session_manager = get_session_manager()
        await session_manager.save_session(session.user_id)
        
        # 调用连续思考回调（如果需要LLM生成更自然的想法）
        if self.on_continuous_thinking_callback:
            task = asyncio.create_task(self._run_callback_safe(
                self.on_continuous_thinking_callback,
                session,
                "continuous_thinking"
            ))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
    
    def _generate_waiting_thought(
        self, 
        session: KokoroSession, 
        wait_progress: float,
    ) -> str:
        """
        生成等待中的内心想法（简单版本，不调用LLM）
        
        Args:
            session: 会话
            wait_progress: 等待进度
            
        Returns:
            str: 内心想法
        """
        wait_seconds = session.get_waiting_duration()
        wait_minutes = wait_seconds / 60
        
        if wait_progress < 0.4:
            thoughts = [
                f"已经等了{wait_minutes:.1f}分钟了，对方可能在忙吧...",
                f"嗯...{wait_minutes:.1f}分钟过去了，不知道对方在做什么",
                "对方好像还没看到消息，再等等吧",
            ]
        elif wait_progress < 0.7:
            thoughts = [
                f"等了{wait_minutes:.1f}分钟了，有点担心对方是不是不想回了",
                f"{wait_minutes:.1f}分钟了，对方可能真的很忙？",
                "时间过得好慢啊...不知道对方什么时候会回复",
            ]
        else:
            thoughts = [
                f"已经等了{wait_minutes:.1f}分钟了，感觉有点焦虑...",
                f"快{wait_minutes:.0f}分钟了，对方是不是忘记回复了？",
                "等了这么久，要不要主动说点什么呢...",
            ]
        
        import random
        return random.choice(thoughts)
    
    async def _run_callback_safe(
        self,
        callback: Callable[[KokoroSession], Coroutine[Any, Any, None]],
        session: KokoroSession,
        callback_type: str,
    ) -> None:
        """安全地运行回调函数"""
        try:
            await callback(session)
        except Exception as e:
            logger.error(f"执行{callback_type}回调时出错 (user={session.user_id}): {e}")
    
    def set_timeout_callback(
        self,
        callback: Callable[[KokoroSession], Coroutine[Any, Any, None]],
    ) -> None:
        """设置超时回调函数"""
        self.on_timeout_callback = callback
    
    def set_continuous_thinking_callback(
        self,
        callback: Callable[[KokoroSession], Coroutine[Any, Any, None]],
    ) -> None:
        """设置连续思考回调函数"""
        self.on_continuous_thinking_callback = callback
    
    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "is_running": self._running,
            "pending_tasks": len(self._pending_tasks),
            "check_interval": self.check_interval,
        }
    
    @property
    def is_running(self) -> bool:
        """调度器是否正在运行"""
        return self._running


# 全局调度器实例
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    """获取全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


async def initialize_scheduler(
    check_interval: float = 10.0,
    on_timeout_callback: Optional[Callable[[KokoroSession], Coroutine[Any, Any, None]]] = None,
    on_continuous_thinking_callback: Optional[Callable[[KokoroSession], Coroutine[Any, Any, None]]] = None,
) -> BackgroundScheduler:
    """
    初始化并启动调度器
    
    Args:
        check_interval: 检查间隔
        on_timeout_callback: 超时回调
        on_continuous_thinking_callback: 连续思考回调
        
    Returns:
        BackgroundScheduler: 调度器实例
    """
    global _scheduler
    _scheduler = BackgroundScheduler(
        check_interval=check_interval,
        on_timeout_callback=on_timeout_callback,
        on_continuous_thinking_callback=on_continuous_thinking_callback,
    )
    await _scheduler.start()
    return _scheduler


async def shutdown_scheduler() -> None:
    """关闭调度器"""
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None
