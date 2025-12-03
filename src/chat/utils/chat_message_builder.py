import random
import re
import time  # 导入 time 模块以获取当前时间
from collections.abc import Callable
from typing import Any

from rich.traceback import install
from sqlalchemy import and_, select

from src.chat.utils.utils import assign_message_ids, translate_timestamp_to_human_readable
from src.common.database.compatibility import get_db_session
from src.common.database.core.models import ActionRecords, Images
from src.common.logger import get_logger
from src.common.message_repository import count_messages, find_messages
from src.config.config import global_config
from src.person_info.person_info import PersonInfoManager, get_person_info_manager

logger = get_logger("chat_message_builder")

install(extra_lines=3)


def replace_user_references_sync(
    content: str,
    platform: str,
    name_resolver: Callable[[str, str], str] | None = None,
    replace_bot_name: bool = True,
) -> str:
    """
    替换内容中的用户引用格式，包括回复<aaa:bbb>和@<aaa:bbb>格式

    Args:
        content: 要处理的内容字符串
        platform: 平台标识
        name_resolver: 名称解析函数，接收(platform, user_id)参数，返回用户名称
                       如果为None，则使用默认的person_info_manager
        replace_bot_name: 是否将机器人的user_id替换为"机器人昵称(你)"

    Returns:
        str: 处理后的内容字符串
    """
    assert global_config is not None
    if not content:
        return ""

    if name_resolver is None:
        def default_resolver(platform: str, user_id: str) -> str:
            assert global_config is not None
            # 检查是否是机器人自己
            if replace_bot_name and (user_id == str(global_config.bot.qq_account)):
                return f"{global_config.bot.nickname}(你)"
            # 同步函数中无法使用异步的 get_value，直接返回 user_id
            # 建议调用方使用 replace_user_references_async 以获取完整的用户名
            return user_id

        name_resolver = default_resolver

    # 处理回复<aaa:bbb>格式
    reply_pattern = r"回复<([^:<>]+):([^:<>]+)>"
    match = re.search(reply_pattern, content)
    if match:
        aaa = match[1]
        bbb = match[2]
        try:
            # 检查是否是机器人自己（支持SELF标记或直接比对QQ号）
            if replace_bot_name and (bbb == str(global_config.bot.qq_account)):
                reply_person_name = f"{global_config.bot.nickname}(你)"
            else:
                reply_person_name = name_resolver(platform, bbb) or aaa
            content = re.sub(reply_pattern, f"回复 {reply_person_name}", content, count=1)
        except Exception:
            # 如果解析失败，使用原始昵称
            content = re.sub(reply_pattern, f"回复 {aaa}", content, count=1)

    # 处理@<aaa:bbb>格式
    at_pattern = r"@<([^:<>]+):([^:<>]+)>"
    at_matches = list(re.finditer(at_pattern, content))
    if at_matches:
        new_content = ""
        last_end = 0
        for m in at_matches:
            new_content += content[last_end : m.start()]
            aaa = m.group(1)
            bbb = m.group(2)
            try:
                # 检查是否是机器人自己
                if replace_bot_name and (bbb == str(global_config.bot.qq_account)):
                    at_person_name = f"{global_config.bot.nickname}(你)"
                else:
                    at_person_name = name_resolver(platform, bbb) or aaa
                new_content += f"@{at_person_name}"
            except Exception:
                # 如果解析失败，使用原始昵称
                new_content += f"@{aaa}"
            last_end = m.end()
        new_content += content[last_end:]
        content = new_content

    return content


async def replace_user_references_async(
    content: str,
    platform: str,
    name_resolver: Callable[[str, str], Any] | None = None,
    replace_bot_name: bool = True,
) -> str:
    """
    替换内容中的用户引用格式，包括回复<aaa:bbb>和@<aaa:bbb>格式

    Args:
        content: 要处理的内容字符串
        platform: 平台标识
        name_resolver: 名称解析函数，接收(platform, user_id)参数，返回用户名称
                       如果为None，则使用默认的person_info_manager
        replace_bot_name: 是否将机器人的user_id替换为"机器人昵称(你)"

    Returns:
        str: 处理后的内容字符串
    """
    assert global_config is not None
    if name_resolver is None:
        person_info_manager = get_person_info_manager()

        async def default_resolver(platform: str, user_id: str) -> str:
            assert global_config is not None
            # 检查是否是机器人自己
            if replace_bot_name and (user_id == str(global_config.bot.qq_account)):
                return f"{global_config.bot.nickname}(你)"
            person_id = PersonInfoManager.get_person_id(platform, user_id)
            return await person_info_manager.get_value(person_id, "person_name") or user_id  # type: ignore

        name_resolver = default_resolver

    # 处理回复<aaa:bbb>格式
    reply_pattern = r"回复<([^:<>]+):([^:<>]+)>"
    match = re.search(reply_pattern, content)
    if match:
        aaa = match.group(1)
        bbb = match.group(2)
        try:
            # 检查是否是机器人自己
            if replace_bot_name and (bbb == str(global_config.bot.qq_account)):
                reply_person_name = f"{global_config.bot.nickname}(你)"
            else:
                reply_person_name = await name_resolver(platform, bbb) or aaa
            content = re.sub(reply_pattern, f"回复 {reply_person_name}", content, count=1)
        except Exception:
            # 如果解析失败，使用原始昵称
            content = re.sub(reply_pattern, f"回复 {aaa}", content, count=1)

    # 处理@<aaa:bbb>格式
    at_pattern = r"@<([^:<>]+):([^:<>]+)>"
    at_matches = list(re.finditer(at_pattern, content))
    if at_matches:
        new_content = ""
        last_end = 0
        for m in at_matches:
            new_content += content[last_end : m.start()]
            aaa = m.group(1)
            bbb = m.group(2)
            try:
                # 检查是否是机器人自己
                if replace_bot_name and (bbb == str(global_config.bot.qq_account)):
                    at_person_name = f"{global_config.bot.nickname}(你)"
                else:
                    at_person_name = await name_resolver(platform, bbb) or aaa
                new_content += f"@{at_person_name}"
            except Exception:
                # 如果解析失败，使用原始昵称
                new_content += f"@{aaa}"
            last_end = m.end()
        new_content += content[last_end:]
        content = new_content

    return content


