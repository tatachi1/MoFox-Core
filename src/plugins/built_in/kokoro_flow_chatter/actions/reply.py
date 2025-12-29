"""
KFC 回复动作模块

KFC 的 reply 动作：
- 完整的回复流程在 execute() 中实现
- 调用 Replyer 生成回复文本
- 回复后处理（系统格式词过滤、分段发送、错字生成等）
- 发送回复消息

与 AFC 类似，但使用 KFC 专属的 Replyer 和 Session 系统。
"""

import asyncio
from typing import TYPE_CHECKING, ClassVar, Optional

from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system import ActionActivationType, BaseAction, ChatMode
from src.plugin_system.apis import send_api

if TYPE_CHECKING:
    from ..session import KokoroSession

logger = get_logger("kfc_reply_action")


class KFCReplyAction(BaseAction):
    """KFC Reply 动作 - 完整的私聊回复流程

    特点：
    - 完整的回复流程：生成回复 → 后处理 → 分段发送
    - 使用 KFC 专属的 Replyer 生成回复
    - 支持系统格式词过滤、分段发送、错字生成等后处理
    - 仅限 KokoroFlowChatter 使用

    action_data 参数：
    - user_id: 用户ID（必需，用于获取 Session）
    - user_name: 用户名称（必需）
    - thought: Planner 生成的想法/内心独白（必需）
    - situation_type: 情况类型（可选，默认 "new_message"）
    - extra_context: 额外上下文（可选）
    - content: 预生成的回复内容（可选，如果提供则直接发送）
    - should_quote_reply: 是否引用原消息（可选，默认 false）
    - enable_splitter: 是否启用分段发送（可选，默认 true）
    - enable_chinese_typo: 是否启用错字生成（可选，默认 true）
    """

    # 动作基本信息
    action_name = "kfc_reply"
    action_description = "发送回复消息。会根据当前对话情境生成并发送回复。"

    # 激活设置
    activation_type = ActionActivationType.ALWAYS
    mode_enable = ChatMode.ALL
    parallel_action = False

    # Chatter 限制：仅允许 KokoroFlowChatter 使用
    chatter_allow: ClassVar[list[str]] = ["KokoroFlowChatter"]

    # 动作参数定义
    action_parameters: ClassVar = {
        "content": "要发送的回复内容（可选，如果不提供则自动生成）",
        "should_quote_reply": "是否引用原消息（可选，true/false，默认 false）",
    }

    # 动作使用场景
    action_require: ClassVar = [
        "需要发送回复消息时使用",
        "私聊场景的标准回复动作",
    ]

    # 关联类型
    associated_types: ClassVar[list[str]] = ["text"]

    async def execute(self) -> tuple[bool, str]:
        """执行 reply 动作 - 完整的回复流程"""
        try:
            # 1. 检查是否有预生成的内容
            content = self.action_data.get("content", "")

            if not content:
                # 2. 需要生成回复，获取必要信息
                user_id = self.action_data.get("user_id")
                user_name = self.action_data.get("user_name", "用户")
                thought = self.action_data.get("thought", "")
                situation_type = self.action_data.get("situation_type", "new_message")
                extra_context = self.action_data.get("extra_context")

                if not user_id:
                    logger.warning(f"{self.log_prefix} 缺少 user_id，无法生成回复")
                    return False, ""

                # 3. 获取 Session
                session = await self._get_session(user_id)
                if not session:
                    logger.warning(f"{self.log_prefix} 无法获取 Session: {user_id}")
                    return False, ""

                # 4. 调用 Replyer 生成回复
                success, content = await self._generate_reply(
                    session=session,
                    user_name=user_name,
                    thought=thought,
                    situation_type=situation_type,
                    extra_context=extra_context,
                )

                if not success or not content:
                    logger.warning(f"{self.log_prefix} 回复生成失败")
                    return False, ""

            # 5. 回复后处理（系统格式词过滤 + 分段处理）
            enable_splitter = self.action_data.get("enable_splitter", True)
            enable_chinese_typo = self.action_data.get("enable_chinese_typo", True)

            processed_segments = self._post_process_reply(
                content=content,
                enable_splitter=enable_splitter,
                enable_chinese_typo=enable_chinese_typo,
            )

            if not processed_segments:
                logger.warning(f"{self.log_prefix} 回复后处理后内容为空")
                return False, ""

            # 6. 分段发送回复
            should_quote = self.action_data.get("should_quote_reply", False)
            reply_text = await self._send_segments(
                segments=processed_segments,
                should_quote=should_quote,
            )

            logger.info(f"{self.log_prefix} KFC reply 动作执行成功: {reply_text[:50]}...")
            return True, reply_text

        except asyncio.CancelledError:
            logger.debug(f"{self.log_prefix} 回复任务被取消")
            return False, ""
        except Exception as e:
            logger.error(f"{self.log_prefix} KFC reply 动作执行失败: {e}")
            import traceback
            traceback.print_exc()
            return False, ""

    def _post_process_reply(
        self,
        content: str,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
    ) -> list[str]:
        """
        回复后处理

        包括：
        1. 系统格式词过滤（移除 [回复...]、[表情包：...]、@<...> 等）
        2. 分段处理（根据标点分句、智能合并）
        3. 错字生成（拟人化）

        Args:
            content: 原始回复内容
            enable_splitter: 是否启用分段
            enable_chinese_typo: 是否启用错字生成

        Returns:
            处理后的文本段落列表
        """
        try:
            from src.chat.utils.utils import filter_system_format_content, process_llm_response

            # 1. 过滤系统格式词
            filtered_content = filter_system_format_content(content)

            if not filtered_content or not filtered_content.strip():
                logger.warning(f"{self.log_prefix} 过滤系统格式词后内容为空")
                return []

            # 2. 分段处理 + 错字生成
            processed_segments = process_llm_response(
                filtered_content,
                enable_splitter=enable_splitter,
                enable_chinese_typo=enable_chinese_typo,
            )

            # 过滤空段落
            processed_segments = [seg for seg in processed_segments if seg and seg.strip()]

            logger.debug(
                f"{self.log_prefix} 回复后处理完成: "
                f"原始长度={len(content)}, 过滤后长度={len(filtered_content)}, "
                f"分段数={len(processed_segments)}"
            )

            return processed_segments

        except Exception as e:
            logger.error(f"{self.log_prefix} 回复后处理失败: {e}")
            # 失败时返回原始内容
            return [content] if content else []

    async def _send_segments(
        self,
        segments: list[str],
        should_quote: bool = False,
    ) -> str:
        """
        分段发送回复

        Args:
            segments: 要发送的文本段落列表
            should_quote: 是否引用原消息（仅第一条消息引用）

        Returns:
            完整的回复文本（所有段落拼接）
        """
        reply_text = ""
        first_sent = False

        # 获取分段发送的间隔时间
        typing_delay = 0.5
        if global_config and hasattr(global_config, "response_splitter"):
            typing_delay = getattr(global_config.response_splitter, "typing_delay", 0.5)

        for segment in segments:
            if not segment or not segment.strip():
                continue

            reply_text += segment

            # 发送消息
            if not first_sent:
                # 第一条消息：可能需要引用
                await send_api.text_to_stream(
                    text=segment,
                    stream_id=self.chat_stream.stream_id,
                    reply_to_message=self.action_message,
                    set_reply=should_quote and bool(self.action_message),
                    typing=False,
                )
                first_sent = True
            else:
                # 后续消息：模拟打字延迟
                if typing_delay > 0:
                    await asyncio.sleep(typing_delay)

                await send_api.text_to_stream(
                    text=segment,
                    stream_id=self.chat_stream.stream_id,
                    reply_to_message=None,
                    set_reply=False,
                    typing=True,
                )

        return reply_text

    async def _get_session(self, user_id: str) -> Optional["KokoroSession"]:
        """获取用户 Session"""
        try:
            from ..session import get_session_manager

            session_manager = get_session_manager()
            return await session_manager.get_session(user_id, self.chat_stream.stream_id)
        except Exception as e:
            logger.error(f"{self.log_prefix} 获取 Session 失败: {e}")
            return None

    async def _generate_reply(
        self,
        session: "KokoroSession",
        user_name: str,
        thought: str,
        situation_type: str,
        extra_context: dict | None = None,
    ) -> tuple[bool, str]:
        """调用 Replyer 生成回复"""
        try:
            from ..replyer import generate_reply_text

            return await generate_reply_text(
                session=session,
                user_name=user_name,
                thought=thought,
                situation_type=situation_type,
                chat_stream=self.chat_stream,
                extra_context=extra_context,
            )
        except Exception as e:
            logger.error(f"{self.log_prefix} 生成回复失败: {e}")
            return False, ""
