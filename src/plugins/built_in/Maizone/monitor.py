import asyncio
import random
import time
import traceback
from typing import List, Dict, Any

from src.common.logger import get_logger
from src.plugin_system.apis import llm_api, config_api

# 导入工具模块
import sys
import os
sys.path.append(os.path.dirname(__file__))

from qzone_utils import QZoneManager

# 获取日志记录器
logger = get_logger('MaiZone-Monitor')


class MonitorManager:
    """监控管理器 - 负责自动监控好友说说并点赞评论"""
    
    def __init__(self, plugin):
        """初始化监控管理器"""
        self.plugin = plugin
        self.is_running = False
        self.task = None
        self.last_check_time = 0
        
        logger.info("监控管理器初始化完成")

    async def start(self):
        """启动监控任务"""
        if self.is_running:
            logger.warning("监控任务已在运行中")
            return
            
        self.is_running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("说说监控任务已启动")

    async def stop(self):
        """停止监控任务"""
        if not self.is_running:
            return
            
        self.is_running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                logger.info("监控任务已被取消")
                
        logger.info("说说监控任务已停止")

    async def _monitor_loop(self):
        """监控任务主循环"""
        while self.is_running:
            try:
                # 获取监控间隔配置
                interval_minutes = int(self.plugin.get_config("monitor.interval_minutes", 10) or 10)
                
                # 等待指定时间间隔
                await asyncio.sleep(interval_minutes * 60)
                
                # 执行监控检查
                await self._check_and_process_feeds()
                
            except asyncio.CancelledError:
                logger.info("监控循环被取消")
                break
            except Exception as e:
                logger.error(f"监控任务出错: {str(e)}")
                logger.error(traceback.format_exc())
                # 出错后等待5分钟再重试
                await asyncio.sleep(300)

    async def _check_and_process_feeds(self):
        """检查并处理好友说说"""
        try:
            # 获取配置
            qq_account = config_api.get_global_config("bot.qq_account", "")
            port = str(self.plugin.get_config("plugin.http_port", "3000"))
            host = str(self.plugin.get_config("plugin.http_host", "127.0.0.1"))
            read_num = 10  # 监控时读取较少的说说数量
            
            logger.info("监控任务: 开始检查好友说说")
            
            # 创建QZone管理器
            qzone_manager = QZoneManager(port, host)
            
            # 获取监控说说列表
            feeds_list = await qzone_manager.monitor_read_feed(qq_account, read_num)
            
            if not feeds_list:
                logger.info("监控任务: 未发现新说说")
                return
                
            logger.info(f"监控任务: 发现 {len(feeds_list)} 条新说说")
            
            # 处理每条说说
            for feed in feeds_list:
                try:
                    await self._process_monitor_feed(feed, qzone_manager)
                    # 每条说说之间随机延迟
                    await asyncio.sleep(3 + random.random() * 2)
                except Exception as e:
                    logger.error(f"处理监控说说失败: {str(e)}")
                    
        except Exception as e:
            logger.error(f"监控检查失败: {str(e)}")

    async def _process_monitor_feed(self, feed: Dict[str, Any], qzone_manager: QZoneManager):
        """处理单条监控说说"""
        try:
            # 提取说说信息
            target_qq = feed.get("target_qq", "")
            tid = feed.get("tid", "")
            content = feed.get("content", "")
            images = feed.get("images", [])
            rt_con = feed.get("rt_con", "")
            
            # 构建完整内容用于显示
            full_content = content
            if images:
                full_content += f" [图片: {len(images)}张]"
            if rt_con:
                full_content += f" [转发: {rt_con[:20]}...]"
            
            logger.info(f"监控处理说说: {target_qq} - {full_content[:30]}...")
            
            # 获取配置
            qq_account = config_api.get_global_config("bot.qq_account", "")
            like_possibility = float(self.plugin.get_config("read.like_possibility", 1.0) or 1.0)
            comment_possibility = float(self.plugin.get_config("read.comment_possibility", 0.3) or 0.3)
            
            # 随机决定是否评论
            if random.random() <= comment_possibility:
                comment = await self._generate_monitor_comment(content, rt_con, target_qq)
                if comment:
                    success = await qzone_manager.comment_feed(qq_account, target_qq, tid, comment)
                    if success:
                        logger.info(f"监控评论成功: '{comment}'")
                    else:
                        logger.error(f"监控评论失败: {content[:20]}...")
            
            # 随机决定是否点赞
            if random.random() <= like_possibility:
                success = await qzone_manager.like_feed(qq_account, target_qq, tid)
                if success:
                    logger.info(f"监控点赞成功: {content[:20]}...")
                else:
                    logger.error(f"监控点赞失败: {content[:20]}...")
                    
        except Exception as e:
            logger.error(f"处理监控说说异常: {str(e)}")

    async def _generate_monitor_comment(self, content: str, rt_con: str, target_qq: str) -> str:
        """生成监控评论内容"""
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

            # 构建提示词
            if not rt_con:
                prompt = f"""
                你是'{bot_personality}'，你正在浏览你好友'{target_qq}'的QQ空间，
                你看到了你的好友'{target_qq}'qq空间上内容是'{content}'的说说，你想要发表你的一条评论，
                {bot_expression}，回复的平淡一些，简短一些，说中文，
                不要刻意突出自身学科背景，不要浮夸，不要夸张修辞，不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。只输出回复内容
                """
            else:
                prompt = f"""
                你是'{bot_personality}'，你正在浏览你好友'{target_qq}'的QQ空间，
                你看到了你的好友'{target_qq}'在qq空间上转发了一条内容为'{rt_con}'的说说，你的好友的评论为'{content}'
                你想要发表你的一条评论，{bot_expression}，回复的平淡一些，简短一些，说中文，
                不要刻意突出自身学科背景，不要浮夸，不要夸张修辞，不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。只输出回复内容
                """
            
            logger.info(f"正在为 {target_qq} 的说说生成评论...")
            
            # 生成评论
            success, comment, reasoning, model_name = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=model_config,
                request_type="story.generate",
                temperature=0.3,
                max_tokens=1000
            )

            if success:
                logger.info(f"成功生成监控评论: '{comment}'")
                return comment
            else:
                logger.error("生成监控评论失败")
                return ""
                
        except Exception as e:
            logger.error(f"生成监控评论异常: {str(e)}")
            return ""

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        return {
            "is_running": self.is_running,
            "interval_minutes": self.plugin.get_config("monitor.interval_minutes", 10),
            "last_check_time": self.last_check_time,
            "enabled": self.plugin.get_config("monitor.enable_auto_monitor", False)
        }

    async def manual_check(self) -> Dict[str, Any]:
        """手动执行一次监控检查"""
        try:
            logger.info("执行手动监控检查")
            await self._check_and_process_feeds()
            
            return {
                "success": True,
                "message": "手动监控检查完成",
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"手动监控检查失败: {str(e)}")
            return {
                "success": False,
                "message": f"手动监控检查失败: {str(e)}",
                "timestamp": time.time()
            }
