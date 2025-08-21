# mmc/src/common/database/monthly_plan_db.py

import datetime
from typing import List
from src.common.database.sqlalchemy_models import MonthlyPlan, get_db_session
from src.common.logger import get_logger

logger = get_logger("monthly_plan_db")

def add_new_plans(plans: List[str], month: str):
    """
    批量添加新生成的月度计划到数据库。

    :param plans: 计划内容列表。
    :param month: 目标月份，格式为 "YYYY-MM"。
    """
    with get_db_session() as session:
        try:
            new_plan_objects = [
                MonthlyPlan(plan_text=plan, target_month=month)
                for plan in plans
            ]
            session.add_all(new_plan_objects)
            session.commit()
            logger.info(f"成功向数据库添加了 {len(new_plan_objects)} 条 {month} 的月度计划。")
        except Exception as e:
            logger.error(f"添加月度计划时发生错误: {e}")
            session.rollback()
            raise

def get_active_plans_for_month(month: str) -> List[MonthlyPlan]:
    """
    获取指定月份所有未被软删除的计划。

    :param month: 目标月份，格式为 "YYYY-MM"。
    :return: MonthlyPlan 对象列表。
    """
    with get_db_session() as session:
        try:
            plans = session.query(MonthlyPlan).filter(
                MonthlyPlan.target_month == month,
                MonthlyPlan.is_deleted == False
            ).all()
            return plans
        except Exception as e:
            logger.error(f"查询 {month} 的有效月度计划时发生错误: {e}")
            return []

def soft_delete_plans(plan_ids: List[int]):
    """
    将指定ID的计划标记为软删除。

    :param plan_ids: 需要软删除的计划ID列表。
    """
    if not plan_ids:
        return

    with get_db_session() as session:
        try:
            session.query(MonthlyPlan).filter(
                MonthlyPlan.id.in_(plan_ids)
            ).update({"is_deleted": True}, synchronize_session=False)
            session.commit()
            logger.info(f"成功软删除了 {len(plan_ids)} 条月度计划。")
        except Exception as e:
            logger.error(f"软删除月度计划时发生错误: {e}")
            session.rollback()
            raise