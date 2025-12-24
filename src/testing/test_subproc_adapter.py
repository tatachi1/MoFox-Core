from __future__ import annotations

from src.common.logger import get_logger

logger = get_logger("test_subproc_adapter")


class TestSubprocAdapter:
    adapter_name = "test_subproc_adapter"
    adapter_version = "0.0.1"
    platform = "test"
    # 关键：标记在子进程运行
    run_in_subprocess = True

    def __init__(self, core_sink, plugin=None, **kwargs):
        self.core_sink = core_sink
        self.plugin = plugin
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("TestSubprocAdapter 子进程已启动")

    async def stop(self) -> None:
        if self._running:
            logger.info("TestSubprocAdapter 子进程即将停止")
        self._running = False