async def get_raw_msg_by_timestamp(
    timestamp_start: float, timestamp_end: float, limit: int = 0, limit_mode: str = "latest"
) -> list[dict[str, Any]]:
    """
    获取从指定时间戳到指定时间戳的消息，按时间升序排序，返回消息列表
    limit: 限制返回的消息数量，0为不限制
    limit_mode: 当 limit > 0 时生效。 'earliest' 表示获取最早的记录， 'latest' 表示获取最新的记录。默认为 'latest'。
    """
    filter_query = {"time": {"$gt": timestamp_start, "$lt": timestamp_end}}
    # 只有当 limit 为 0 时才应用外部 sort
    sort_order = [("time", 1)] if limit == 0 else None
    return await find_messages(message_filter=filter_query, sort=sort_order, limit=limit, limit_mode=limit_mode)


async def get_raw_msg_by_timestamp_with_chat(
    chat_id: str,
    timestamp_start: float,
    timestamp_end: float,
    limit: int = 0,
    limit_mode: str = "latest",
    filter_bot=False,
    filter_command=False,
) -> list[dict[str, Any]]:
    """获取在特定聊天从指定时间戳到指定时间戳的消息，按时间升序排序，返回消息列表
    limit: 限制返回的消息数量，0为不限制
    limit_mode: 当 limit > 0 时生效。 'earliest' 表示获取最早的记录， 'latest' 表示获取最新的记录。默认为 'latest'。
    """
    filter_query = {"chat_id": chat_id, "time": {"$gt": timestamp_start, "$lt": timestamp_end}}
    # 只有当 limit 为 0 时才应用外部 sort
    sort_order = [("time", 1)] if limit == 0 else None
    # 直接将 limit_mode 传递给 find_messages
    return await find_messages(
        message_filter=filter_query,
        sort=sort_order,
        limit=limit,
        limit_mode=limit_mode,
        filter_bot=filter_bot,
        filter_command=filter_command,
    )


async def get_raw_msg_by_timestamp_with_chat_inclusive(
    chat_id: str,
    timestamp_start: float,
    timestamp_end: float,
    limit: int = 0,
    limit_mode: str = "latest",
    filter_bot=False,
    filter_meaningless=False,
) -> list[dict[str, Any]]:
    """获取在特定聊天从指定时间戳到指定时间戳的消息（包含边界），按时间升序排序，返回消息列表
    limit: 限制返回的消息数量，0为不限制
    limit_mode: 当 limit > 0 时生效。 'earliest' 表示获取最早的记录， 'latest' 表示获取最新的记录。默认为 'latest'。
    filter_meaningless: 是否过滤无意义消息（表情包、通知等）。用于表达学习等场景。
    """
    filter_query = {"chat_id": chat_id, "time": {"$gte": timestamp_start, "$lte": timestamp_end}}
    # 只有当 limit 为 0 时才应用外部 sort
    sort_order = [("time", 1)] if limit == 0 else None
    # 直接将 limit_mode 传递给 find_messages

    return await find_messages(
        message_filter=filter_query,
        sort=sort_order,
        limit=limit,
        limit_mode=limit_mode,
        filter_bot=filter_bot,
        filter_meaningless=filter_meaningless,
    )


async def get_raw_msg_by_timestamp_with_chat_users(
    chat_id: str,
    timestamp_start: float,
    timestamp_end: float,
    person_ids: list[str],
    limit: int = 0,
    limit_mode: str = "latest",
) -> list[dict[str, Any]]:
    """获取某些特定用户在特定聊天从指定时间戳到指定时间戳的消息，按时间升序排序，返回消息列表
    limit: 限制返回的消息数量，0为不限制
    limit_mode: 当 limit > 0 时生效。 'earliest' 表示获取最早的记录， 'latest' 表示获取最新的记录。默认为 'latest'。
    """
    filter_query = {
        "chat_id": chat_id,
        "time": {"$gt": timestamp_start, "$lt": timestamp_end},
        "user_id": {"$in": person_ids},
    }
    # 只有当 limit 为 0 时才应用外部 sort
    sort_order = [("time", 1)] if limit == 0 else None
    return await find_messages(message_filter=filter_query, sort=sort_order, limit=limit, limit_mode=limit_mode)


