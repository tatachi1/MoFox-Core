import asyncio
import time
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional

# Benchmark the distribution manager's run_chat_stream/conversation_loop behavior
# by wiring a lightweight dummy manager and contexts. This avoids touching real DB or chat subsystems.

# Ensure project root is on sys.path when running as a script
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Avoid importing the whole 'src.chat' package to prevent heavy deps (e.g., redis)
# Local minimal implementation of loop and manager to isolate benchmark from heavy deps.
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class ConversationTick:
    stream_id: str
    tick_time: float = field(default_factory=time.time)
    force_dispatch: bool = False
    tick_count: int = 0


async def conversation_loop(
    stream_id: str,
    get_context_func: Callable[[str], Awaitable["DummyContext | None"]],
    calculate_interval_func: Callable[[str, bool], Awaitable[float]],
    flush_cache_func: Callable[[str], Awaitable[list[Any]]],
    check_force_dispatch_func: Callable[["DummyContext", int], bool],
    is_running_func: Callable[[], bool],
) -> AsyncIterator[ConversationTick]:
    tick_count = 0
    while is_running_func():
        ctx = await get_context_func(stream_id)
        if not ctx:
            await asyncio.sleep(0.1)
            continue
        await flush_cache_func(stream_id)
        unread = ctx.get_unread_messages()
        ucnt = len(unread)
        force = check_force_dispatch_func(ctx, ucnt)
        if ucnt > 0 or force:
            tick_count += 1
            yield ConversationTick(stream_id=stream_id, force_dispatch=force, tick_count=tick_count)
        interval = await calculate_interval_func(stream_id, ucnt > 0)
        await asyncio.sleep(interval)


class StreamLoopManager:
    def __init__(self, max_concurrent_streams: Optional[int] = None):
        self.stats: dict[str, Any] = {
            "active_streams": 0,
            "total_loops": 0,
            "total_process_cycles": 0,
            "total_failures": 0,
            "start_time": time.time(),
        }
        self.max_concurrent_streams = max_concurrent_streams or 100
        self.force_dispatch_unread_threshold = 20
        self.chatter_manager = DummyChatterManager()
        self.is_running = False
        self._stream_start_locks: dict[str, asyncio.Lock] = {}
        self._processing_semaphore = asyncio.Semaphore(self.max_concurrent_streams)
        self._chat_manager: Optional[DummyChatManager] = None

    def set_chat_manager(self, chat_manager: "DummyChatManager") -> None:
        self._chat_manager = chat_manager

    async def start(self):
        self.is_running = True

    async def stop(self):
        self.is_running = False

    async def _get_stream_context(self, stream_id: str):
        assert self._chat_manager is not None
        stream = await self._chat_manager.get_stream(stream_id)
        return stream.context if stream else None

    async def _flush_cached_messages_to_unread(self, stream_id: str):
        ctx = await self._get_stream_context(stream_id)
        return ctx.flush_cached_messages() if ctx else []

    def _needs_force_dispatch_for_context(self, context: "DummyContext", unread_count: int) -> bool:
        return unread_count > (self.force_dispatch_unread_threshold or 20)

    async def _process_stream_messages(self, stream_id: str, context: "DummyContext") -> bool:
        res = await self.chatter_manager.process_stream_context(stream_id, context)  # type: ignore[attr-defined]
        return bool(res.get("success", False))

    async def _update_stream_energy(self, stream_id: str, context: "DummyContext") -> None:
        pass

    async def _calculate_interval(self, stream_id: str, has_messages: bool) -> float:
        return 0.005 if has_messages else 0.02

    async def start_stream_loop(self, stream_id: str, force: bool = False) -> bool:
        ctx = await self._get_stream_context(stream_id)
        if not ctx:
            return False
        # create driver
        loop_task = asyncio.create_task(run_chat_stream(stream_id, self))
        ctx.stream_loop_task = loop_task
        self.stats["active_streams"] += 1
        self.stats["total_loops"] += 1
        return True


async def run_chat_stream(stream_id: str, manager: StreamLoopManager) -> None:
    try:
        gen = conversation_loop(
            stream_id=stream_id,
            get_context_func=manager._get_stream_context,
            calculate_interval_func=manager._calculate_interval,
            flush_cache_func=manager._flush_cached_messages_to_unread,
            check_force_dispatch_func=manager._needs_force_dispatch_for_context,
            is_running_func=lambda: manager.is_running,
        )
        async for tick in gen:
            ctx = await manager._get_stream_context(stream_id)
            if not ctx:
                continue
            if ctx.is_chatter_processing:
                continue
            try:
                async with manager._processing_semaphore:
                    ok = await manager._process_stream_messages(stream_id, ctx)
            except Exception:
                ok = False
            manager.stats["total_process_cycles"] += 1
            if not ok:
                manager.stats["total_failures"] += 1
    except asyncio.CancelledError:
        pass


@dataclass
class DummyMessage:
    time: float
    processed_plain_text: str = ""
    display_message: str = ""
    is_at: bool = False
    is_mentioned: bool = False


class DummyContext:
    def __init__(self, stream_id: str, initial_unread: int):
        self.stream_id = stream_id
        self.unread_messages = [DummyMessage(time=time.time()) for _ in range(initial_unread)]
        self.history_messages: list[DummyMessage] = []
        self.is_chatter_processing: bool = False
        self.processing_task: Optional[asyncio.Task] = None
        self.stream_loop_task: Optional[asyncio.Task] = None
        self.triggering_user_id: Optional[str] = None

    def get_unread_messages(self) -> list[DummyMessage]:
        return list(self.unread_messages)

    def flush_cached_messages(self) -> list[DummyMessage]:
        return []

    def get_last_message(self) -> Optional[DummyMessage]:
        return self.unread_messages[-1] if self.unread_messages else None

    def get_history_messages(self, limit: int = 50) -> list[DummyMessage]:
        return self.history_messages[-limit:]


