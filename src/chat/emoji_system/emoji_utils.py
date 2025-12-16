import asyncio
import os
import time
from typing import Any

from src.chat.emoji_system.emoji_constants import BASE_DIR, EMOJI_DIR, EMOJI_REGISTERED_DIR
from src.chat.emoji_system.emoji_entities import MaiEmoji
from src.common.logger import get_logger

logger = get_logger("emoji")


def _emoji_objects_to_readable_list(emoji_objects: list[MaiEmoji]) -> list[str]:
    emoji_info_list = []
    for i, emoji in enumerate(emoji_objects):
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(emoji.register_time))
        emoji_info = f"编号: {i + 1}\n描述: {emoji.description}\n使用次数: {emoji.usage_count}\n添加时间: {time_str}\n"
        emoji_info_list.append(emoji_info)
    return emoji_info_list


def _to_emoji_objects(data: Any) -> tuple[list[MaiEmoji], int]:
    emoji_objects = []
    load_errors = 0
    emoji_data_list = list(data)

    for emoji_data in emoji_data_list:
        full_path = emoji_data.full_path
        if not full_path:
            logger.warning(
                f"[加载错误] 数据库记录缺少 'full_path' 字段: ID {emoji_data.id if hasattr(emoji_data, 'id') else 'Unknown'}"
            )
            load_errors += 1
            continue

        try:
            emoji = MaiEmoji(full_path=full_path)

            emoji.hash = emoji_data.emoji_hash
            if not emoji.hash:
                logger.warning(f"[加载错误] 数据库记录缺少 'hash' 字段: {full_path}")
                load_errors += 1
                continue

            emoji.description = emoji_data.description
            emoji.emotion = emoji_data.emotion.split(",") if emoji_data.emotion else []
            emoji.usage_count = emoji_data.usage_count

            db_last_used_time = emoji_data.last_used_time
            db_register_time = emoji_data.register_time

            emoji.last_used_time = db_last_used_time if db_last_used_time is not None else emoji.register_time
            emoji.register_time = db_register_time if db_register_time is not None else emoji.register_time

            emoji.format = emoji_data.format

            emoji_objects.append(emoji)

        except ValueError as ve:
            logger.error(f"[加载错误] 初始化 MaiEmoji 失败 ({full_path}): {ve}")
            load_errors += 1
        except Exception as e:
            logger.error(f"[加载错误] 处理数据库记录时出错 ({full_path}): {e!s}")
            load_errors += 1
    return emoji_objects, load_errors


def _ensure_emoji_dir() -> None:
    os.makedirs(EMOJI_DIR, exist_ok=True)
    os.makedirs(EMOJI_REGISTERED_DIR, exist_ok=True)


async def clear_temp_emoji() -> None:
    logger.info("[清理] 开始清理缓存...")

    for need_clear in (
        os.path.join(BASE_DIR, "emoji"),
        os.path.join(BASE_DIR, "image"),
        os.path.join(BASE_DIR, "images"),
    ):
        if await asyncio.to_thread(os.path.exists, need_clear):
            files = await asyncio.to_thread(os.listdir, need_clear)
            if len(files) > 1000:
                for i, filename in enumerate(files):
                    file_path = os.path.join(need_clear, filename)
                    if await asyncio.to_thread(os.path.isfile, file_path):
                        try:
                            await asyncio.to_thread(os.remove, file_path)
                            logger.debug(f"[清理] 删除: {filename}")
                        except Exception as e:
                            logger.debug(f"[清理] 删除失败 {filename}: {e!s}")
                    if (i + 1) % 100 == 0:
                        await asyncio.sleep(0)


async def clean_unused_emojis(emoji_dir: str, emoji_objects: list[MaiEmoji], removed_count: int) -> int:
    if not await asyncio.to_thread(os.path.exists, emoji_dir):
        logger.warning(f"[清理] 目标目录不存在，跳过清理: {emoji_dir}")
        return removed_count

    cleaned_count = 0
    try:
        tracked_full_paths = {emoji.full_path for emoji in emoji_objects if not emoji.is_deleted}

        for entry in await asyncio.to_thread(lambda: list(os.scandir(emoji_dir))):
            if not entry.is_file():
                continue

            file_full_path = entry.path

            if file_full_path not in tracked_full_paths:
                try:
                    await asyncio.to_thread(os.remove, file_full_path)
                    logger.info(f"[清理] 删除未追踪的表情包文件: {file_full_path}")
                    cleaned_count += 1
                except Exception as e:
                    logger.error(f"[错误] 删除文件时出错 ({file_full_path}): {e!s}")

        if cleaned_count > 0:
            logger.info(f"[清理] 在目录 {emoji_dir} 中清理了 {cleaned_count} 个破损表情包。")
        else:
            logger.info(f"[清理] 目录 {emoji_dir} 中没有需要清理的。")

    except Exception as e:
        logger.error(f"[错误] 清理未使用表情包文件时出错 ({emoji_dir}): {e!s}")

    return removed_count + cleaned_count


async def list_image_files(directory: str) -> tuple[list[str], bool]:
    def _scan() -> tuple[list[str], bool]:
        entries = list(os.scandir(directory))
        files = [
            entry.name
            for entry in entries
            if entry.is_file() and entry.name.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))
        ]
        return files, len(entries) == 0

    return await asyncio.to_thread(_scan)
