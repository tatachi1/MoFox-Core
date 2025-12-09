"""
用户关键信息记录工具

用于记录用户的长期重要信息，如生日、职业、理想、宠物等。
这些信息会存储在 user_relationships 表的 key_facts 字段中。
"""

import time
from typing import Any

import orjson
from sqlalchemy import select

from src.common.database.compatibility import get_db_session
from src.common.database.core.models import UserRelationships
from src.common.logger import get_logger
from src.plugin_system import BaseTool, ToolParamType

logger = get_logger("user_fact_tool")


class UserFactTool(BaseTool):
    """用户关键信息记录工具

    用于记录生日、职业、理想、宠物等长期重要信息。
    注意：一般情况下使用 update_user_profile 工具即可同时记录印象和关键信息。
    此工具仅在需要单独补充记录信息时使用。
    """

    name = "remember_user_info"
    description = """【备用工具】单独记录用户的重要个人信息。
注意：大多数情况请直接使用 update_user_profile 工具（它可以同时更新印象和记录关键信息）。
仅当你只想补充记录一条信息、不需要更新印象时才使用此工具。"""

    parameters = [
        ("target_user_id", ToolParamType.STRING, "目标用户的ID（必须）", True, None),
        ("target_user_name", ToolParamType.STRING, "目标用户的名字/昵称（必须）", True, None),
        ("info_type", ToolParamType.STRING, "信息类型：birthday（生日）/job（职业）/location（所在地）/dream（理想）/family（家庭）/pet（宠物）/other（其他）", True, None),
        ("info_value", ToolParamType.STRING, "具体内容，如'11月23日'、'程序员'、'想开咖啡店'", True, None),
    ]
    available_for_llm = True
    history_ttl = 5

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行关键信息记录

        Args:
            function_args: 工具参数

        Returns:
            dict: 执行结果
        """
        try:
            # 提取参数
            target_user_id = function_args.get("target_user_id")
            target_user_name = function_args.get("target_user_name", target_user_id)
            info_type = function_args.get("info_type", "other")
            info_value = function_args.get("info_value", "")

            if not target_user_id:
                return {
                    "type": "error",
                    "id": "remember_user_info",
                    "content": "错误：必须提供目标用户ID"
                }

            if not info_value:
                return {
                    "type": "error",
                    "id": "remember_user_info",
                    "content": "错误：必须提供要记录的信息内容"
                }

            # 验证 info_type
            valid_types = ["birthday", "job", "location", "dream", "family", "pet", "other"]
            if info_type not in valid_types:
                info_type = "other"

            # 更新数据库
            await self._add_key_fact(target_user_id, info_type, info_value)

            # 生成友好的类型名称
            type_names = {
                "birthday": "生日",
                "job": "职业",
                "location": "所在地",
                "dream": "理想",
                "family": "家庭",
                "pet": "宠物",
                "other": "其他信息"
            }
            type_name = type_names.get(info_type, "信息")

            result_text = f"已记住 {target_user_name} 的{type_name}：{info_value}"
            logger.info(f"记录用户关键信息: {target_user_id}, {info_type}={info_value}")

            return {
                "type": "user_fact_recorded",
                "id": target_user_id,
                "content": result_text
            }

        except Exception as e:
            logger.error(f"记录用户关键信息失败: {e}")
            return {
                "type": "error",
                "id": function_args.get("target_user_id", "unknown"),
                "content": f"记录失败: {e!s}"
            }

    async def _add_key_fact(self, user_id: str, info_type: str, info_value: str):
        """添加或更新关键信息

        Args:
            user_id: 用户ID
            info_type: 信息类型
            info_value: 信息内容
        """
        try:
            current_time = time.time()

            async with get_db_session() as session:
                stmt = select(UserRelationships).where(UserRelationships.user_id == user_id)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    # 解析现有的 key_facts
                    try:
                        facts = orjson.loads(existing.key_facts) if existing.key_facts else []
                    except Exception:
                        facts = []

                    if not isinstance(facts, list):
                        facts = []

                    # 查找是否已有相同类型的信息
                    found = False
                    for i, fact in enumerate(facts):
                        if isinstance(fact, dict) and fact.get("type") == info_type:
                            # 更新现有记录
                            facts[i] = {"type": info_type, "value": info_value}
                            found = True
                            break

                    if not found:
                        # 添加新记录
                        facts.append({"type": info_type, "value": info_value})

                    # 更新数据库
                    existing.key_facts = orjson.dumps(facts).decode("utf-8")
                    existing.last_updated = current_time
                else:
                    # 创建新用户记录
                    facts = [{"type": info_type, "value": info_value}]
                    new_profile = UserRelationships(
                        user_id=user_id,
                        user_name=user_id,
                        key_facts=orjson.dumps(facts).decode("utf-8"),
                        first_met_time=current_time,
                        last_updated=current_time
                    )
                    session.add(new_profile)

                await session.commit()
                logger.info(f"关键信息已保存: {user_id}, {info_type}={info_value}")

        except Exception as e:
            logger.error(f"保存关键信息失败: {e}")
            raise