async def get_actions_by_timestamp_with_chat(
    chat_id: str,
    timestamp_start: float = 0,
    timestamp_end: float = time.time(),
    limit: int = 0,
    limit_mode: str = "latest",
) -> list[dict[str, Any]]:
    """获取在特定聊天从指定时间戳到指定时间戳的动作记录，按时间升序排序，返回动作记录列表"""
    from src.common.logger import get_logger

    logger = get_logger("chat_message_builder")

    # 记录函数调用参数
    logger.debug(
        f"[get_actions_by_timestamp_with_chat] 调用参数: chat_id={chat_id}, "
        f"timestamp_start={timestamp_start}, timestamp_end={timestamp_end}, "
        f"limit={limit}, limit_mode={limit_mode}"
    )

    async with get_db_session() as session:
        if limit > 0:
            result = await session.execute(
                select(ActionRecords)
                .where(
                    and_(
                        ActionRecords.chat_id == chat_id,
                        ActionRecords.time >= timestamp_start,
                        ActionRecords.time <= timestamp_end,
                    )
                )
                .order_by(ActionRecords.time.desc())
                .limit(limit)
            )
            actions = list(result.scalars())
            actions_result = []
            for action in reversed(actions):
                action_dict = {
                    "id": action.id,
                    "action_id": action.action_id,
                    "time": action.time,
                    "action_name": action.action_name,
                    "action_data": action.action_data,
                    "action_done": action.action_done,
                    "action_build_into_prompt": action.action_build_into_prompt,
                    "action_prompt_display": action.action_prompt_display,
                    "chat_id": action.chat_id,
                    "chat_info_stream_id": action.chat_info_stream_id,
                    "chat_info_platform": action.chat_info_platform,
                }
                actions_result.append(action_dict)
                actions_result.append(action_dict)
            else:  # earliest
                result = await session.execute(
                    select(ActionRecords)
                    .where(
                        and_(
                            ActionRecords.chat_id == chat_id,
                            ActionRecords.time > timestamp_start,
                            ActionRecords.time < timestamp_end,
                        )
                    )
                    .order_by(ActionRecords.time.asc())
                    .limit(limit)
                )
                actions = list(result.scalars())
                actions_result = []
                for action in actions:
                    action_dict = {
                        "id": action.id,
                        "action_id": action.action_id,
                        "time": action.time,
                        "action_name": action.action_name,
                        "action_data": action.action_data,
                        "action_done": action.action_done,
                        "action_build_into_prompt": action.action_build_into_prompt,
                        "action_prompt_display": action.action_prompt_display,
                        "chat_id": action.chat_id,
                        "chat_info_stream_id": action.chat_info_stream_id,
                        "chat_info_platform": action.chat_info_platform,
                    }
                    actions_result.append(action_dict)
        else:
            result = await session.execute(
                select(ActionRecords)
                .where(
                    and_(
                        ActionRecords.chat_id == chat_id,
                        ActionRecords.time > timestamp_start,
                        ActionRecords.time < timestamp_end,
                    )
                )
                .order_by(ActionRecords.time.asc())
            )
            actions = list(result.scalars())
            actions_result = []
            for action in actions:
                action_dict = {
                    "id": action.id,
                    "action_id": action.action_id,
                    "time": action.time,
                    "action_name": action.action_name,
                    "action_data": action.action_data,
                    "action_done": action.action_done,
                    "action_build_into_prompt": action.action_build_into_prompt,
                    "action_prompt_display": action.action_prompt_display,
                    "chat_id": action.chat_id,
                    "chat_info_stream_id": action.chat_info_stream_id,
                    "chat_info_platform": action.chat_info_platform,
                }
                actions_result.append(action_dict)
        return actions_result


async def get_actions_by_timestamp_with_chat_inclusive(
    chat_id: str, timestamp_start: float, timestamp_end: float, limit: int = 0, limit_mode: str = "latest"
) -> list[dict[str, Any]]:
    """获取在特定聊天从指定时间戳到指定时间戳的动作记录（包含边界），按时间升序排序，返回动作记录列表"""
    async with get_db_session() as session:
        if limit > 0:
            if limit_mode == "latest":
                result = await session.execute(
                    select(ActionRecords)
                    .where(
                        and_(
                            ActionRecords.chat_id == chat_id,
                            ActionRecords.time >= timestamp_start,
                            ActionRecords.time <= timestamp_end,
                        )
                    )
                    .order_by(ActionRecords.time.desc())
                    .limit(limit)
                )
                actions = list(result.scalars())
                return [action.__dict__ for action in reversed(actions)]
            else:  # earliest
                query = await session.execute(
                    select(ActionRecords)
                    .where(
                        and_(
                            ActionRecords.chat_id == chat_id,
                            ActionRecords.time >= timestamp_start,
                            ActionRecords.time <= timestamp_end,
                        )
                    )
                    .order_by(ActionRecords.time.asc())
                    .limit(limit)
                )
        else:
            query = await session.execute(
                select(ActionRecords)
                .where(
                    and_(
                        ActionRecords.chat_id == chat_id,
                        ActionRecords.time >= timestamp_start,
                        ActionRecords.time <= timestamp_end,
                    )
                )
                .order_by(ActionRecords.time.asc())
            )

        actions = list(query.scalars())
        return [action.__dict__ for action in actions]


async def get_raw_msg_by_timestamp_random(
    timestamp_start: float, timestamp_end: float, limit: int = 0, limit_mode: str = "latest"
) -> list[dict[str, Any]]:
    """
    先在范围时间戳内随机选择一条消息，取得消息的chat_id，然后根据chat_id获取该聊天在指定时间戳范围内的消息
    """
    # 获取所有消息，只取chat_id字段
    all_msgs = await get_raw_msg_by_timestamp(timestamp_start, timestamp_end)
    if not all_msgs:
        return []
    # 随机选一条
    msg = random.choice(all_msgs)
    chat_id = msg["chat_id"]
    timestamp_start = msg["time"]
    # 用 chat_id 获取该聊天在指定时间戳范围内的消息
    return await get_raw_msg_by_timestamp_with_chat(chat_id, timestamp_start, timestamp_end, limit, "earliest")


async def get_raw_msg_by_timestamp_with_users(
    timestamp_start: float, timestamp_end: float, person_ids: list, limit: int = 0, limit_mode: str = "latest"
) -> list[dict[str, Any]]:
    """获取某些特定用户在 *所有聊天* 中从指定时间戳到指定时间戳的消息，按时间升序排序，返回消息列表
    limit: 限制返回的消息数量，0为不限制
    limit_mode: 当 limit > 0 时生效。 'earliest' 表示获取最早的记录， 'latest' 表示获取最新的记录。默认为 'latest'。
    """
    filter_query = {"time": {"$gt": timestamp_start, "$lt": timestamp_end}, "user_id": {"$in": person_ids}}
    # 只有当 limit 为 0 时才应用外部 sort
    sort_order = [("time", 1)] if limit == 0 else None
    return await find_messages(message_filter=filter_query, sort=sort_order, limit=limit, limit_mode=limit_mode)


async def get_raw_msg_before_timestamp(timestamp: float, limit: int = 0) -> list[dict[str, Any]]:
    """获取指定时间戳之前的消息，按时间升序排序，返回消息列表
    limit: 限制返回的消息数量，0为不限制
    """
    filter_query = {"time": {"$lt": timestamp}}
    sort_order = [("time", 1)]
    return await find_messages(message_filter=filter_query, sort=sort_order, limit=limit)


