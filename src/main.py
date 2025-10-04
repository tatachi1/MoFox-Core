# 再用这个就写一行注释来混提交的我直接全部🌿飞😡
import asyncio
import signal
import sys
import time
import traceback
from functools import partial
from typing import Any

from maim_message import MessageServer
from rich.traceback import install

from src.chat.emoji_system.emoji_manager import get_emoji_manager

# 导入增强记忆系统管理器
from src.chat.memory_system.memory_manager import memory_manager
from src.chat.message_receive.bot import chat_bot
from src.chat.message_receive.chat_stream import get_chat_manager
from src.chat.utils.statistic import OnlineTimeRecordTask, StatisticOutputTask
from src.common.logger import get_logger

# 导入消息API和traceback模块
from src.common.message import get_global_api
from src.common.remote import TelemetryHeartBeatTask
from src.common.server import Server, get_global_server
from src.config.config import global_config
from src.individuality.individuality import Individuality, get_individuality
from src.manager.async_task_manager import async_task_manager
from src.mood.mood_manager import mood_manager
from src.plugin_system.base.component_types import EventType
from src.plugin_system.core.event_manager import event_manager

# from src.api.main import start_api_server
# 导入新的插件管理器
from src.plugin_system.core.plugin_manager import plugin_manager
from src.schedule.monthly_plan_manager import monthly_plan_manager
from src.schedule.schedule_manager import schedule_manager

# 插件系统现在使用统一的插件加载器

install(extra_lines=3)

logger = get_logger("main")


def _task_done_callback(task: asyncio.Task, message_id: str, start_time: float):
    """后台任务完成时的回调函数"""
    end_time = time.time()
    duration = end_time - start_time
    try:
        task.result()  # 如果任务有异常，这里会重新抛出
        logger.debug(f"消息 {message_id} 的后台任务 (ID: {id(task)}) 已成功完成, 耗时: {duration:.2f}s")
    except asyncio.CancelledError:
        logger.warning(f"消息 {message_id} 的后台任务 (ID: {id(task)}) 被取消, 耗时: {duration:.2f}s")
    except Exception:
        logger.error(f"处理消息 {message_id} 的后台任务 (ID: {id(task)}) 出现未捕获的异常, 耗时: {duration:.2f}s:")
        logger.error(traceback.format_exc())


