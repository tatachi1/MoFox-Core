import asyncio
import base64
import binascii
import hashlib
import io
import os
import time
import traceback

from PIL import Image

from src.chat.emoji_system.emoji_constants import EMOJI_REGISTERED_DIR
from src.chat.utils.utils_image import image_path_to_base64
from src.common.database.api.crud import CRUDBase
from src.common.database.compatibility import get_db_session
from src.common.database.core.models import Emoji
from src.common.database.optimization.cache_manager import get_cache
from src.common.database.utils.decorators import generate_cache_key
from src.common.logger import get_logger

logger = get_logger("emoji")


class MaiEmoji:
    """定义一个表情包"""

    def __init__(self, full_path: str):
        if not full_path:
            raise ValueError("full_path cannot be empty")
        self.full_path = full_path
        self.path = os.path.dirname(full_path)
        self.filename = os.path.basename(full_path)
        self.embedding = []
        self.hash = ""
        self.description = ""
        self.emotion: list[str] = []
        self.usage_count = 0
        self.last_used_time = time.time()
        self.register_time = time.time()
        self.is_deleted = False
        self.format = ""

    async def initialize_hash_format(self) -> bool | None:
        """从文件创建表情包实例, 计算哈希值和格式"""
        try:
            if not os.path.exists(self.full_path):
                logger.error(f"[初始化错误] 表情包文件不存在: {self.full_path}")
                self.is_deleted = True
                return None

            logger.debug(f"[初始化] 正在读取文件: {self.full_path}")
            image_base64 = image_path_to_base64(self.full_path)
            if image_base64 is None:
                logger.error(f"[初始化错误] 无法读取或转换Base64: {self.full_path}")
                self.is_deleted = True
                return None
            logger.debug(f"[初始化] 文件读取成功 (Base64预览: {image_base64[:50]}...)")

            logger.debug(f"[初始化] 正在解码Base64并计算哈希: {self.filename}")
            if isinstance(image_base64, str):
                image_base64 = image_base64.encode("ascii", errors="ignore").decode("ascii")
            image_bytes = base64.b64decode(image_base64)
            self.hash = hashlib.md5(image_bytes).hexdigest()
            logger.debug(f"[初始化] 哈希计算成功: {self.hash}")

            logger.debug(f"[初始化] 正在使用Pillow获取格式: {self.filename}")
            try:
                with Image.open(io.BytesIO(image_bytes)) as img:
                    self.format = (img.format or "jpeg").lower()
                logger.debug(f"[初始化] 格式获取成功: {self.format}")
            except Exception as pil_error:
                logger.error(f"[初始化错误] Pillow无法处理图片 ({self.filename}): {pil_error}")
                logger.error(traceback.format_exc())
                self.is_deleted = True
                return None

            return True

        except FileNotFoundError:
            logger.error(f"[初始化错误] 文件在处理过程中丢失: {self.full_path}")
            self.is_deleted = True
            return None
        except (binascii.Error, ValueError) as b64_error:
            logger.error(f"[初始化错误] Base64解码失败 ({self.filename}): {b64_error}")
            self.is_deleted = True
            return None
        except Exception as e:
            logger.error(f"[初始化错误] 初始化表情包时发生未预期错误 ({self.filename}): {e!s}")
            logger.error(traceback.format_exc())
            self.is_deleted = True
            return None

    async def register_to_db(self) -> bool:
        """注册表情包，将文件移动到注册目录并保存数据库"""
        try:
            source_full_path = self.full_path
            destination_full_path = os.path.join(EMOJI_REGISTERED_DIR, self.filename)

            if not await asyncio.to_thread(os.path.exists, source_full_path):
                logger.error(f"[错误] 源文件不存在: {source_full_path}")
                return False

            try:
                if await asyncio.to_thread(os.path.exists, destination_full_path):
                    await asyncio.to_thread(os.remove, destination_full_path)

                await asyncio.to_thread(os.rename, source_full_path, destination_full_path)
                logger.debug(f"[移动] 文件从 {source_full_path} 移动到 {destination_full_path}")
                self.full_path = destination_full_path
                self.path = EMOJI_REGISTERED_DIR
            except Exception as move_error:
                logger.error(f"[错误] 移动文件失败: {move_error!s}")
                return False

            try:
                async with get_db_session() as session:
                    emotion_str = ",".join(self.emotion) if self.emotion else ""

                    emoji = Emoji(
                        emoji_hash=self.hash,
                        full_path=self.full_path,
                        format=self.format,
                        description=self.description,
                        emotion=emotion_str,
                        query_count=0,
                        is_registered=True,
                        is_banned=False,
                        record_time=self.register_time,
                        register_time=self.register_time,
                        usage_count=self.usage_count,
                        last_used_time=self.last_used_time,
                    )
                    session.add(emoji)
                    await session.commit()

                    logger.info(f"[注册] 表情包信息保存到数据库: {self.filename} ({self.emotion})")

                    return True

            except Exception as db_error:
                logger.error(f"[错误] 保存数据库失败 ({self.filename}): {db_error!s}")
                return False

        except Exception as e:
            logger.error(f"[错误] 注册表情包失败 ({self.filename}): {e!s}")
            logger.error(traceback.format_exc())
            return False

    async def delete(self) -> bool:
        """删除表情包文件及数据库记录"""
        try:
            file_to_delete = self.full_path
            if await asyncio.to_thread(os.path.exists, file_to_delete):
                try:
                    await asyncio.to_thread(os.remove, file_to_delete)
                    logger.debug(f"[删除] 文件: {file_to_delete}")
                except Exception as e:
                    logger.error(f"[错误] 删除文件失败 {file_to_delete}: {e!s}")

            try:
                crud = CRUDBase(Emoji)
                will_delete_emoji = await crud.get_by(emoji_hash=self.hash)
                if will_delete_emoji is None:
                    logger.warning(f"[删除] 数据库中未找到哈希值为 {self.hash} 的表情包记录。")
                    result = 0
                else:
                    await crud.delete(will_delete_emoji.id)
                    result = 1

                    cache = await get_cache()
                    await cache.delete(generate_cache_key("emoji_by_hash", self.hash))
                    await cache.delete(generate_cache_key("emoji_description", self.hash))
                    await cache.delete(generate_cache_key("emoji_tag", self.hash))
            except Exception as e:
                logger.error(f"[错误] 删除数据库记录时出错: {e!s}")
                result = 0

            if result > 0:
                logger.info(f"[删除] 表情包数据库记录 {self.filename} (Hash: {self.hash})")
                self.is_deleted = True
                return True
            if not os.path.exists(file_to_delete):
                logger.warning(
                    f"[警告] 表情包文件 {file_to_delete} 已删除，但数据库记录删除失败 (Hash: {self.hash})"
                )
            else:
                logger.error(f"[错误] 删除表情包数据库记录失败: {self.hash}")
            return False

        except Exception as e:
            logger.error(f"[错误] 删除表情包失败 ({self.filename}): {e!s}")
            return False
