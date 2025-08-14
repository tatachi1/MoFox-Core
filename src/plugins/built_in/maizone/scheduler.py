import asyncio
import datetime
import time
import traceback
import os
from typing import Dict, Any

from src.common.logger import get_logger
from src.plugin_system.apis import llm_api, config_api
from src.manager.schedule_manager import schedule_manager

# 导入工具模块
import sys
sys.path.append(os.path.dirname(__file__))

from qzone_utils import QZoneManager, get_send_history

# 获取日志记录器
logger = get_logger('MaiZone-Scheduler')


class ScheduleManager:
    """定时任务管理器 - 根据日程表定时发送说说"""
    
    def __init__(self, plugin):
        """初始化定时任务管理器"""
        self.plugin = plugin
        self.is_running = False
        self.task = None
        self.last_activity_hash = None  # 记录上次处理的活动哈希，避免重复发送
        
        logger.info("定时任务管理器初始化完成 - 将根据日程表发送说说")

    async def start(self):
        """启动定时任务"""
        if self.is_running:
            logger.warning("定时任务已在运行中")
            return
            
        self.is_running = True
        self.task = asyncio.create_task(self._schedule_loop())
        logger.info("定时发送说说任务已启动 - 基于日程表")

    async def stop(self):
        """停止定时任务"""
        if not self.is_running:
            return
            
        self.is_running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                logger.info("定时任务已被取消")
                
        logger.info("定时发送说说任务已停止")

    async def _schedule_loop(self):
        """定时任务主循环 - 根据日程表检查活动"""
        while self.is_running:
            try:
                # 检查定时任务是否启用
                if not self.plugin.get_config("schedule.enable_schedule", False):
                    logger.info("定时任务已禁用，等待下次检查")
                    await asyncio.sleep(60)
                    continue
                
                # 获取当前活动
                current_activity = schedule_manager.get_current_activity()
                
                if current_activity:
                    # 生成当前活动的哈希以避免重复发送
                    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    activity_hash = f"{current_time}_{current_activity}"
                    
                    # 检查是否已经为这个活动发送过说说
                    if activity_hash != self.last_activity_hash:
                        logger.info(f"检测到新的日程活动: {current_activity}")
                        await self._execute_schedule_based_send(current_activity)
                        self.last_activity_hash = activity_hash
                    else:
                        logger.debug(f"当前活动已处理过: {current_activity}")
                else:
                    logger.debug("当前时间没有日程活动")
                
                # 每5分钟检查一次，避免频繁检查
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                logger.info("定时任务循环被取消")
                break
            except Exception as e:
                logger.error(f"定时任务循环出错: {str(e)}")
                logger.error(traceback.format_exc())
                # 出错后等待5分钟再重试
                await asyncio.sleep(300)

    async def _execute_schedule_based_send(self, activity: str) -> bool:
        """根据日程活动执行发送任务"""
        try:
            logger.info(f"根据日程活动生成说说: {activity}")
            
            # 生成基于活动的说说内容
            story = await self._generate_activity_story(activity)
            if not story:
                logger.error("生成活动相关说说内容失败")
                return False

            logger.info(f"基于日程活动生成说说内容: '{story}'")

            # 处理配图
            await self._handle_images(story)
            
            # 发送说说
            success = await self._send_scheduled_feed(story)
            
            if success:
                logger.info(f"基于日程活动的说说发送成功: {story}")
            else:
                logger.error(f"基于日程活动的说说发送失败: {activity}")
            
            return success
            
        except Exception as e:
            logger.error(f"执行基于日程的发送任务失败: {str(e)}")
            return False

    async def _generate_activity_story(self, activity: str) -> str:
        """根据日程活动生成说说内容"""
        try:
            # 获取模型配置
            models = llm_api.get_available_models()
            text_model = str(self.plugin.get_config("models.text_model", "replyer_1"))
            model_config = models.get(text_model)
            
            if not model_config:
                logger.error("未配置LLM模型")
                return ""

            # 获取机器人信息
            bot_personality = config_api.get_global_config("personality.personality_core", "一个机器人")
            bot_expression = config_api.get_global_config("expression.expression_style", "内容积极向上")
            qq_account = config_api.get_global_config("bot.qq_account", "")

            # 构建基于活动的提示词
            prompt = f"""
            你是'{bot_personality}'，根据你当前的日程安排，你正在'{activity}'。
            请基于这个活动写一条说说发表在qq空间上，
            {bot_expression}
            说说内容应该自然地反映你正在做的事情或你的想法，
            不要刻意突出自身学科背景，不要浮夸，不要夸张修辞，可以适当使用颜文字，
            只输出一条说说正文的内容，不要有其他的任何正文以外的冗余输出
            
            注意：
            - 如果活动是学习相关的，可以分享学习心得或感受
            - 如果活动是休息相关的，可以分享放松的感受
            - 如果活动是日常生活相关的，可以分享生活感悟
            - 让说说内容贴近你当前正在做的事情，显得自然真实
            """

            # 添加历史记录避免重复
            prompt += "\n\n以下是你最近发过的说说，写新说说时注意不要在相隔不长的时间发送相似内容的说说\n"
            history_block = await get_send_history(qq_account)
            if history_block:
                prompt += history_block

            # 生成内容
            success, story, reasoning, model_name = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=model_config,
                request_type="story.generate",
                temperature=0.7,  # 稍微提高创造性
                max_tokens=1000
            )

            if success:
                return story
            else:
                logger.error("生成基于活动的说说内容失败")
                return ""
                
        except Exception as e:
            logger.error(f"生成基于活动的说说内容异常: {str(e)}")
            return ""

    async def _handle_images(self, story: str):
        """处理定时说说配图"""
        try:
            enable_ai_image = bool(self.plugin.get_config("send.enable_ai_image", False))
            apikey = str(self.plugin.get_config("models.siliconflow_apikey", ""))
            image_dir = str(self.plugin.get_config("send.image_directory", "./plugins/Maizone/images"))
            image_num = int(self.plugin.get_config("send.ai_image_number", 1) or 1)
            
            if enable_ai_image and apikey:
                from qzone_utils import generate_image_by_sf
                await generate_image_by_sf(
                    api_key=apikey, 
                    story=story, 
                    image_dir=image_dir, 
                    batch_size=image_num
                )
                logger.info("基于日程活动的AI配图生成完成")
            elif enable_ai_image and not apikey:
                logger.warning('启用了AI配图但未填写API密钥')
                
        except Exception as e:
            logger.error(f"处理基于日程的说说配图失败: {str(e)}")

    async def _send_scheduled_feed(self, story: str) -> bool:
        """发送基于日程的说说"""
        try:
            # 获取配置
            qq_account = config_api.get_global_config("bot.qq_account", "")
            enable_image = self.plugin.get_config("send.enable_image", False)
            image_dir = str(self.plugin.get_config("send.image_directory", "./plugins/Maizone/images"))

            # 创建QZone管理器并发送 (定时任务不需要stream_id)
            qzone_manager = QZoneManager()
            success = await qzone_manager.send_feed(story, image_dir, qq_account, enable_image)
            
            if success:
                logger.info(f"基于日程的说说发送成功: {story}")
            else:
                logger.error("基于日程的说说发送失败")
                
            return success
            
        except Exception as e:
            logger.error(f"发送基于日程的说说失败: {str(e)}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """获取定时任务状态"""
        current_activity = schedule_manager.get_current_activity()
        return {
            "is_running": self.is_running,
            "enabled": self.plugin.get_config("schedule.enable_schedule", False),
            "schedule_mode": "based_on_daily_schedule",
            "current_activity": current_activity,
            "last_activity_hash": self.last_activity_hash
        }