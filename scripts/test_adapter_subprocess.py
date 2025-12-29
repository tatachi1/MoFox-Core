import asyncio

from src.common.core_sink_manager import (
    initialize_core_sink_manager,
    shutdown_core_sink_manager,
)
from src.common.logger import get_logger, initialize_logging
from src.plugin_system.core.adapter_manager import get_adapter_manager
from src.testing.test_subproc_adapter import TestSubprocAdapter

logger = get_logger("test_subproc")


async def main() -> None:
    initialize_logging()

    # 初始化 CoreSinkManager（主程序通常会做这一步）
    await initialize_core_sink_manager()

    am = get_adapter_manager()

    # 注册并启动子进程适配器
    am.register_adapter(TestSubprocAdapter, plugin=None)
    ok = await am.start_adapter(TestSubprocAdapter.adapter_name)
    logger.info(f"启动结果: {ok}")
    if not ok:
        await shutdown_core_sink_manager()
        return

    # 等待片刻，查看存活状态
    await asyncio.sleep(1.0)
    status = am.list_adapters().get(TestSubprocAdapter.adapter_name, {})
    logger.info(f"适配器状态: {status}")

    # 停止并退出
    await am.stop_adapter(TestSubprocAdapter.adapter_name)
    await shutdown_core_sink_manager()
    logger.info("测试结束")


if __name__ == "__main__":
    asyncio.run(main())
