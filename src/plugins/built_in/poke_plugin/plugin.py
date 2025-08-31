import asyncio
import random
from typing import List, Tuple, Type

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseAction,
    BaseCommand,
    ComponentInfo,
    ActionActivationType,
    ConfigField,
)
from src.common.logger import get_logger
from src.person_info.person_info import get_person_info_manager
from src.plugin_system.apis import generator_api

logger = get_logger("poke_plugin")


# ===== Action组件 =====
class PokeAction(BaseAction):
    """发送戳一戳动作"""

    # === 基本信息（必须填写）===
    action_name = "poke_user"
    action_description = "向用户发送戳一戳"
    activation_type = ActionActivationType.ALWAYS
    parallel_action = True

    # === 功能描述（必须填写）===
    action_parameters = {
        "user_name": "需要戳一戳的用户的名字",
        "times": "需要戳一戳的次数 (默认为 1)",
    }
    action_require = ["当需要戳某个用户时使用", "当你想提醒特定用户时使用"]
    llm_judge_prompt = """
    判定是否需要使用戳一戳动作的条件：
    1. 用户明确要求使用戳一戳。
    2. 你想以一种有趣的方式提醒或与某人互动。
    3. 上下文明确需要你戳一个或多个人。

    请回答"是"或"否"。
    """
    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        """执行戳一戳的动作"""
        user_name = self.action_data.get("user_name")
        try:
            times = int(self.action_data.get("times", 1))
        except (ValueError, TypeError):
            times = 1

        if not user_name:
            logger.warning("戳一戳动作缺少 'user_name' 参数。")
            return False, "缺少 'user_name' 参数"

        user_info = await get_person_info_manager().get_person_info_by_name(user_name)
        if not user_info or not user_info.get("user_id"):
            logger.info(f"找不到名为 '{user_name}' 的用户。")
            return False, f"找不到名为 '{user_name}' 的用户"

        user_id = user_info.get("user_id")

        for i in range(times):
            logger.info(f"正在向 {user_name} ({user_id}) 发送第 {i + 1}/{times} 次戳一戳...")
            await self.send_command(
                "SEND_POKE", args={"qq_id": user_id}, display_message=f"戳了戳 {user_name} ({i + 1}/{times})"
            )
            # 添加一个小的延迟，以避免发送过快
            await asyncio.sleep(0.5)

        success_message = f"已向 {user_name} 发送 {times} 次戳一戳。"
        await self.store_action_info(
            action_build_into_prompt=True, action_prompt_display=success_message, action_done=True
        )
        return True, success_message


