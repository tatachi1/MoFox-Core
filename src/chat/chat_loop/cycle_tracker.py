import time
from typing import Dict, Any, Tuple

from src.common.logger import get_logger
from src.chat.chat_loop.hfc_utils import CycleDetail
from .hfc_context import HfcContext

logger = get_logger("hfc.cycle")

class CycleTracker:
    def __init__(self, context: HfcContext):
        self.context = context

    def start_cycle(self) -> Tuple[Dict[str, float], str]:
        self.context.cycle_counter += 1
        self.context.current_cycle_detail = CycleDetail(self.context.cycle_counter)
        self.context.current_cycle_detail.thinking_id = f"tid{str(round(time.time(), 2))}"
        cycle_timers = {}
        return cycle_timers, self.context.current_cycle_detail.thinking_id

    def end_cycle(self, loop_info: Dict[str, Any], cycle_timers: Dict[str, float]):
        if self.context.current_cycle_detail:
            self.context.current_cycle_detail.set_loop_info(loop_info)
            self.context.history_loop.append(self.context.current_cycle_detail)
            self.context.current_cycle_detail.timers = cycle_timers
            self.context.current_cycle_detail.end_time = time.time()
            self.print_cycle_info(cycle_timers)

    def print_cycle_info(self, cycle_timers: Dict[str, float]):
        if not self.context.current_cycle_detail:
            return

        timer_strings = []
        for name, elapsed in cycle_timers.items():
            formatted_time = f"{elapsed * 1000:.2f}毫秒" if elapsed < 1 else f"{elapsed:.2f}秒"
            timer_strings.append(f"{name}: {formatted_time}")

        if self.context.current_cycle_detail.end_time and self.context.current_cycle_detail.start_time:
            duration = self.context.current_cycle_detail.end_time - self.context.current_cycle_detail.start_time
            logger.info(
                f"{self.context.log_prefix} 第{self.context.current_cycle_detail.cycle_id}次思考,"
                f"耗时: {duration:.1f}秒, "
                f"选择动作: {self.context.current_cycle_detail.loop_plan_info.get('action_result', {}).get('action_type', '未知动作')}"
                + (f"\n详情: {'; '.join(timer_strings)}" if timer_strings else "")
            )