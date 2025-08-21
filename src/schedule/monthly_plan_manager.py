# mmc/src/schedule/monthly_plan_manager.py
# 我要混提交
import datetime
from src.config.config import global_config
from src.common.database.monthly_plan_db import get_active_plans_for_month, add_new_plans
from src.schedule.plan_generator import PlanGenerator
from src.common.logger import get_logger

logger = get_logger("monthly_plan_manager")

class MonthlyPlanManager:
    """
    管理月度计划的生成和填充。
    """

    @staticmethod
    async def initialize_monthly_plans():
        """
        程序启动时调用，检查并按需填充当月的计划池。
        """
        config = global_config.monthly_plan_system
        if not config or not config.enable:
            logger.info("月层计划系统未启用，跳过初始化。")
            return

        now = datetime.datetime.now()
        current_month_str = now.strftime("%Y-%m")
        
        try:
            # 1. 检查当月已有计划数量
            existing_plans = get_active_plans_for_month(current_month_str)
            plan_count = len(existing_plans)
            
            header = "📅 月度计划检查"
            
            # 2. 判断是否需要生成新计划
            if plan_count >= config.generation_threshold:
                summary = f"计划数量充足 ({plan_count}/{config.generation_threshold})，无需生成。"
                log_message = (
                    f"\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    f"┃ {header}\n"
                    f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                    f"┃ 月份: {current_month_str}\n"
                    f"┃ 状态: {summary}\n"
                    f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
                )
                logger.info(log_message)
                return

            # 3. 计算需要生成的计划数量并调用生成器
            needed_plans = config.generation_threshold - plan_count
            summary = f"计划不足 ({plan_count}/{config.generation_threshold})，需要生成 {needed_plans} 条。"
            generation_info = f"即将生成 {config.plans_per_generation} 条新计划..."
            log_message = (
                f"\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃ {header}\n"
                f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                f"┃ 月份: {current_month_str}\n"
                f"┃ 状态: {summary}\n"
                f"┃ 操作: {generation_info}\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
            )
            logger.info(log_message)
            
            generator = PlanGenerator()
            new_plans = await generator.generate_plans(
                year=now.year,
                month=now.month,
                count=config.plans_per_generation # 每次生成固定数量以保证质量
            )

            # 4. 将新计划存入数据库
            if new_plans:
                add_new_plans(new_plans, current_month_str)
                completion_header = "✅ 月度计划生成完毕"
                completion_summary = f"成功添加 {len(new_plans)} 条新计划。"
                
                # 构建计划详情
                plan_details = "\n".join([f"┃  - {plan}" for plan in new_plans])
                
                log_message = (
                    f"\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    f"┃ {completion_header}\n"
                    f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                    f"┃ 月份: {current_month_str}\n"
                    f"┃ 结果: {completion_summary}\n"
                    f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                    f"{plan_details}\n"
                    f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
                )
                logger.info(log_message)
            else:
                completion_header = "❌ 月度计划生成失败"
                completion_summary = "未能生成任何新的月度计划。"
                log_message = (
                    f"\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    f"┃ {completion_header}\n"
                    f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                    f"┃ 月份: {current_month_str}\n"
                    f"┃ 结果: {completion_summary}\n"
                    f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
                )
                logger.warning(log_message)

        except Exception as e:
            logger.error(f"初始化月度计划时发生严重错误: {e}", exc_info=True)