class MainSystem:
    def __init__(self):
        # 使用增强记忆系统
        self.memory_manager = memory_manager

        self.individuality: Individuality = get_individuality()

        # 使用消息API替代直接的FastAPI实例
        self.app: MessageServer = get_global_api()
        self.server: Server = get_global_server()

        # 信号处理现在由bot.py的KeyboardInterrupt处理
        pass

    async def _message_process_wrapper(self, message_data: dict[str, Any]):
        """并行处理消息的包装器"""
        try:
            start_time = time.time()
            message_id = message_data.get("message_info", {}).get("message_id", "UNKNOWN")
            # 创建后台任务
            task = asyncio.create_task(chat_bot.message_process(message_data))
            logger.debug(f"已为消息 {message_id} 创建后台处理任务 (ID: {id(task)})")
            # 添加一个回调函数，当任务完成时，它会被调用
            task.add_done_callback(partial(_task_done_callback, message_id=message_id, start_time=start_time))
        except Exception:
            logger.error("在创建消息处理任务时发生严重错误:")
            logger.error(traceback.format_exc())

    async def initialize(self):
        """初始化系统组件"""
        logger.info(f"正在唤醒{global_config.bot.nickname}......")

        # 其他初始化任务
        await asyncio.gather(self._init_components())
        phrases = [
            ("我们的代码里真的没有bug，只有‘特性’.", 10),
            ("你知道吗？阿范喜欢被切成臊子😡", 10),  # 你加的提示出语法问题来了😡😡😡😡😡😡😡
            ("你知道吗,雅诺狐的耳朵其实很好摸", 5),
            ("你群最高技术力————言柒姐姐！", 20),
            ("初墨小姐宇宙第一(不是)", 10),  # 15
            ("world.execute(me);", 10),
            ("正在尝试连接到MaiBot的服务器...连接失败...，正在转接到maimaiDX", 10),
            ("你的bug就像星星一样多，而我的代码像太阳一样，一出来就看不见了。", 10),
            ("温馨提示：请不要在代码中留下任何魔法数字，除非你知道它的含义。", 10),
            ("世界上只有10种人：懂二进制的和不懂的。", 10),
            ("喵喵~你的麦麦被猫娘入侵了喵~", 15),
            ("恭喜你触发了稀有彩蛋喵：诺狐嗷呜~ ~", 1),
            ("恭喜你！！！你的开发者模式已成功开启，快来加入我们吧！(๑•̀ㅂ•́)و✧   (小声bb:其实是当黑奴)", 10),
        ]
        from random import choices

        # 分离彩蛋和权重
        egg_texts, weights = zip(*phrases, strict=True)

        # 使用choices进行带权重的随机选择
        selected_egg = choices(egg_texts, weights=weights, k=1)
        eggs = selected_egg[0]
        logger.info(f"""
全部系统初始化完成，{global_config.bot.nickname}已成功唤醒
=========================================================
MoFox_Bot(第三方修改版)
全部组件已成功启动!
=========================================================
🌐 项目地址: https://github.com/MoFox-Studio/MoFox_Bot
🏠 官方项目: https://github.com/MaiM-with-u/MaiBot
=========================================================
这是基于原版MMC的社区改版，包含增强功能和优化(同时也有更多的'特性')
=========================================================
小贴士:{eggs}
""")

    async def _init_components(self):
        """初始化其他组件"""
        init_start_time = time.time()

        # 添加在线时间统计任务
        await async_task_manager.add_task(OnlineTimeRecordTask())

        # 添加统计信息输出任务
        await async_task_manager.add_task(StatisticOutputTask())

        # 添加遥测心跳任务
        await async_task_manager.add_task(TelemetryHeartBeatTask())

        # 注册默认事件
        event_manager.init_default_events()

        # 初始化权限管理器
        from src.plugin_system.apis.permission_api import permission_api
        from src.plugin_system.core.permission_manager import PermissionManager

        permission_manager = PermissionManager()
        await permission_manager.initialize()
        permission_api.set_permission_manager(permission_manager)
        logger.info("权限管理器初始化成功")

        # 启动API服务器
        # start_api_server()
        # logger.info("API服务器启动成功")

        # 注册API路由
        try:
            from src.api.message_router import router as message_router
            self.server.register_router(message_router, prefix="/api")
            logger.info("API路由注册成功")
        except ImportError as e:
            logger.error(f"导入API路由失败: {e}")
        except Exception as e:
            logger.error(f"注册API路由时发生错误: {e}")

        # 加载所有actions，包括默认的和插件的
        plugin_manager.load_all_plugins()

        # 处理所有缓存的事件订阅（插件加载完成后）
        event_manager.process_all_pending_subscriptions()

        # 初始化表情管理器
        get_emoji_manager().initialize()
        logger.info("表情包管理器初始化成功")
        
        '''
        # 初始化回复后关系追踪系统
        try:
            from src.plugins.built_in.affinity_flow_chatter.interest_scoring import chatter_interest_scoring_system
            from src.plugins.built_in.affinity_flow_chatter.relationship_tracker import ChatterRelationshipTracker

            relationship_tracker = ChatterRelationshipTracker(interest_scoring_system=chatter_interest_scoring_system)
            chatter_interest_scoring_system.relationship_tracker = relationship_tracker
            logger.info("回复后关系追踪系统初始化成功")
        except Exception as e:
            logger.error(f"回复后关系追踪系统初始化失败: {e}")
            relationship_tracker = None
        '''
  
        # 启动情绪管理器
        await mood_manager.start()
        logger.info("情绪管理器初始化成功")

        # 初始化聊天管理器
        await get_chat_manager()._initialize()
        asyncio.create_task(get_chat_manager()._auto_save_task())
        logger.info("聊天管理器初始化成功")

        # 初始化增强记忆系统
        await self.memory_manager.initialize()
        logger.info("增强记忆系统初始化成功")

        # 老记忆系统已完全删除

        # 初始化消息兴趣值计算组件
        await self._initialize_interest_calculator()

        # 初始化LPMM知识库
        from src.chat.knowledge.knowledge_lib import initialize_lpmm_knowledge

        initialize_lpmm_knowledge()
        logger.info("LPMM知识库初始化成功")

        # 异步记忆管理器已禁用，增强记忆系统有内置的优化机制
        logger.info("异步记忆管理器已禁用 - 使用增强记忆系统内置优化")

        # await asyncio.sleep(0.5) #防止logger输出飞了

        # 将bot.py中的chat_bot.message_process消息处理函数注册到api.py的消息处理基类中
        self.app.register_message_handler(self._message_process_wrapper)

        # 启动消息重组器的清理任务
        from src.utils.message_chunker import reassembler

        await reassembler.start_cleanup_task()
        logger.info("消息重组器已启动")

        # 启动消息管理器
        from src.chat.message_manager import message_manager

        await message_manager.start()
        logger.info("消息管理器已启动")

        # 初始化个体特征
        await self.individuality.initialize()

        # 初始化月度计划管理器
        if global_config.planning_system.monthly_plan_enable:
            logger.info("正在初始化月度计划管理器...")
            try:
                await monthly_plan_manager.initialize()
                logger.info("月度计划管理器初始化成功")
            except Exception as e:
                logger.error(f"月度计划管理器初始化失败: {e}")

        # 初始化日程管理器
        if global_config.planning_system.schedule_enable:
            logger.info("日程表功能已启用，正在初始化管理器...")
            await schedule_manager.initialize()
            logger.info("日程表管理器初始化成功。")

        try:
            await event_manager.trigger_event(EventType.ON_START, permission_group="SYSTEM")
            init_time = int(1000 * (time.time() - init_start_time))
            logger.info(f"初始化完成，神经元放电{init_time}次")
        except Exception as e:
            logger.error(f"启动大脑和外部世界失败: {e}")
            raise

    async def schedule_tasks(self):
        """调度定时任务"""
        try:
            while True:
                try:
                    tasks = [
                        get_emoji_manager().start_periodic_check_register(),
                        self.app.run(),
                        self.server.run(),
                    ]

                    # 增强记忆系统不需要定时任务，已禁用原有记忆系统的定时任务
                    # 使用 return_exceptions=True 防止单个任务失败导致整个程序崩溃
                    await asyncio.gather(*tasks, return_exceptions=True)

                except (ConnectionResetError, OSError) as e:
                    logger.warning(f"网络连接发生错误，尝试重新启动任务: {e}")
                    await asyncio.sleep(1)  # 短暂等待后重新开始
                    continue
                except asyncio.InvalidStateError as e:
                    logger.error(f"异步任务状态无效，重新初始化: {e}")
                    await asyncio.sleep(2)  # 等待更长时间让系统稳定
                    continue
                except Exception as e:
                    logger.error(f"调度任务发生未预期异常: {e}")
                    logger.error(traceback.format_exc())
                    await asyncio.sleep(5)  # 发生其他错误时等待更长时间
                    continue

        except asyncio.CancelledError:
            logger.info("调度任务被取消，正在退出...")
        except Exception as e:
            logger.error(f"调度任务发生致命异常: {e}")
            logger.error(traceback.format_exc())
            raise

    async def shutdown(self):
        """关闭系统组件"""
        logger.info("正在关闭MainSystem...")

        # 关闭表情管理器
        try:
            get_emoji_manager().shutdown()
            logger.info("表情管理器已关闭")
        except Exception as e:
            logger.warning(f"关闭表情管理器时出错: {e}")

        # 关闭服务器
        try:
            if self.server:
                await self.server.shutdown()
                logger.info("服务器已关闭")
        except Exception as e:
            logger.warning(f"关闭服务器时出错: {e}")

        # 关闭应用 (MessageServer可能没有shutdown方法)
        try:
            if self.app:
                if hasattr(self.app, 'shutdown'):
                    await self.app.shutdown()
                    logger.info("应用已关闭")
                elif hasattr(self.app, 'stop'):
                    await self.app.stop()
                    logger.info("应用已停止")
                else:
                    logger.info("应用没有shutdown方法，跳过关闭")
        except Exception as e:
            logger.warning(f"关闭应用时出错: {e}")

        logger.info("MainSystem关闭完成")

    # 老记忆系统的定时任务已删除 - 增强记忆系统使用内置的维护机制


async def main():
    """主函数"""
    system = MainSystem()
    await asyncio.gather(
        system.initialize(),
        system.schedule_tasks(),
    )


if __name__ == "__main__":
    asyncio.run(main())

    