class DummyStream:
    def __init__(self, stream_id: str, ctx: DummyContext):
        self.stream_id = stream_id
        self.context = ctx
        self.group_info = None  # treat as private chat to accelerate
        self._focus_energy = 0.5


class DummyChatManager:
    def __init__(self, streams: dict[str, DummyStream]):
        self._streams = streams

    async def get_stream(self, stream_id: str) -> Optional[DummyStream]:
        return self._streams.get(stream_id)

    def get_all_streams(self) -> dict[str, DummyStream]:
        return self._streams


class DummyChatterManager:
    async def process_stream_context(self, stream_id: str, context: DummyContext) -> dict[str, Any]:
        # Simulate some processing latency and consume one unread message
        await asyncio.sleep(0.01)
        if context.unread_messages:
            context.unread_messages.pop(0)
        return {"success": True}


class BenchStreamLoopManager(StreamLoopManager):
    def __init__(self, chat_manager: DummyChatManager, max_concurrent_streams: int | None = None):
        super().__init__(max_concurrent_streams=max_concurrent_streams)
        self._chat_manager = chat_manager
        self.chatter_manager = DummyChatterManager()

    async def _get_stream_context(self, stream_id: str):  # type: ignore[override]
        stream = await self._chat_manager.get_stream(stream_id)
        return stream.context if stream else None

    async def _flush_cached_messages_to_unread(self, stream_id: str):  # type: ignore[override]
        ctx = await self._get_stream_context(stream_id)
        return ctx.flush_cached_messages() if ctx else []

    def _needs_force_dispatch_for_context(self, context, unread_count: int) -> bool:  # type: ignore[override]
        # force when unread exceeds threshold
        return unread_count > (self.force_dispatch_unread_threshold or 20)

    async def _process_stream_messages(self, stream_id: str, context):  # type: ignore[override]
        # delegate to chatter manager
        res = await self.chatter_manager.process_stream_context(stream_id, context)  # type: ignore[attr-defined]
        return bool(res.get("success", False))

    async def _should_skip_for_mute_group(self, stream_id: str, unread_messages: list) -> bool:
        return False

    async def _update_stream_energy(self, stream_id: str, context):  # type: ignore[override]
        # lightweight: compute based on unread size
        focus = min(1.0, 0.1 + 0.02 * len(context.get_unread_messages()))
        # set for compatibility
        stream = await self._chat_manager.get_stream(stream_id)
        if stream:
            stream._focus_energy = focus


def make_streams(n_streams: int, initial_unread: int) -> dict[str, DummyStream]:
    streams: dict[str, DummyStream] = {}
    for i in range(n_streams):
        sid = f"s{i:04d}"
        ctx = DummyContext(sid, initial_unread)
        streams[sid] = DummyStream(sid, ctx)
    return streams


async def run_benchmark(n_streams: int, initial_unread: int, max_concurrent: Optional[int]) -> dict[str, Any]:
    streams = make_streams(n_streams, initial_unread)
    chat_mgr = DummyChatManager(streams)
    mgr = BenchStreamLoopManager(chat_mgr, max_concurrent_streams=max_concurrent)
    await mgr.start()

    # start loops for all streams
    start_ts = time.time()
    for sid in list(streams.keys()):
        await mgr.start_stream_loop(sid, force=True)

    # run until all unread consumed or timeout
    timeout = 5.0
    end_deadline = start_ts + timeout
    while time.time() < end_deadline:
        remaining = sum(len(s.context.get_unread_messages()) for s in streams.values())
        if remaining == 0:
            break
        await asyncio.sleep(0.02)

    duration = time.time() - start_ts
    total_cycles = mgr.stats.get("total_process_cycles", 0)
    total_failures = mgr.stats.get("total_failures", 0)
    remaining = sum(len(s.context.get_unread_messages()) for s in streams.values())

    # stop all
    await mgr.stop()

    return {
        "n_streams": n_streams,
        "initial_unread": initial_unread,
        "max_concurrent": max_concurrent,
        "duration_sec": duration,
        "total_cycles": total_cycles,
        "total_failures": total_failures,
        "remaining_unread": remaining,
        "throughput_msgs_per_sec": (n_streams * initial_unread - remaining) / max(0.001, duration),
    }


async def main():
    cases = [
        (50, 5, None),   # baseline using configured default
        (50, 5, 5),      # constrained concurrency
        (50, 5, 10),     # moderate concurrency
        (100, 3, 10),    # scale streams
    ]

    print("Running distribution manager benchmark...\n")
    for n_streams, initial_unread, max_concurrent in cases:
        res = await run_benchmark(n_streams, initial_unread, max_concurrent)
        print(
            f"streams={res['n_streams']} unread={res['initial_unread']} max_conc={res['max_concurrent']} | "
            f"dur={res['duration_sec']:.3f}s cycles={res['total_cycles']} fail={res['total_failures']} rem={res['remaining_unread']} "+
            f"thr={res['throughput_msgs_per_sec']:.1f}/s"
        )


if __name__ == "__main__":
    asyncio.run(main())
