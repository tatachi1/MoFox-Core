from enum import Enum, auto
from datetime import datetime
from src.common.logger import get_logger
from src.manager.local_store_manager import local_storage

logger = get_logger("sleep_state")


class SleepState(Enum):
    """睡眠状态枚举"""

    AWAKE = auto()
    INSOMNIA = auto()
    PREPARING_SLEEP = auto()
    SLEEPING = auto()
    WOKEN_UP = auto()


class SleepStateSerializer:
    @staticmethod
    def save(state_data: dict):
        """将当前睡眠状态保存到本地存储"""
        try:
            state = {
                "current_state": state_data["_current_state"].name,
                "sleep_buffer_end_time_ts": state_data["_sleep_buffer_end_time"].timestamp()
                if state_data["_sleep_buffer_end_time"]
                else None,
                "total_delayed_minutes_today": state_data["_total_delayed_minutes_today"],
                "last_sleep_check_date_str": state_data["_last_sleep_check_date"].isoformat()
                if state_data["_last_sleep_check_date"]
                else None,
                "re_sleep_attempt_time_ts": state_data["_re_sleep_attempt_time"].timestamp()
                if state_data["_re_sleep_attempt_time"]
                else None,
            }
            local_storage["schedule_sleep_state"] = state
            logger.debug(f"已保存睡眠状态: {state}")
        except Exception as e:
            logger.error(f"保存睡眠状态失败: {e}")

    @staticmethod
    def load() -> dict:
        """从本地存储加载睡眠状态"""
        state_data = {
            "_current_state": SleepState.AWAKE,
            "_sleep_buffer_end_time": None,
            "_total_delayed_minutes_today": 0,
            "_last_sleep_check_date": None,
            "_re_sleep_attempt_time": None,
        }
        try:
            state = local_storage["schedule_sleep_state"]
            if state and isinstance(state, dict):
                state_name = state.get("current_state")
                if state_name and hasattr(SleepState, state_name):
                    state_data["_current_state"] = SleepState[state_name]

                end_time_ts = state.get("sleep_buffer_end_time_ts")
                if end_time_ts:
                    state_data["_sleep_buffer_end_time"] = datetime.fromtimestamp(end_time_ts)

                re_sleep_ts = state.get("re_sleep_attempt_time_ts")
                if re_sleep_ts:
                    state_data["_re_sleep_attempt_time"] = datetime.fromtimestamp(re_sleep_ts)

                state_data["_total_delayed_minutes_today"] = state.get("total_delayed_minutes_today", 0)

                date_str = state.get("last_sleep_check_date_str")
                if date_str:
                    state_data["_last_sleep_check_date"] = datetime.fromisoformat(date_str).date()

                logger.info(f"成功从本地存储加载睡眠状态: {state}")
        except Exception as e:
            logger.warning(f"加载睡眠状态失败，将使用默认值: {e}")
        return state_data