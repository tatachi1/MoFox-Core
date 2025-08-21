import random
from typing import Dict, Any, TYPE_CHECKING

from src.common.logger import get_logger
from src.config.config import global_config
from src.chat.willing.willing_manager import get_willing_manager
from .hfc_context import HfcContext

if TYPE_CHECKING:
    from .cycle_processor import CycleProcessor

logger = get_logger("hfc.normal_mode")

class NormalModeHandler:
    def __init__(self, context: HfcContext, cycle_processor: "CycleProcessor"):
        self.context = context
        self.cycle_processor = cycle_processor
        self.willing_manager = get_willing_manager()

    async def handle_message(self, message_data: Dict[str, Any]) -> bool:
        if not self.context.chat_stream:
            return False

        interested_rate = message_data.get("interest_value") or 0.0
        self.willing_manager.setup(message_data, self.context.chat_stream)
        reply_probability = await self.willing_manager.get_reply_probability(message_data.get("message_id", ""))

        if reply_probability < 1:
            additional_config = message_data.get("additional_config", {})
            if additional_config and "maimcore_reply_probability_gain" in additional_config:
                reply_probability += additional_config["maimcore_reply_probability_gain"]
                reply_probability = min(max(reply_probability, 0), 1)

        talk_frequency = global_config.chat.get_current_talk_frequency(self.context.stream_id)
        reply_probability = talk_frequency * reply_probability

        if message_data.get("is_emoji") or message_data.get("is_picid"):
            reply_probability = 0

        mes_name = self.context.chat_stream.group_info.group_name if self.context.chat_stream.group_info else "私聊"
        if reply_probability > 0.05:
            logger.info(
                f"[{mes_name}]"
                f"{message_data.get('user_nickname')}:"
                f"{message_data.get('processed_plain_text')}[兴趣:{interested_rate:.2f}][回复概率:{reply_probability * 100:.1f}%]"
            )

        if random.random() < reply_probability:
            await self.willing_manager.before_generate_reply_handle(message_data.get("message_id", ""))
            await self.cycle_processor.observe(message_data=message_data)
            return True

        self.willing_manager.delete(message_data.get("message_id", ""))
        return False