from typing import List, Optional, Dict, Any
import time
from src.chat.message_receive.chat_stream import ChatStream, get_chat_manager
from src.person_info.relationship_builder_manager import RelationshipBuilder
from src.chat.express.expression_learner import ExpressionLearner
from src.plugin_system.base.component_types import ChatMode
from src.chat.planner_actions.action_manager import ActionManager
from src.chat.chat_loop.hfc_utils import CycleDetail

class HfcContext:
    def __init__(self, chat_id: str):
        self.stream_id: str = chat_id
        self.chat_stream: Optional[ChatStream] = get_chat_manager().get_stream(self.stream_id)
        if not self.chat_stream:
            raise ValueError(f"无法找到聊天流: {self.stream_id}")

        self.log_prefix = f"[{get_chat_manager().get_stream_name(self.stream_id) or self.stream_id}]"
        
        self.relationship_builder: Optional[RelationshipBuilder] = None
        self.expression_learner: Optional[ExpressionLearner] = None
        
        self.loop_mode = ChatMode.NORMAL
        self.energy_value = 5.0
        
        self.last_message_time = time.time()
        self.last_read_time = time.time() - 1
        
        self.action_manager = ActionManager()
        
        self.running: bool = False
        
        self.history_loop: List[CycleDetail] = []
        self.cycle_counter = 0
        self.current_cycle_detail: Optional[CycleDetail] = None