async def get_raw_msg_before_timestamp_with_chat(
    chat_id: str, timestamp: float, limit: int = 0
) -> list[dict[str, Any]]:
    """获取指定时间戳之前的消息，按时间升序排序，返回消息列表
    limit: 限制返回的消息数量，0为不限制
    """
    filter_query = {"chat_id": chat_id, "time": {"$lt": timestamp}}
    sort_order = [("time", 1)]
    return await find_messages(message_filter=filter_query, sort=sort_order, limit=limit)


async def get_raw_msg_before_timestamp_with_users(
    timestamp: float, person_ids: list, limit: int = 0
) -> list[dict[str, Any]]:
    """获取指定时间戳之前的消息，按时间升序排序，返回消息列表
    limit: 限制返回的消息数量，0为不限制
    """
    filter_query = {"time": {"$lt": timestamp}, "user_id": {"$in": person_ids}}
    sort_order = [("time", 1)]
    return await find_messages(message_filter=filter_query, sort=sort_order, limit=limit)


async def num_new_messages_since(chat_id: str, timestamp_start: float = 0.0, timestamp_end: float | None = None) -> int:
    """
    检查特定聊天从 timestamp_start (不含) 到 timestamp_end (不含) 之间有多少新消息。
    如果 timestamp_end 为 None，则检查从 timestamp_start (不含) 到当前时间的消息。
    """
    # 确定有效的结束时间戳
    _timestamp_end = timestamp_end if timestamp_end is not None else time.time()

    # 确保 timestamp_start < _timestamp_end
    if timestamp_start >= _timestamp_end:
        # logger.warning(f"timestamp_start ({timestamp_start}) must be less than _timestamp_end ({_timestamp_end}). Returning 0.")
        return 0  # 起始时间大于等于结束时间，没有新消息

    filter_query = {"chat_id": chat_id, "time": {"$gt": timestamp_start, "$lt": _timestamp_end}}
    return await count_messages(message_filter=filter_query)


async def num_new_messages_since_with_users(
    chat_id: str, timestamp_start: float, timestamp_end: float, person_ids: list
) -> int:
    """检查某些特定用户在特定聊天在指定时间戳之间有多少新消息"""
    if not person_ids:  # 保持空列表检查
        return 0
    filter_query = {
        "chat_id": chat_id,
        "time": {"$gt": timestamp_start, "$lt": timestamp_end},
        "user_id": {"$in": person_ids},
    }
    return await count_messages(message_filter=filter_query)


