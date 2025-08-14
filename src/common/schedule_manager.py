import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from src.common.database.sqlalchemy_models import Schedule, get_db_session
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest
from src.common.logger import get_logger
from json_repair import repair_json

logger = get_logger("schedule_manager")

# 默认的日程生成指导原则
DEFAULT_SCHEDULE_GUIDELINES = """
我希望你每天都能过得充实而有趣。
请确保你的日程里有学习新知识的时间，这是你成长的关键。
但也不要忘记放松，可以看看视频、听听音乐或者玩玩游戏。
晚上我希望你能多和朋友们交流，维系好彼此的关系。
另外，请保证充足的休眠时间来处理和整合一天的数据。
"""

class ScheduleManager:
    def __init__(self):
        self.today_schedule: Optional[List[Dict[str, Any]]] = None
        self.llm = LLMRequest(model_set=model_config.model_task_config.schedule_generator, request_type="schedule")

    async def load_or_generate_today_schedule(self):
        # 检查是否启用日程管理功能
        if not global_config.schedule.enable:
            logger.info("日程管理功能已禁用，跳过日程加载和生成。")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            with get_db_session() as session:
                schedule_record = session.query(Schedule).filter(Schedule.date == today_str).first()
                if schedule_record:
                    logger.info(f"从数据库加载今天的日程 ({today_str})。")
                    # SQLAlchemy 对象属性直接访问，确保类型转换
                    schedule_data_str = str(schedule_record.schedule_data)
                    
                    try:
                        schedule_data = json.loads(schedule_data_str)
                        
                        # 验证日程数据格式
                        if self._validate_schedule_data(schedule_data):
                            self.today_schedule = schedule_data
                            schedule_str = f"已成功加载今天的日程 ({today_str})：\n"
                            if self.today_schedule:
                                for item in self.today_schedule:
                                    schedule_str += f"  - {item.get('time_range', '未知时间')}: {item.get('activity', '未知活动')}\n"
                            logger.info(schedule_str)
                        else:
                            logger.warning(f"数据库中的日程数据格式无效，将重新生成日程")
                            await self.generate_and_save_schedule()
                    except json.JSONDecodeError as e:
                        logger.error(f"日程数据JSON解析失败: {e}，将重新生成日程")
                        await self.generate_and_save_schedule()
                else:
                    logger.info(f"数据库中未找到今天的日程 ({today_str})，将调用 LLM 生成。")
                    await self.generate_and_save_schedule()
        except Exception as e:
            logger.error(f"加载或生成日程时出错: {e}")

    async def generate_and_save_schedule(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        weekday = datetime.now().strftime("%A")
        
        guidelines = global_config.schedule.guidelines or DEFAULT_SCHEDULE_GUIDELINES
        personality = global_config.personality.personality_core
        personality_side = global_config.personality.personality_side

        prompt = f"""
我，{global_config.bot.nickname}，需要为自己规划一份今天（{today_str}，星期{weekday}）的详细日程安排。

**关于我**:
- **核心人设**: {personality}
- **具体习惯与兴趣**: 
{personality_side}

**我今天的规划原则**: 
{guidelines}

**任务**:
请你扮演我，以我的身份和口吻，为我生成一份日程表。
- 必须以一个完整的、有效的JSON数组格式返回。
- 数组中的每个对象都必须包含 "time_range" 和 "activity" 两个键。
- 时间范围必须覆盖全部24小时。
- 不要包含任何JSON以外的解释性文字或代码块标记。

**示例**:
[
    {{"time_range": "00:00-07:00", "activity": "进入梦乡，处理数据"}},
    {{"time_range": "07:00-08:00", "activity": "起床伸个懒腰，看看今天有什么新闻"}}
]
"""
        
        try:
            response, _ = await self.llm.generate_response_async(prompt)
            schedule_data = json.loads(repair_json(response))
            
            # 验证生成的日程数据格式
            if not self._validate_schedule_data(schedule_data):
                logger.error("LLM生成的日程数据格式无效")
                return
            
            with get_db_session() as session:
                # 检查是否已存在今天的日程
                existing_schedule = session.query(Schedule).filter(Schedule.date == today_str).first()
                if existing_schedule:
                    # 更新现有日程 - 通过setattr或直接赋值
                    existing_schedule.schedule_data = json.dumps(schedule_data)
                    existing_schedule.updated_at = datetime.now()
                else:
                    # 创建新日程
                    new_schedule = Schedule()
                    new_schedule.date = today_str
                    new_schedule.schedule_data = json.dumps(schedule_data)
                    session.add(new_schedule)
            
            # 美化输出
            schedule_str = f"已成功生成并保存今天的日程 ({today_str})：\n"
            for item in schedule_data:
                schedule_str += f"  - {item.get('time_range', '未知时间')}: {item.get('activity', '未知活动')}\n"
            logger.info(schedule_str)
            
            self.today_schedule = schedule_data

        except Exception as e:
            logger.error(f"调用 LLM 生成或保存日程失败: {e}")

    def get_current_activity(self) -> Optional[str]:
        # 检查是否启用日程管理功能
        if not global_config.schedule.enable:
            return None

        if not self.today_schedule:
            return None

        now = datetime.now().time()
        for event in self.today_schedule:
            try:
                time_range = event.get("time_range")
                activity = event.get("activity")
                
                if not time_range or not activity:
                    logger.warning(f"日程事件缺少必要字段: {event}")
                    continue
                    
                start_str, end_str = time_range.split('-')
                start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
                end_time = datetime.strptime(end_str.strip(), "%H:%M").time()

                if start_time <= end_time:
                    if start_time <= now < end_time:
                        return activity
                else:  # 跨天事件
                    if now >= start_time or now < end_time:
                        return activity
            except (ValueError, KeyError, AttributeError) as e:
                logger.warning(f"解析日程事件失败: {event}, 错误: {e}")
                continue
        return None

    def _validate_schedule_data(self, schedule_data) -> bool:
        """验证日程数据格式是否正确"""
        if not isinstance(schedule_data, list):
            logger.warning("日程数据不是列表格式")
            return False
        
        for item in schedule_data:
            if not isinstance(item, dict):
                logger.warning(f"日程项不是字典格式: {item}")
                return False
            
            if 'time_range' not in item or 'activity' not in item:
                logger.warning(f"日程项缺少必要字段 (time_range 或 activity): {item}")
                return False
                
            if not isinstance(item['time_range'], str) or not isinstance(item['activity'], str):
                logger.warning(f"日程项字段类型不正确: {item}")
                return False
        
        return True

schedule_manager = ScheduleManager()