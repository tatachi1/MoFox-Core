"""
兴趣度评分系统
基于多维度评分机制，包括兴趣匹配度、用户关系分、提及度和时间因子
"""
from datetime import datetime
from typing import Dict, List

from src.common.data_models.database_data_model import DatabaseMessages
from src.common.data_models.info_data_model import InterestScore
from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("interest_scoring")


class InterestScoringSystem:
    """兴趣度评分系统"""

    def __init__(self):
        self.interest_keywords = {
            "游戏": ["游戏", "原神", "米哈游", "抽卡", "角色", "装备", "任务", "副本", "PVP", "LOL", "王者荣耀", "吃鸡"],
            "动漫": ["动漫", "二次元", "新番", "番剧", "漫画", "角色", "声优", "OP", "ED"],
            "音乐": ["音乐", "歌曲", "歌手", "专辑", "演唱会", "乐器", "作词", "作曲"],
            "电影": ["电影", "电视剧", "综艺", "演员", "导演", "剧情", "影评", "票房"],
            "科技": ["科技", "AI", "人工智能", "编程", "Python", "代码", "软件", "硬件", "手机"],
            "生活": ["生活", "日常", "美食", "旅行", "天气", "工作", "学习", "健身"],
            "情感": ["情感", "心情", "感情", "恋爱", "友情", "家人", "开心", "难过", "生气"],
        }

        # 评分权重
        self.score_weights = {
            "interest_match": 0.4,    # 兴趣匹配度权重
            "relationship": 0.3,      # 关系分权重
            "mentioned": 0.2,         # 是否提及bot权重
            "time_factor": 0.1,       # 时间因子权重
        }

        # 评分阈值
        self.reply_threshold = 0.6    # 默认回复阈值
        self.mention_threshold = 0.3   # 提及阈值

        # 连续不回复概率提升
        self.no_reply_count = 0
        self.max_no_reply_count = 5
        self.probability_boost_per_no_reply = 0.15  # 每次不回复增加15%概率

        # 用户关系数据
        self.user_relationships: Dict[str, float] = {}  # user_id -> relationship_score

    def calculate_interest_scores(self, messages: List[DatabaseMessages], bot_nickname: str) -> List[InterestScore]:
        """计算消息的兴趣度评分"""
        scores = []
        # 通过 user_id 判断是否是用户消息（非机器人发送的消息）
        user_messages = [msg for msg in messages if str(msg.user_info.user_id) != str(global_config.bot.qq_account)]

        for msg in user_messages:
            score = self._calculate_single_message_score(msg, bot_nickname)
            scores.append(score)

        return scores

    def _calculate_single_message_score(self, message: DatabaseMessages, bot_nickname: str) -> InterestScore:
        """计算单条消息的兴趣度评分"""
        # 1. 计算兴趣匹配度
        interest_match_score = self._calculate_interest_match_score(message.processed_plain_text)

        # 2. 计算关系分
        relationship_score = self._calculate_relationship_score(message.user_info.user_id)

        # 3. 计算提及分数
        mentioned_score = self._calculate_mentioned_score(message.processed_plain_text, bot_nickname)

        # 4. 计算时间因子
        time_factor_score = self._calculate_time_factor_score(message.time)

        # 5. 计算总分
        total_score = (
            interest_match_score * self.score_weights["interest_match"] +
            relationship_score * self.score_weights["relationship"] +
            mentioned_score * self.score_weights["mentioned"] +
            time_factor_score * self.score_weights["time_factor"]
        )

        details = {
            "interest_match": f"兴趣匹配度: {interest_match_score:.2f}",
            "relationship": f"关系分: {relationship_score:.2f}",
            "mentioned": f"提及分数: {mentioned_score:.2f}",
            "time_factor": f"时间因子: {time_factor_score:.2f}",
        }

        return InterestScore(
            message_id=message.message_id,
            total_score=total_score,
            interest_match_score=interest_match_score,
            relationship_score=relationship_score,
            mentioned_score=mentioned_score,
            time_factor_score=time_factor_score,
            details=details
        )

    def _calculate_interest_match_score(self, content: str) -> float:
        """计算兴趣匹配度"""
        if not content:
            return 0.0

        content_lower = content.lower()
        max_score = 0.0

        for _category, keywords in self.interest_keywords.items():
            category_score = 0.0
            matched_keywords = []

            for keyword in keywords:
                if keyword.lower() in content_lower:
                    category_score += 0.1
                    matched_keywords.append(keyword)

            # 如果匹配到多个关键词，增加额外分数
            if len(matched_keywords) > 1:
                category_score += (len(matched_keywords) - 1) * 0.05

            # 限制每个类别的最高分
            category_score = min(category_score, 0.8)
            max_score = max(max_score, category_score)

        return min(max_score, 1.0)

    def _calculate_relationship_score(self, user_id: str) -> float:
        """计算关系分"""
        if user_id in self.user_relationships:
            relationship_value = self.user_relationships[user_id]
            return min(relationship_value, 1.0)
        return 0.3  # 默认新用户的基础分

    def _calculate_mentioned_score(self, content: str, bot_nickname: str) -> float:
        """计算提及分数"""
        if not content:
            return 0.0

        content_lower = content.lower()
        bot_name_lower = bot_nickname.lower()

        if bot_name_lower in content_lower:
            return 1.0

        # 检查是否被@提及
        if "@" in content and any(alias.lower() in content_lower for alias in global_config.bot.alias_names or []):
            return 1.0

        return 0.0

    def _calculate_time_factor_score(self, timestamp: float) -> float:
        """计算时间因子分数"""
        message_time = datetime.fromtimestamp(timestamp)
        current_time = datetime.now()
        time_diff_hours = (current_time - message_time).total_seconds() / 3600

        # 24小时内消息时间因子为1.0，之后逐渐衰减
        if time_diff_hours <= 24:
            return 1.0
        elif time_diff_hours <= 72:  # 3天内
            return 0.8
        elif time_diff_hours <= 168:  # 7天内
            return 0.6
        else:
            return 0.3

    def should_reply(self, score: InterestScore) -> bool:
        """判断是否应该回复"""
        base_threshold = self.reply_threshold

        # 如果被提及，降低阈值
        if score.mentioned_score >= 1.0:
            base_threshold = self.mention_threshold

        # 计算连续不回复的概率提升
        probability_boost = min(self.no_reply_count * self.probability_boost_per_no_reply, 0.8)
        effective_threshold = base_threshold - probability_boost

        logger.debug(f"评分决策: 总分={score.total_score:.2f}, 有效阈值={effective_threshold:.2f}, 连续不回复次数={self.no_reply_count}")

        return score.total_score >= effective_threshold

    def record_reply_action(self, did_reply: bool):
        """记录回复动作"""
        if did_reply:
            self.no_reply_count = max(0, self.no_reply_count - 1)
        else:
            self.no_reply_count += 1

        # 限制最大计数
        self.no_reply_count = min(self.no_reply_count, self.max_no_reply_count)

        logger.debug(f"回复动作记录: {did_reply}, 当前连续不回复次数: {self.no_reply_count}")

    def update_user_relationship(self, user_id: str, relationship_change: float):
        """更新用户关系"""
        if user_id in self.user_relationships:
            self.user_relationships[user_id] = max(0.0, min(1.0, self.user_relationships[user_id] + relationship_change))
        else:
            self.user_relationships[user_id] = max(0.0, min(1.0, relationship_change))

        logger.debug(f"更新用户关系: {user_id} -> {self.user_relationships[user_id]:.2f}")

    def get_user_relationship(self, user_id: str) -> float:
        """获取用户关系分"""
        return self.user_relationships.get(user_id, 0.3)

    def get_scoring_stats(self) -> Dict:
        """获取评分系统统计"""
        return {
            "no_reply_count": self.no_reply_count,
            "max_no_reply_count": self.max_no_reply_count,
            "reply_threshold": self.reply_threshold,
            "mention_threshold": self.mention_threshold,
            "user_relationships": len(self.user_relationships),
            "interest_categories": len(self.interest_keywords),
        }

    def add_interest_category(self, category: str, keywords: List[str]):
        """添加新的兴趣类别"""
        self.interest_keywords[category] = keywords
        logger.info(f"添加新的兴趣类别: {category}, 关键词数量: {len(keywords)}")

    def remove_interest_category(self, category: str):
        """移除兴趣类别"""
        if category in self.interest_keywords:
            del self.interest_keywords[category]
            logger.info(f"移除兴趣类别: {category}")

    def update_interest_keywords(self, category: str, keywords: List[str]):
        """更新兴趣类别的关键词"""
        if category in self.interest_keywords:
            self.interest_keywords[category] = keywords
            logger.info(f"更新兴趣类别 {category} 的关键词: {len(keywords)}")
        else:
            self.add_interest_category(category, keywords)

    def get_interest_keywords(self) -> Dict[str, List[str]]:
        """获取所有兴趣关键词"""
        return self.interest_keywords.copy()

    def reset_stats(self):
        """重置统计信息"""
        self.no_reply_count = 0
        logger.info("重置兴趣度评分系统统计")