async def _build_readable_messages_internal(
    messages: list[dict[str, Any]],
    replace_bot_name: bool = True,
    merge_messages: bool = False,
    timestamp_mode: str = "relative",
    truncate: bool = False,
    pic_id_mapping: dict[str, str] | None = None,
    pic_counter: int = 1,
    show_pic: bool = True,
    message_id_list: list[dict[str, Any]] | None = None,
) -> tuple[str, list[tuple[float, str, str]], dict[str, str], int]:
    """
    内部辅助函数，构建可读消息字符串和原始消息详情列表。

    Args:
        messages: 消息字典列表。
        replace_bot_name: 是否将机器人的 user_id 替换为 "我"。
        merge_messages: 是否合并来自同一用户的连续消息。
        timestamp_mode: 时间戳的显示模式 ('relative', 'absolute', etc.)。传递给 translate_timestamp_to_human_readable。
        truncate: 是否根据消息的新旧程度截断过长的消息内容。
        pic_id_mapping: 图片ID映射字典，如果为None则创建新的
        pic_counter: 图片计数器起始值

    Returns:
        包含格式化消息的字符串、原始消息详情列表、图片映射字典和更新后的计数器的元组。
    """
    assert global_config is not None
    if not messages:
        return "", [], pic_id_mapping or {}, pic_counter

    message_details_raw: list[tuple[float, str, str, bool]] = []

    # 使用传入的映射字典，如果没有则创建新的
    if pic_id_mapping is None:
        pic_id_mapping = {}
    current_pic_counter = pic_counter

    # --- 异步图片ID处理器 (修复核心问题) ---
    async def process_pic_ids(content: str) -> str:
        """异步处理内容中的图片ID，将其直接替换为[图片：描述]格式"""
        pic_pattern = r"\[picid:([^\]]+)\]"
        matches = list(re.finditer(pic_pattern, content))
        if not matches:
            return content

        new_content = ""
        last_end = 0
        for match in matches:
            new_content += content[last_end : match.start()]
            pic_id = match.group(1)
            description = "[图片内容未知]"
            try:
                async with get_db_session() as session:
                    result = await session.execute(select(Images.description).where(Images.image_id == pic_id))
                    desc_scalar = result.scalar_one_or_none()
                    if desc_scalar and desc_scalar.strip():
                        description = f"[图片：{desc_scalar}]"
                    else:
                        description = "[图片内容未知]"
            except Exception as e:
                logger.debug(f"[chat_message_builder] 查询图片 {pic_id} 描述失败: {e}")
                description = "[图片内容未知]"
            new_content += description
            last_end = match.end()
        new_content += content[last_end:]
        return new_content

    # 创建时间戳到消息ID的映射，用于在消息前添加[id]标识符
    timestamp_to_id = {}
    if message_id_list:
        for item in message_id_list:
            message = item.get("message", {})
            timestamp = message.get("time")
            if timestamp is not None:
                timestamp_to_id[timestamp] = item.get("id", "")

    # 1 & 2: 获取发送者信息并提取消息组件
    for msg in messages:
        # 检查是否是动作记录
        if msg.get("is_action_record", False):
            is_action = True
            timestamp: float = msg.get("time")  # type: ignore
            content = msg.get("display_message", "")
            if show_pic:
                content = await process_pic_ids(content)
            message_details_raw.append((timestamp, global_config.bot.nickname, content, is_action))
            continue

        # 检查并修复缺少的user_info字段
        if "user_info" not in msg:
            # 创建user_info字段
            msg["user_info"] = {
                "platform": msg.get("user_platform", ""),
                "user_id": msg.get("user_id", ""),
                "user_nickname": msg.get("user_nickname", ""),
                "user_cardname": msg.get("user_cardname", ""),
            }

        user_info = msg.get("user_info", {})
        platform = user_info.get("platform")
        user_id = user_info.get("user_id")

        user_nickname = user_info.get("user_nickname")
        user_cardname = user_info.get("user_cardname")

        timestamp: float = msg.get("time")  # type: ignore
        content: str
        if msg.get("display_message"):
            content = msg.get("display_message", "")
        else:
            content = msg.get("processed_plain_text", "")  # 默认空字符串

        if "ᶠ" in content:
            content = content.replace("ᶠ", "")
        if "ⁿ" in content:
            content = content.replace("ⁿ", "")

        # 处理图片ID
        if show_pic:
            content = await process_pic_ids(content)

        # 检查必要信息是否存在
        if not all([platform, user_id, timestamp is not None]):
            continue

        # 根据 replace_bot_name 参数决定是否替换机器人名称
        person_name: str
        # 检查是否是机器人自己（支持SELF标记或直接比对QQ号）
        if replace_bot_name and user_id == str(global_config.bot.qq_account):
            person_name = f"{global_config.bot.nickname}(你)"
        else:
            person_id = PersonInfoManager.get_person_id(platform, user_id)
            person_info_manager = get_person_info_manager()
            person_name = await person_info_manager.get_value(person_id, "person_name")  # type: ignore

        # 如果 person_name 未设置，则使用消息中的 nickname 或默认名称
        if not person_name:
            if user_cardname:
                person_name = f"昵称：{user_cardname}"
            elif user_nickname:
                person_name = f"{user_nickname}"
            else:
                person_name = "某人"

        # 在用户名后面添加 QQ 号, 但机器人本体不用
        if user_id != str(global_config.bot.qq_account):
            person_name = f"{person_name}({user_id})"

        # 使用独立函数处理用户引用格式
        content = await replace_user_references_async(content, platform, replace_bot_name=replace_bot_name)

        target_str = "这是QQ的一个功能，用于提及某人，但没那么明显"
        if target_str in content and random.random() < 0.6:
            content = content.replace(target_str, "")

        if content != "":
            message_details_raw.append((timestamp, person_name, content, False))

    if not message_details_raw:
        return "", [], pic_id_mapping, current_pic_counter

    message_details_raw.sort(key=lambda x: x[0])  # 按时间戳(第一个元素)升序排序，越早的消息排在前面

    # 为每条消息添加一个标记，指示它是否是动作记录
    message_details_with_flags = []
    for timestamp, name, content, is_action in message_details_raw:
        message_details_with_flags.append((timestamp, name, content, is_action))

    # 应用截断逻辑 (如果 truncate 为 True)
    message_details: list[tuple[float, str, str, bool]] = []
    n_messages = len(message_details_with_flags)
    if truncate and n_messages > 0:
        for i, (timestamp, name, content, is_action) in enumerate(message_details_with_flags):
            # 对于动作记录，不进行截断
            if is_action:
                message_details.append((timestamp, name, content, is_action))
                continue

            percentile = i / n_messages  # 计算消息在列表中的位置百分比 (0 <= percentile < 1)
            original_len = len(content)
            limit = -1  # 默认不截断
            replace_content = ""

            if percentile < 0.2:  # 60% 之前的消息 (即最旧的 60%)
                limit = 50
                replace_content = "......（记不清了）"
            elif percentile < 0.5:  # 60% 之前的消息 (即最旧的 60%)
                limit = 100
                replace_content = "......（有点记不清了）"
            elif percentile < 0.7:  # 60% 到 80% 之前的消息 (即中间的 20%)
                limit = 200
                replace_content = "......（内容太长了）"
            elif percentile < 1.0:  # 80% 到 100% 之前的消息 (即较新的 20%)
                limit = 400
                replace_content = "......（太长了）"

            truncated_content = content
            if 0 < limit < original_len:
                truncated_content = f"{content[:limit]}{replace_content}"

            message_details.append((timestamp, name, truncated_content, is_action))
    else:
        # 如果不截断，直接使用原始列表
        message_details = message_details_with_flags

    # 3: 合并连续消息 (如果 merge_messages 为 True)
    merged_messages = []
    if merge_messages and message_details:
        # 初始化第一个合并块
        current_merge = {
            "name": message_details[0][1],
            "start_time": message_details[0][0],
            "end_time": message_details[0][0],
            "content": [message_details[0][2]],
            "is_action": message_details[0][3],
        }

        for i in range(1, len(message_details)):
            timestamp, name, content, is_action = message_details[i]

            # 对于动作记录，不进行合并
            if is_action or current_merge["is_action"]:
                # 保存当前的合并块
                merged_messages.append(current_merge)
                # 创建新的块
                current_merge = {
                    "name": name,
                    "start_time": timestamp,
                    "end_time": timestamp,
                    "content": [content],
                    "is_action": is_action,
                }
                continue

            # 如果是同一个人发送的连续消息且时间间隔小于等于60秒
            if name == current_merge["name"] and (timestamp - current_merge["end_time"] <= 60):
                current_merge["content"].append(content)
                current_merge["end_time"] = timestamp  # 更新最后消息时间
            else:
                # 保存上一个合并块
                merged_messages.append(current_merge)
                # 开始新的合并块
                current_merge = {
                    "name": name,
                    "start_time": timestamp,
                    "end_time": timestamp,
                    "content": [content],
                    "is_action": is_action,
                }
        # 添加最后一个合并块
        merged_messages.append(current_merge)
    elif message_details:  # 如果不合并消息，则每个消息都是一个独立的块
        for timestamp, name, content, is_action in message_details:
            merged_messages.append(
                {
                    "name": name,
                    "start_time": timestamp,  # 起始和结束时间相同
                    "end_time": timestamp,
                    "content": [content],  # 内容只有一个元素
                    "is_action": is_action,
                }
            )

    # 4 & 5: 格式化为字符串
    output_lines = []

    for _i, merged in enumerate(merged_messages):
        # 使用指定的 timestamp_mode 格式化时间
        readable_time = translate_timestamp_to_human_readable(merged["start_time"], mode=timestamp_mode)

        # 查找对应的消息ID
        message_id = timestamp_to_id.get(merged["start_time"], "")
        id_prefix = f"[{message_id}] " if message_id else ""

        # 检查是否是动作记录
        if merged["is_action"]:
            # 对于动作记录，使用特殊格式
            output_lines.append(f"{id_prefix}{readable_time}, {merged['content'][0]}")
        else:
            header = f"{id_prefix}{readable_time}, {merged['name']} :"
            output_lines.append(header)
            # 将内容合并，并添加缩进
            for line in merged["content"]:
                stripped_line = line.strip()
                if stripped_line:  # 过滤空行
                    # 移除末尾句号，添加分号 - 这个逻辑似乎有点奇怪，暂时保留
                    if stripped_line.endswith("。"):
                        stripped_line = stripped_line[:-1]
                    # 如果内容被截断，结尾已经是 ...（内容太长），不再添加分号
                    if not stripped_line.endswith("（内容太长）"):
                        output_lines.append(f"{stripped_line}")
                    else:
                        output_lines.append(stripped_line)  # 直接添加截断后的内容
        output_lines.append("\n")  # 在每个消息块后添加换行，保持可读性

    # 移除可能的多余换行，然后合并
    formatted_string = "".join(output_lines).strip()

    # 返回格式化后的字符串、消息详情列表、图片映射字典和更新后的计数器
    return (
        formatted_string,
        [(t, n, c) for t, n, c, is_action in message_details if not is_action],
        pic_id_mapping,
        current_pic_counter,
    )