# ===== Command组件 =====
class PokeBackCommand(BaseCommand):
    """反戳命令组件"""

    command_name = "poke_back"
    command_description = "检测到戳一戳时自动反戳回去"
    # 匹配戳一戳的正则表达式 - 匹配 "xxx戳了戳xxx" 的格式
    command_pattern = r"(?P<poker_name>\S+)\s*戳了戳\s*(?P<target_name>\S+)"

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行反戳逻辑"""
        # 检查反戳功能是否启用
        if not self.get_config("components.command_poke_back", True):
            return False, "", False

        # 获取匹配的用户名
        poker_name = self.matched_groups.get("poker_name", "")
        target_name = self.matched_groups.get("target_name", "")

        if not poker_name or not target_name:
            logger.debug("戳一戳消息格式不匹配，跳过反戳")
            return False, "", False

        # 只有当目标是机器人自己时才反戳
        if target_name not in ["我", "bot", "机器人", "麦麦"]:
            logger.debug(f"戳一戳目标不是机器人 ({target_name}), 跳过反戳")
            return False, "", False

        # 获取戳我的用户信息
        poker_info = await get_person_info_manager().get_person_info_by_name(poker_name)
        if not poker_info or not poker_info.get("user_id"):
            logger.info(f"找不到名为 '{poker_name}' 的用户信息，无法反戳")
            return False, "", False

        poker_id = poker_info.get("user_id")
        if not isinstance(poker_id, (int, str)):
            logger.error(f"获取到的用户ID类型不正确: {type(poker_id)}")
            return False, "", False

        # 确保poker_id是整数类型
        try:
            poker_id = int(poker_id)
        except (ValueError, TypeError):
            logger.error(f"无法将用户ID转换为整数: {poker_id}")
            return False, "", False

        # 检查反戳冷却时间（防止频繁反戳）
        cooldown_seconds = self.get_config("components.poke_back_cooldown", 5)
        current_time = asyncio.get_event_loop().time()

        # 使用类变量存储上次反戳时间
        if not hasattr(PokeBackCommand, "_last_poke_back_time"):
            PokeBackCommand._last_poke_back_time = {}

        last_time = PokeBackCommand._last_poke_back_time.get(poker_id, 0)
        if current_time - last_time < cooldown_seconds:
            logger.info(f"反戳冷却中，跳过对 {poker_name} 的反戳")
            return False, "", False

        # 记录本次反戳时间
        PokeBackCommand._last_poke_back_time[poker_id] = current_time

        # 执行反戳
        logger.info(f"检测到 {poker_name} 戳了我，准备反戳回去")

        try:
            # 获取反戳模式
            poke_back_mode = self.get_config("components.poke_back_mode", "poke")  # "poke", "reply", "random"

            if poke_back_mode == "random":
                # 随机选择模式
                poke_back_mode = random.choice(["poke", "reply"])

            if poke_back_mode == "poke":
                # 戳回去模式
                await self._poke_back(poker_id, poker_name)
            elif poke_back_mode == "reply":
                # 回复模式
                await self._reply_back(poker_name)
            else:
                logger.warning(f"未知的反戳模式: {poke_back_mode}")
                return False, "", False

            logger.info(f"成功反戳了 {poker_name} (模式: {poke_back_mode})")
            return True, f"反戳了 {poker_name}", False  # 不拦截消息继续处理

        except Exception as e:
            logger.error(f"反戳失败: {e}")
            return False, "", False

    async def _poke_back(self, poker_id: int, poker_name: str):
        """执行戳一戳反击"""
        await self.send_command(
            "SEND_POKE",
            args={"qq_id": poker_id},
            display_message=f"反戳了 {poker_name}",
            storage_message=False,  # 不存储到消息历史中
        )

        # 可选：发送一个随机的反戳回复
        poke_back_messages = self.get_config(
            "components.poke_back_messages",
            [
                "哼，戳回去！",
                "戳我干嘛~",
                "反戳！",
                "你戳我，我戳你！",
                "（戳回去）",
            ],
        )

        if poke_back_messages and self.get_config("components.send_poke_back_message", False):
            reply_message = random.choice(poke_back_messages)
            await self.send_text(reply_message)

    async def _reply_back(self, poker_name: str):
        """生成AI回复"""
        # 构造回复上下文
        extra_info = f"{poker_name}戳了我一下，需要生成一个有趣的回应。"

        # 获取配置，确保类型正确
        enable_typo = self.get_config("components.enable_typo_in_reply", False)
        if not isinstance(enable_typo, bool):
            enable_typo = False

        # 使用generator_api生成回复
        success, reply_set, _ = await generator_api.generate_reply(
            chat_stream=self.message.chat_stream,
            extra_info=extra_info,
            enable_tool=False,
            enable_splitter=True,
            enable_chinese_typo=enable_typo,
            from_plugin=True,
        )

        if success and reply_set:
            # 发送生成的回复
            for reply_item in reply_set:
                message_type, content = reply_item
                if message_type == "text":
                    await self.send_text(content)
                else:
                    await self.send_type(message_type, content)
        else:
            # 如果AI回复失败，发送一个默认回复
            fallback_messages = self.get_config(
                "components.fallback_reply_messages",
                [
                    "被戳了！",
                    "诶？",
                    "做什么呢~",
                    "怎么了？",
                ],
            )

            # 确保fallback_messages是列表
            if isinstance(fallback_messages, list) and fallback_messages:
                fallback_reply = random.choice(fallback_messages)
                await self.send_text(fallback_reply)
            else:
                await self.send_text("被戳了！")


# ===== 插件注册 =====
@register_plugin
class PokePlugin(BasePlugin):
    """戳一戳插件"""

    # 插件基本信息
    plugin_name: str = "poke_plugin"
    enable_plugin: bool = True
    dependencies: List[str] = []
    python_dependencies: List[str] = []
    config_file_name: str = "config.toml"

    # 配置节描述
    config_section_descriptions = {"plugin": "插件基本信息", "components": "插件组件"}

    # 配置Schema定义
    config_schema: dict = {
        "plugin": {
            "name": ConfigField(type=str, default="poke_plugin", description="插件名称"),
            "version": ConfigField(type=str, default="1.0.0", description="插件版本"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="1.0", description="配置版本"),
        },
        "components": {
            "action_poke_user": ConfigField(type=bool, default=True, description="是否启用戳一戳功能"),
            "command_poke_back": ConfigField(type=bool, default=True, description="是否启用反戳功能"),
            "poke_back_mode": ConfigField(
                type=str, default="poke", description="反戳模式: poke(戳回去), reply(AI回复), random(随机)"
            ),
            "poke_back_cooldown": ConfigField(type=int, default=5, description="反戳冷却时间（秒）"),
            "send_poke_back_message": ConfigField(type=bool, default=False, description="戳回去时是否发送文字回复"),
            "enable_typo_in_reply": ConfigField(type=bool, default=False, description="AI回复时是否启用错字生成"),
            "poke_back_messages": ConfigField(
                type=list,
                default=["哼，戳回去！", "戳我干嘛~", "反戳！", "你戳我，我戳你！", "（戳回去）"],
                description="戳回去时的随机回复消息列表",
            ),
            "fallback_reply_messages": ConfigField(
                type=list,
                default=["被戳了！", "诶？", "做什么呢~", "怎么了？"],
                description="AI回复失败时的备用回复消息列表",
            ),
        },
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        components = []

        # 添加戳一戳动作组件
        if self.get_config("components.action_poke_user"):
            components.append((PokeAction.get_action_info(), PokeAction))

        # 添加反戳命令组件
        if self.get_config("components.command_poke_back"):
            components.append((PokeBackCommand.get_command_info(), PokeBackCommand))

        return components
