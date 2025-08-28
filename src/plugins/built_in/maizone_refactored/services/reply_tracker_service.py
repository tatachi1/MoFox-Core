# -*- coding: utf-8 -*-
"""
评论回复跟踪服务
负责记录和管理已回复过的评论ID，避免重复回复
"""

import json
import time
from pathlib import Path
from typing import Set, Dict, Any
from src.common.logger import get_logger

logger = get_logger("MaiZone.ReplyTrackerService")


class ReplyTrackerService:
    """
    评论回复跟踪服务
    使用本地JSON文件持久化存储已回复的评论ID
    """
    
    def __init__(self):
        # 数据存储路径
        self.data_dir = Path(__file__).resolve().parent.parent / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.reply_record_file = self.data_dir / "replied_comments.json"
        
        # 内存中的已回复评论记录
        # 格式: {feed_id: {comment_id: timestamp, ...}, ...}
        self.replied_comments: Dict[str, Dict[str, float]] = {}
        
        # 数据清理配置
        self.max_record_days = 30  # 保留30天的记录
        
        # 加载已有数据
        self._load_data()
    
    def _load_data(self):
        """从文件加载已回复评论数据"""
        try:
            if self.reply_record_file.exists():
                with open(self.reply_record_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.replied_comments = data
                logger.info(f"已加载 {len(self.replied_comments)} 条说说的回复记录")
            else:
                logger.info("未找到回复记录文件，将创建新的记录")
        except Exception as e:
            logger.error(f"加载回复记录失败: {e}")
            self.replied_comments = {}
    
    def _save_data(self):
        """保存已回复评论数据到文件"""
        try:
            # 清理过期数据
            self._cleanup_old_records()
            
            with open(self.reply_record_file, 'w', encoding='utf-8') as f:
                json.dump(self.replied_comments, f, ensure_ascii=False, indent=2)
            logger.debug("回复记录已保存")
        except Exception as e:
            logger.error(f"保存回复记录失败: {e}")
    
    def _cleanup_old_records(self):
        """清理超过保留期限的记录"""
        current_time = time.time()
        cutoff_time = current_time - (self.max_record_days * 24 * 60 * 60)
        
        feeds_to_remove = []
        total_removed = 0
        
        for feed_id, comments in self.replied_comments.items():
            comments_to_remove = []
            
            for comment_id, timestamp in comments.items():
                if timestamp < cutoff_time:
                    comments_to_remove.append(comment_id)
            
            # 移除过期的评论记录
            for comment_id in comments_to_remove:
                del comments[comment_id]
                total_removed += 1
            
            # 如果该说说下没有任何记录了，标记删除整个说说记录
            if not comments:
                feeds_to_remove.append(feed_id)
        
        # 移除空的说说记录
        for feed_id in feeds_to_remove:
            del self.replied_comments[feed_id]
        
        if total_removed > 0:
            logger.info(f"清理了 {total_removed} 条过期的回复记录")
    
    def has_replied(self, feed_id: str, comment_id: str) -> bool:
        """
        检查是否已经回复过指定的评论
        
        Args:
            feed_id: 说说ID
            comment_id: 评论ID
            
        Returns:
            bool: 如果已回复过返回True，否则返回False
        """
        if not feed_id or not comment_id:
            return False
            
        return (feed_id in self.replied_comments and 
                comment_id in self.replied_comments[feed_id])
    
    def mark_as_replied(self, feed_id: str, comment_id: str):
        """
        标记指定评论为已回复
        
        Args:
            feed_id: 说说ID
            comment_id: 评论ID
        """
        if not feed_id or not comment_id:
            logger.warning("feed_id 或 comment_id 为空，无法标记为已回复")
            return
        
        current_time = time.time()
        
        if feed_id not in self.replied_comments:
            self.replied_comments[feed_id] = {}
        
        self.replied_comments[feed_id][comment_id] = current_time
        
        # 保存到文件
        self._save_data()
        
        logger.info(f"已标记评论为已回复: feed_id={feed_id}, comment_id={comment_id}")
    
    def get_replied_comments(self, feed_id: str) -> Set[str]:
        """
        获取指定说说下所有已回复的评论ID
        
        Args:
            feed_id: 说说ID
            
        Returns:
            Set[str]: 已回复的评论ID集合
        """
        if feed_id in self.replied_comments:
            return set(self.replied_comments[feed_id].keys())
        return set()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取回复记录统计信息
        
        Returns:
            Dict: 包含统计信息的字典
        """
        total_feeds = len(self.replied_comments)
        total_replies = sum(len(comments) for comments in self.replied_comments.values())
        
        return {
            "total_feeds_with_replies": total_feeds,
            "total_replied_comments": total_replies,
            "data_file": str(self.reply_record_file),
            "max_record_days": self.max_record_days
        }
    
    def remove_reply_record(self, feed_id: str, comment_id: str):
        """
        移除指定评论的回复记录
        
        Args:
            feed_id: 说说ID
            comment_id: 评论ID
        """
        if feed_id in self.replied_comments and comment_id in self.replied_comments[feed_id]:
            del self.replied_comments[feed_id][comment_id]
            
            # 如果该说说下没有任何回复记录了，删除整个说说记录
            if not self.replied_comments[feed_id]:
                del self.replied_comments[feed_id]
            
            self._save_data()
            logger.debug(f"已移除回复记录: feed_id={feed_id}, comment_id={comment_id}")
    
    def remove_feed_records(self, feed_id: str):
        """
        移除指定说说的所有回复记录
        
        Args:
            feed_id: 说说ID
        """
        if feed_id in self.replied_comments:
            del self.replied_comments[feed_id]
            self._save_data()
            logger.info(f"已移除说说 {feed_id} 的所有回复记录")