async def build_pic_mapping_info(pic_id_mapping: dict[str, str]) -> str:
    """
    此函数已废弃，因为图片描述现在被内联处理。
    保留此函数以确保向后兼容性，但它将始终返回一个空字符串。
    """
    return ""


def build_readable_actions(actions: list[dict[str, Any]]) -> str:
    """
    将动作列表转换为可读的文本格式。
    格式: 在（）分钟前，你使用了(action_name)，具体内容是：（action_prompt_display）

    Args:
        actions: 动作记录字典列表。

    Returns:
        格式化的动作字符串。
    """
    from src.common.logger import get_logger

    logger = get_logger("chat_message_builder")

    logger.debug(f"[build_readable_actions] 开始处理 {len(actions) if actions else 0} 条动作记录")

    if not actions:
        logger.debug("[build_readable_actions] 动作记录为空，返回空字符串")
        return ""

    output_lines = []
    current_time = time.time()

    logger.debug(f"[build_readable_actions] 当前时间戳: {current_time}")

    # The get functions return actions sorted ascending by time. Let's reverse it to show newest first.
    # sorted_actions = sorted(actions, key=lambda x: x.get("time", 0), reverse=True)

    for i, action in enumerate(actions):
        logger.debug(f"[build_readable_actions] === 处理第 {i} 条动作记录 ===")
        logger.debug(f"[build_readable_actions] 原始动作数据: {action}")

        action_time = action.get("time", current_time)
        action_name = action.get("action_name", "未知动作")

        logger.debug(f"[build_readable_actions] 动作时间戳: {action_time}, 动作名称: '{action_name}'")

        # 检查是否是原始的 action_name 值
        original_action_name = action.get("action_name")
        if original_action_name is None:
            logger.error(f"[build_readable_actions] 动作 #{i}: action_name 为 None!")
        elif original_action_name == "":
            logger.error(f"[build_readable_actions] 动作 #{i}: action_name 为空字符串!")
        elif original_action_name == "未知动作":
            logger.error(f"[build_readable_actions] 动作 #{i}: action_name 已经是'未知动作'!")

        if action_name in ["no_action", "no_reply"]:
            logger.debug(f"[build_readable_actions] 跳过动作 #{i}: {action_name} (在跳过列表中)")
            continue

        action_prompt_display = action.get("action_prompt_display", "无具体内容")
        logger.debug(f"[build_readable_actions] 动作提示显示: '{action_prompt_display}'")

        time_diff_seconds = current_time - action_time
        logger.debug(f"[build_readable_actions] 时间差: {time_diff_seconds} 秒")

        if time_diff_seconds < 60:
            time_ago_str = f"在{int(time_diff_seconds)}秒前"
        else:
            time_diff_minutes = round(time_diff_seconds / 60)
            time_ago_str = f"在{int(time_diff_minutes)}分钟前"

        logger.debug(f"[build_readable_actions] 时间描述: '{time_ago_str}'")

        line = f'{time_ago_str}，你使用了"{action_name}"，具体内容是："{action_prompt_display}"'
        logger.debug(f"[build_readable_actions] 生成的行: '{line}'")
        output_lines.append(line)

    result = "\n".join(output_lines)
    logger.debug(f"[build_readable_actions] 最终结果: '{result}'")
    return result


async def build_readable_messages_with_list(
    messages: list[dict[str, Any]],
    replace_bot_name: bool = True,
    merge_messages: bool = False,
    timestamp_mode: str = "relative",
    truncate: bool = False,
) -> tuple[str, list[tuple[float, str, str]]]:
    """
    将消息列表转换为可读的文本格式，并返回原始(时间戳, 昵称, 内容)列表。
    允许通过参数控制格式化行为。
    """
    formatted_string, details_list, _, _ = await _build_readable_messages_internal(
        messages, replace_bot_name, merge_messages, timestamp_mode, truncate
    )
    return formatted_string, details_list


