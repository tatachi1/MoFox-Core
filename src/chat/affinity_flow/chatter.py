"""
亲和力聊天处理器
单个聊天流的处理器，负责处理特定聊天流的完整交互流程
"""
import time
import traceback
from datetime import datetime
from typing import Dict

from src.chat.planner_actions.action_manager import ActionManager
from src.chat.planner_actions.planner import ActionPlanner
from src.plugin_system.base.component_types import ChatMode

from src.common.logger import get_logger

logger = get_logger("affinity_chatter")


class AffinityFlowChatter:
    """单个亲和力聊天处理器"""

    def __init__(self, stream_id: str, planner: ActionPlanner, action_manager: ActionManager):
        """
        初始化亲和力聊天处理器

        Args:
            stream_id: 聊天流ID
            planner: 动作规划器
            action_manager: 动作管理器
        """
        self.stream_id = stream_id
        self.planner = planner
        self.action_manager = action_manager

        # 处理器统计
        self.stats = {
            "messages_processed": 0,
            "plans_created": 0,
            "actions_executed": 0,
            "successful_executions": 0,
            "failed_executions": 0,
        }
        self.last_activity_time = time.time()

    async def process_message(self, message_data: dict) -> Dict[str, any]:
        """
        处理单个消息

        Args:
            message_data: 消息数据字典

        Returns:
            处理结果字典
        """
        try:
            # 使用增强版规划器处理消息
            actions, target_message = await self.planner.plan(mode=ChatMode.FOCUS)
            self.stats["plans_created"] += 1

            # 执行动作（如果规划器返回了动作）
            execution_result = {"executed_count": len(actions) if actions else 0}
            if actions:
                # 这里可以添加额外的动作执行逻辑
                logger.debug(f"聊天流 {self.stream_id} 生成了 {len(actions)} 个动作")

            # 更新统计
            self.stats["messages_processed"] += 1
            self.stats["actions_executed"] += execution_result.get("executed_count", 0)
            self.stats["successful_executions"] += 1  # TODO:假设成功
            self.last_activity_time = time.time()

            result = {
                "success": True,
                "stream_id": self.stream_id,
                "plan_created": True,
                "actions_count": len(actions) if actions else 0,
                "has_target_message": target_message is not None,
                **execution_result,
            }

            logger.info(f"聊天流 {self.stream_id} 消息处理成功: 动作数={result['actions_count']}")

            return result

        except Exception as e:
            logger.error(f"亲和力聊天处理器 {self.stream_id} 处理消息时出错: {e}\n{traceback.format_exc()}")
            self.stats["failed_executions"] += 1
            self.last_activity_time = time.time()

            return {
                "success": False,
                "stream_id": self.stream_id,
                "error_message": str(e),
                "executed_count": 0,
            }

    def get_stats(self) -> Dict[str, any]:
        """
        获取处理器统计信息

        Returns:
            统计信息字典
        """
        return self.stats.copy()

    def get_planner_stats(self) -> Dict[str, any]:
        """
        获取规划器统计信息

        Returns:
            规划器统计信息字典
        """
        return self.planner.get_planner_stats()

    def get_interest_scoring_stats(self) -> Dict[str, any]:
        """
        获取兴趣度评分统计信息

        Returns:
            兴趣度评分统计信息字典
        """
        return self.planner.get_interest_scoring_stats()

    def get_relationship_stats(self) -> Dict[str, any]:
        """
        获取用户关系统计信息

        Returns:
            用户关系统计信息字典
        """
        return self.planner.get_relationship_stats()

    def get_user_relationship(self, user_id: str) -> float:
        """
        获取用户关系分

        Args:
            user_id: 用户ID

        Returns:
            用户关系分 (0.0-1.0)
        """
        return self.planner.get_user_relationship(user_id)

    def update_interest_keywords(self, new_keywords: dict):
        """
        更新兴趣关键词

        Args:
            new_keywords: 新的兴趣关键词字典
        """
        self.planner.update_interest_keywords(new_keywords)
        logger.info(f"聊天流 {self.stream_id} 已更新兴趣关键词: {list(new_keywords.keys())}")

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "messages_processed": 0,
            "plans_created": 0,
            "actions_executed": 0,
            "successful_executions": 0,
            "failed_executions": 0,
        }

    def is_active(self, max_inactive_minutes: int = 60) -> bool:
        """
        检查处理器是否活跃

        Args:
            max_inactive_minutes: 最大不活跃分钟数

        Returns:
            是否活跃
        """
        current_time = time.time()
        max_inactive_seconds = max_inactive_minutes * 60
        return (current_time - self.last_activity_time) < max_inactive_seconds

    def get_activity_time(self) -> float:
        """
        获取最后活动时间

        Returns:
            最后活动时间戳
        """
        return self.last_activity_time

    def __str__(self) -> str:
        """字符串表示"""
        return f"AffinityFlowChatter(stream_id={self.stream_id}, messages={self.stats['messages_processed']})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"AffinityFlowChatter(stream_id={self.stream_id}, "
                f"messages_processed={self.stats['messages_processed']}, "
                f"plans_created={self.stats['plans_created']}, "
                f"last_activity={datetime.fromtimestamp(self.last_activity_time)})")