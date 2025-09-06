from datetime import datetime, time
from typing import Optional

from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("time_checker")


class TimeChecker:
    def __init__(self, schedule_source):
        self.schedule_source = schedule_source

    def is_in_theoretical_sleep_time(self, now_time: time) -> tuple[bool, Optional[str]]:
        if global_config.sleep_system.sleep_by_schedule:
            if self.schedule_source.get_today_schedule():
                return self._is_in_schedule_sleep_time(now_time)
            else:
                return self._is_in_fixed_sleep_time(now_time)
        else:
            return self._is_in_fixed_sleep_time(now_time)

    def _is_in_schedule_sleep_time(self, now_time: time) -> tuple[bool, Optional[str]]:
        """检查当前时间是否落在日程表的任何一个睡眠活动中"""
        sleep_keywords = ["休眠", "睡觉", "梦乡"]
        today_schedule = self.schedule_source.get_today_schedule()
        if today_schedule:
            for event in today_schedule:
                try:
                    activity = event.get("activity", "").strip()
                    time_range = event.get("time_range")

                    if not activity or not time_range:
                        continue

                    if any(keyword in activity for keyword in sleep_keywords):
                        start_str, end_str = time_range.split("-")
                        start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
                        end_time = datetime.strptime(end_str.strip(), "%H:%M").time()

                        if start_time <= end_time:  # 同一天
                            if start_time <= now_time < end_time:
                                return True, activity
                        else:  # 跨天
                            if now_time >= start_time or now_time < end_time:
                                return True, activity
                except (ValueError, KeyError, AttributeError) as e:
                    logger.warning(f"解析日程事件时出错: {event}, 错误: {e}")
                    continue
        return False, None

    def _is_in_fixed_sleep_time(self, now_time: time) -> tuple[bool, Optional[str]]:
        """检查当前时间是否在固定的睡眠时间内"""
        try:
            start_time_str = global_config.sleep_system.fixed_sleep_time
            end_time_str = global_config.sleep_system.fixed_wake_up_time
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()

            if start_time <= end_time:
                if start_time <= now_time < end_time:
                    return True, "固定睡眠时间"
            else:
                if now_time >= start_time or now_time < end_time:
                    return True, "固定睡眠时间"
        except ValueError as e:
            logger.error(f"固定的睡眠时间格式不正确，请使用 HH:MM 格式: {e}")
        return False, None