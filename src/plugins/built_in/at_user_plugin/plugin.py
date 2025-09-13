from typing import List, Tuple, Type
from src.plugin_system import (
    BasePlugin,
    BaseCommand,
    CommandInfo,
    register_plugin,
    BaseAction,
    ActionInfo,
    ActionActivationType,
)
from src.common.logger import get_logger
from src.plugin_system.base.component_types import ChatType

logger = get_logger(__name__)


class AtAction(BaseAction):
    """发送艾特消息"""

    # === 基本信息（必须填写）===
    action_name = "at_user"
    action_description = "发送艾特消息"
    activation_type = ActionActivationType.LLM_JUDGE 
    parallel_action = False
    chat_type_allow = ChatType.GROUP

    # === 功能描述（必须填写）===
    action_parameters = {"user_name": "需要艾特用户的名字", "at_message": "艾特用户时要发送的消息"}
    action_require = [
        "当用户明确要求你去'叫'、'喊'、'提醒'或'艾特'某人时使用",
        "当你判断，为了让特定的人看到消息，需要代表用户去呼叫他/她时使用",
        "例如：'你去叫一下张三'，'提醒一下李四开会'",
    ]
    llm_judge_prompt = """
    判定是否需要使用艾特用户动作的条件：
    1. 你在对话中提到了某个具体的人，并且需要提醒他/她。
    3. 上下文明确需要你艾特一个或多个人。

    请回答"是"或"否"。
    """
    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        """执行艾特用户的动作"""
        user_name = self.action_data.get("user_name")
        at_message = self.action_data.get("at_message")

        if not user_name or not at_message:
            logger.warning("艾特用户的动作缺少必要参数。")
            return False, "缺少必要参数"

        from src.plugin_system.apis import send_api
        from fuzzywuzzy import process

        group_id = self.chat_stream.group_info.group_id
        if not group_id:
            return False, "无法获取群组ID"

        response = await send_api.adapter_command_to_stream(
            action="get_group_member_list",
            params={"group_id": group_id},
            stream_id=self.chat_id,
        )

        if response.get("status") != "ok":
            return False, f"获取群成员列表失败: {response.get('message')}"

        member_list = response.get("data", [])
        if not member_list:
            return False, "群成员列表为空"

        # 使用模糊匹配找到最接近的用户名
        choices = {member["card"] or member["nickname"]: member["user_id"] for member in member_list}
        best_match, score = process.extractOne(user_name, choices.keys())
        
        if score < 30: # 设置一个匹配度阈值
            logger.info(f"找不到与 '{user_name}' 高度匹配的用户 (最佳匹配: {best_match}, 分数: {score})")
            return False, "用户不存在"
            
        user_id = choices[best_match]
        user_info = {"user_id": user_id, "user_nickname": best_match}

        try:
            from src.chat.replyer.default_generator import DefaultReplyer
            from src.chat.message_receive.chat_stream import get_chat_manager

            chat_manager = get_chat_manager()
            chat_stream = chat_manager.get_stream(self.chat_id)
            
            if not chat_stream:
                logger.error(f"找不到聊天流: {self.stream_id}")
                return False, "聊天流不存在"
            
            replyer = DefaultReplyer(chat_stream)
            extra_info = f"你需要艾特用户 {user_name} 并回复他们说: {at_message}"
            
            success, llm_response, _ = await replyer.generate_reply_with_context(
                reply_to=f"{user_name}:{at_message}",
                extra_info=extra_info,
                enable_tool=False,
                from_plugin=False
            )
            
            if not success or not llm_response:
                logger.error("回复器生成回复失败")
                return False, "回复生成失败"
            
            final_message_raw = llm_response.get("content", "")
            if not final_message_raw:
                logger.warning("回复器生成了空内容")
                return False, "回复内容为空"

            # 对LLM生成的内容进行后处理，解析[SPLIT]标记并将分段消息合并
            from src.chat.utils.utils import process_llm_response
            final_message_segments = process_llm_response(final_message_raw, enable_splitter=True, enable_chinese_typo=False)
            final_message = " ".join(final_message_segments)

            await self.send_command(
                "SEND_AT_MESSAGE",
                args={"group_id": self.chat_stream.group_info.group_id, "qq_id": user_id, "text": final_message},
                display_message=f"艾特用户 {user_name} 并发送消息: {final_message}",
            )
            
            await self.store_action_info(
                action_build_into_prompt=True,
                action_prompt_display=f"执行了艾特用户动作：艾特用户 {user_name} 并发送消息: {final_message}",
                action_done=True,
            )
            
            logger.info(f"成功发送艾特消息给 {user_name}: {final_message}")
            return True, "艾特消息发送成功"
                
        except Exception as e:
            logger.error(f"执行艾特用户动作时发生异常: {e}", exc_info=True)
            return False, f"执行失败: {str(e)}"


@register_plugin
class AtUserPlugin(BasePlugin):
    plugin_name: str = "at_user_plugin"
    enable_plugin: bool = True
    dependencies: list[str] = []
    python_dependencies: list[str] = ["fuzzywuzzy", "python-Levenshtein"]
    config_file_name: str = "config.toml"
    config_schema: dict = {}

    def get_plugin_components(self) -> List[Tuple[CommandInfo | ActionInfo, Type[BaseCommand] | Type[BaseAction]]]:
        return [
            (AtAction.get_action_info(), AtAction),
        ]