async def build_readable_messages_with_id(
    messages: list[dict[str, Any]],
    replace_bot_name: bool = True,
    merge_messages: bool = False,
    timestamp_mode: str = "relative",
    read_mark: float = 0.0,
    truncate: bool = False,
    show_actions: bool = False,
    show_pic: bool = True,
) -> tuple[str, list[dict[str, Any]]]:
    """
    将消息列表转换为可读的文本格式，并返回原始(时间戳, 昵称, 内容)列表。
    允许通过参数控制格式化行为。
    """
    message_id_list = assign_message_ids(messages)

    formatted_string = await build_readable_messages(
        messages=messages,
        replace_bot_name=replace_bot_name,
        merge_messages=merge_messages,
        timestamp_mode=timestamp_mode,
        truncate=truncate,
        show_actions=show_actions,
        show_pic=show_pic,
        read_mark=read_mark,
        message_id_list=message_id_list,
    )

    return formatted_string, message_id_list


async def build_readable_messages(
    messages: list[dict[str, Any]],
    replace_bot_name: bool = True,
    merge_messages: bool = False,
    timestamp_mode: str = "relative",
    read_mark: float = 0.0,
    truncate: bool = False,
    show_actions: bool = True,
    show_pic: bool = True,
    message_id_list: list[dict[str, Any]] | None = None,
) -> str:  # sourcery skip: extract-method
    """
    将消息列表转换为可读的文本格式。
    如果提供了 read_mark，则在相应位置插入已读标记。
    允许通过参数控制格式化行为。

    Args:
        messages: 消息列表
        replace_bot_name: 是否替换机器人名称为"你"
        merge_messages: 是否合并连续消息
        timestamp_mode: 时间戳显示模式
        read_mark: 已读标记时间戳
        truncate: 是否截断长消息
        show_actions: 是否显示动作记录
    """
    assert global_config is not None
    # 创建messages的深拷贝，避免修改原始列表
    if not messages:
        return ""

    copy_messages = [msg.copy() for msg in messages]

    if not copy_messages:
        return ""

    if show_actions and copy_messages:
        # 获取所有消息的时间范围
        min_time = min(msg.get("time", 0) for msg in copy_messages)
        max_time = max(msg.get("time", 0) for msg in copy_messages)

        # 从第一条消息中获取chat_id
        chat_id = copy_messages[0].get("chat_id") if copy_messages else None

        from src.common.database.compatibility import get_db_session

        async with get_db_session() as session:
            # 获取这个时间范围内的动作记录，并匹配chat_id
            actions_in_range = (
                await session.execute(
                    select(ActionRecords)
                    .where(
                        and_(
                            ActionRecords.time >= min_time,
                            ActionRecords.time <= max_time,
                            ActionRecords.chat_id == chat_id,
                        )
                    )
                    .order_by(ActionRecords.time)
                )
            ).scalars()

            # 获取最新消息之后的第一个动作记录
            action_after_latest = (
                await session.execute(
                    select(ActionRecords)
                    .where(and_(ActionRecords.time > max_time, ActionRecords.chat_id == chat_id))
                    .order_by(ActionRecords.time)
                    .limit(1)
                )
            ).scalars()

            # 合并两部分动作记录，并转为 dict，避免 DetachedInstanceError
            actions = [
                {
                    "time": a.time,
                    "user_id": str(global_config.bot.qq_account),
                    "user_nickname": global_config.bot.nickname,
                    "user_cardname": "",
                    "processed_plain_text": f"{a.action_prompt_display}",
                    "display_message": f"{a.action_prompt_display}",
                    "chat_info_platform": a.chat_info_platform,
                    "is_action_record": True,
                    "action_name": a.action_name,
                    "action_build_into_prompt": a.action_build_into_prompt,
                }
                for a in list(actions_in_range) + list(action_after_latest)
            ]

        # 将动作记录转换为消息格式
        for action in actions:
            # 只有当build_into_prompt为True时才添加动作记录
            if action["action_build_into_prompt"]:
                action_msg = action.copy()
                copy_messages.append(action_msg)

        # 重新按时间排序
        copy_messages.sort(key=lambda x: x.get("time", 0))

    if read_mark <= 0:
        # 没有有效的 read_mark，直接格式化所有消息
        formatted_string, _, _, _ = await _build_readable_messages_internal(
            copy_messages,
            replace_bot_name,
            merge_messages,
            timestamp_mode,
            truncate,
            show_pic=show_pic,
            message_id_list=message_id_list,
        )

        return formatted_string
    else:
        # 按 read_mark 分割消息
        messages_before_mark = [msg for msg in copy_messages if msg.get("time", 0) <= read_mark]
        messages_after_mark = [msg for msg in copy_messages if msg.get("time", 0) > read_mark]

        # 共享的图片映射字典和计数器
        pic_id_mapping = {}
        pic_counter = 1

        # 分别格式化，但使用共享的图片映射
        formatted_before, _, pic_id_mapping, pic_counter = await _build_readable_messages_internal(
            messages_before_mark,
            replace_bot_name,
            merge_messages,
            timestamp_mode,
            truncate,
            pic_id_mapping,
            pic_counter,
            show_pic=show_pic,
            message_id_list=message_id_list,
        )
        formatted_after, _, pic_id_mapping, _ = await _build_readable_messages_internal(
            messages_after_mark,
            replace_bot_name,
            merge_messages,
            timestamp_mode,
            False,
            pic_id_mapping,
            pic_counter,
            show_pic=show_pic,
            message_id_list=message_id_list,
        )

        read_mark_line = "\n--- 以上消息是你已经看过，请关注以下未读的新消息---\n"

        # 组合结果
        result_parts = []
        if formatted_before and formatted_after:
            result_parts.extend([formatted_before, read_mark_line, formatted_after])
        elif formatted_before:
            result_parts.extend([formatted_before, read_mark_line])
        elif formatted_after:
            result_parts.extend([read_mark_line.strip(), formatted_after])
        else:
            result_parts.append(read_mark_line.strip())

        return "".join(result_parts)


async def build_anonymous_messages(messages: list[dict[str, Any]], filter_for_learning: bool = False) -> str:
    """
    构建匿名可读消息，将不同人的名称转为唯一占位符（A、B、C...），bot自己用SELF。
    处理 回复<aaa:bbb> 和 @<aaa:bbb> 字段，将bbb映射为匿名占位符。
    
    Args:
        messages: 消息列表
        filter_for_learning: 是否为表达学习场景进行额外过滤（过滤掉纯回复、纯@、纯图片等无意义内容）
    """
    assert global_config is not None
    if not messages:
        print("111111111111没有消息，无法构建匿名消息")
        return ""

    person_map = {}
    current_char = ord("A")
    output_lines = []

    # This function builds anonymous messages, so we don't need full descriptions.
    # The existing placeholder logic is sufficient.
    # However, to maintain consistency, we will adapt it slightly.

    def get_anon_name(platform, user_id):
        # print(f"get_anon_name: platform:{platform}, user_id:{user_id}")
        # print(f"global_config.bot.qq_account:{global_config.bot.qq_account}")
        assert global_config is not None

        if user_id == global_config.bot.qq_account:
            # print("SELF11111111111111")
            return "SELF"
        try:
            person_id = PersonInfoManager.get_person_id(platform, user_id)
        except Exception as _e:
            person_id = None
        if not person_id:
            return "?"
        if person_id not in person_map:
            nonlocal current_char
            person_map[person_id] = chr(current_char)
            current_char += 1
        return person_map[person_id]
    
    def is_meaningless_content(content: str, msg: dict) -> bool:
        """
        判断消息内容是否无意义（用于表达学习过滤）
        """
        if not content or not content.strip():
            return True
        
        stripped = content.strip()
        
        # 检查消息标记字段
        if msg.get("is_emoji", False):
            return True
        if msg.get("is_notify", False):
            return True
        if msg.get("is_public_notice", False):
            return True
        if msg.get("is_command", False):
            return True
        
        # 🔥 检查纯回复消息（只有[回复<xxx>]没有其他内容）
        reply_pattern = r"^\s*\[回复[^\]]*\]\s*$"
        if re.match(reply_pattern, stripped):
            return True
        
        # 🔥 检查纯@消息（只有@xxx没有其他内容）
        at_pattern = r"^\s*(@[^\s]+\s*)+$"
        if re.match(at_pattern, stripped):
            return True
        
        # 🔥 检查纯图片消息
        image_pattern = r"^\s*(\[图片\]|\[动画表情\]|\[表情\]|\[picid:[^\]]+\])\s*$"
        if re.match(image_pattern, stripped):
            return True
        
        # 🔥 移除回复标记、@标记、图片标记后检查是否还有实质内容
        clean_content = re.sub(r"\[回复[^\]]*\]", "", stripped)
        clean_content = re.sub(r"@[^\s]+", "", clean_content)
        clean_content = re.sub(r"\[图片\]|\[动画表情\]|\[表情\]|\[picid:[^\]]+\]", "", clean_content)
        clean_content = clean_content.strip()
        
        # 如果移除后内容太短（少于2个字符），认为无意义
        if len(clean_content) < 2:
            return True
        
        return False

    for msg in messages:
        try:
            platform: str = msg.get("chat_info_platform")  # type: ignore
            user_id = msg.get("user_id")
            _timestamp = msg.get("time")
            content: str = ""
            if msg.get("display_message"):
                content = msg.get("display_message", "")
            else:
                content = msg.get("processed_plain_text", "")

            if "ᶠ" in content:
                content = content.replace("ᶠ", "")
            if "ⁿ" in content:
                content = content.replace("ⁿ", "")

            # For anonymous messages, we just replace with a placeholder.
            content = re.sub(r"\[picid:([^\]]+)\]", "[图片]", content)
            
            # 🔥 表达学习场景：过滤无意义消息
            if filter_for_learning and is_meaningless_content(content, msg):
                continue

            # if not all([platform, user_id, timestamp is not None]):
            # continue

            anon_name = get_anon_name(platform, user_id)
            # print(f"anon_name:{anon_name}")

            # 使用独立函数处理用户引用格式，传入自定义的匿名名称解析器
            async def anon_name_resolver(platform: str, user_id: str) -> str:
                try:
                    return get_anon_name(platform, user_id)
                except Exception:
                    return "?"

            content = await replace_user_references_async(content, platform, anon_name_resolver, replace_bot_name=False)

            header = f"{anon_name}说 "
            output_lines.append(header)
            stripped_line = content.strip()
            if stripped_line:
                if stripped_line.endswith("。"):
                    stripped_line = stripped_line[:-1]
                output_lines.append(f"{stripped_line}")
            # print(f"output_lines:{output_lines}")
            output_lines.append("\n")
        except Exception:
            continue

    # Since we are not generating a pic_mapping_info block, just join and return.
    formatted_string = "".join(output_lines).strip()
    return formatted_string


async def get_person_id_list(messages: list[dict[str, Any]]) -> list[str]:
    """
    从消息列表中提取不重复的 person_id 列表 (忽略机器人自身)。

    Args:
        messages: 消息字典列表。

    Returns:
        一个包含唯一 person_id 的列表。
    """
    assert global_config is not None
    person_ids_set = set()  # 使用集合来自动去重

    for msg in messages:
        platform: str = msg.get("user_platform")  # type: ignore
        user_id: str = msg.get("user_id")  # type: ignore

        # 检查必要信息是否存在 且 不是机器人自己
        if not all([platform, user_id]) or user_id == global_config.bot.qq_account:
            continue

        # 添加空值检查，防止 platform 为 None 时出错
        if platform is None:
            platform = "unknown"

        if person_id := PersonInfoManager.get_person_id(platform, user_id):
            person_ids_set.add(person_id)

    return list(person_ids_set)
