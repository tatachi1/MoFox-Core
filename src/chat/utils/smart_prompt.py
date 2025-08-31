"""
智能Prompt系统 - 完全重构版本
基于原有DefaultReplyer的完整功能集成，使用新的参数结构
解决实现质量不高、功能集成不完整和错误处理不足的问题
"""

import asyncio
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple

from src.chat.utils.prompt_builder import global_prompt_manager, Prompt
from src.common.logger import get_logger
from src.config.config import global_config
from src.chat.utils.chat_message_builder import (
    build_readable_messages,
)
from src.person_info.person_info import get_person_info_manager
from src.chat.utils.prompt_utils import PromptUtils
from src.chat.utils.prompt_parameters import SmartPromptParameters

logger = get_logger("smart_prompt")


@dataclass
class ChatContext:
    """聊天上下文信息"""

    chat_id: str = ""
    platform: str = ""
    is_group: bool = False
    user_id: str = ""
    user_nickname: str = ""
    group_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class SmartPromptBuilder:
    """重构的智能提示词构建器 - 统一错误处理和功能集成，移除缓存机制和依赖检查"""

    def __init__(self):
        # 移除缓存相关初始化
        pass

    async def build_context_data(self, params: SmartPromptParameters) -> Dict[str, Any]:
        """并行构建完整的上下文数据 - 移除缓存机制和依赖检查"""

        # 并行执行所有构建任务
        start_time = time.time()
        timing_logs = {}

        try:
            # 准备构建任务
            tasks = []
            task_names = []

            # 初始化预构建参数，使用新的结构
            pre_built_params = {}
            if params.expression_habits_block:
                pre_built_params["expression_habits_block"] = params.expression_habits_block
            if params.relation_info_block:
                pre_built_params["relation_info_block"] = params.relation_info_block
            if params.memory_block:
                pre_built_params["memory_block"] = params.memory_block
            if params.tool_info_block:
                pre_built_params["tool_info_block"] = params.tool_info_block
            if params.knowledge_prompt:
                pre_built_params["knowledge_prompt"] = params.knowledge_prompt
            if params.cross_context_block:
                pre_built_params["cross_context_block"] = params.cross_context_block

            # 根据新的参数结构确定要构建的项
            if params.enable_expression and not pre_built_params.get("expression_habits_block"):
                tasks.append(self._build_expression_habits(params))
                task_names.append("expression_habits")

            if params.enable_memory and not pre_built_params.get("memory_block"):
                tasks.append(self._build_memory_block(params))
                task_names.append("memory_block")

            if params.enable_relation and not pre_built_params.get("relation_info_block"):
                tasks.append(self._build_relation_info(params))
                task_names.append("relation_info")

            # 添加mai_think上下文构建任务
            if not pre_built_params.get("mai_think"):
                tasks.append(self._build_mai_think_context(params))
                task_names.append("mai_think_context")

            if params.enable_tool and not pre_built_params.get("tool_info_block"):
                tasks.append(self._build_tool_info(params))
                task_names.append("tool_info")

            if params.enable_knowledge and not pre_built_params.get("knowledge_prompt"):
                tasks.append(self._build_knowledge_info(params))
                task_names.append("knowledge_info")

            if params.enable_cross_context and not pre_built_params.get("cross_context_block"):
                tasks.append(self._build_cross_context(params))
                task_names.append("cross_context")

            # 性能优化：根据任务数量动态调整超时时间
            base_timeout = 10.0  # 基础超时时间
            task_timeout = 2.0  # 每个任务的超时时间
            timeout_seconds = min(
                max(base_timeout, len(tasks) * task_timeout),  # 根据任务数量计算超时
                30.0,  # 最大超时时间
            )

            # 性能优化：限制并发任务数量，避免资源耗尽
            max_concurrent_tasks = 5  # 最大并发任务数
            if len(tasks) > max_concurrent_tasks:
                # 分批执行任务
                results = []
                for i in range(0, len(tasks), max_concurrent_tasks):
                    batch_tasks = tasks[i : i + max_concurrent_tasks]
                    batch_names = task_names[i : i + max_concurrent_tasks]

                    batch_results = await asyncio.wait_for(
                        asyncio.gather(*batch_tasks, return_exceptions=True), timeout=timeout_seconds
                    )
                    results.extend(batch_results)
            else:
                # 一次性执行所有任务
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=timeout_seconds
                )

            # 处理结果并收集性能数据
            context_data = {}
            for i, result in enumerate(results):
                task_name = task_names[i] if i < len(task_names) else f"task_{i}"

                if isinstance(result, Exception):
                    logger.error(f"构建任务{task_name}失败: {str(result)}")
                elif isinstance(result, dict):
                    # 结果格式: {component_name: value}
                    context_data.update(result)

                    # 记录耗时过长的任务
                    if task_name in timing_logs and timing_logs[task_name] > 8.0:
                        logger.warning(f"构建任务{task_name}耗时过长: {timing_logs[task_name]:.2f}s")

            # 添加预构建的参数
            for key, value in pre_built_params.items():
                if value:
                    context_data[key] = value

        except asyncio.TimeoutError:
            logger.error(f"构建超时 ({timeout_seconds}s)")
            context_data = {}

            # 添加预构建的参数，即使在超时情况下
            for key, value in pre_built_params.items():
                if value:
                    context_data[key] = value

        # 构建聊天历史 - 根据模式不同
        if params.prompt_mode == "s4u":
            await self._build_s4u_chat_context(context_data, params)
        else:
            await self._build_normal_chat_context(context_data, params)

        # 补充基础信息
        context_data.update(
            {
                "keywords_reaction_prompt": params.keywords_reaction_prompt,
                "extra_info_block": params.extra_info_block,
                "time_block": params.time_block or f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "identity": params.identity_block,
                "schedule_block": params.schedule_block,
                "moderation_prompt": params.moderation_prompt_block,
                "reply_target_block": params.reply_target_block,
                "mood_state": params.mood_prompt,
                "action_descriptions": params.action_descriptions,
            }
        )

        total_time = time.time() - start_time
        if timing_logs:
            timing_str = "; ".join([f"{name}: {time:.2f}s" for name, time in timing_logs.items()])
            logger.info(f"构建任务耗时: {timing_str}")
        logger.debug(f"构建完成，总耗时: {total_time:.2f}s")

        return context_data

    async def _build_s4u_chat_context(self, context_data: Dict[str, Any], params: SmartPromptParameters) -> None:
        """构建S4U模式的聊天上下文 - 使用新参数结构"""
        if not params.message_list_before_now_long:
            return

        # 使用共享工具构建分离历史
        core_dialogue, background_dialogue = await self._build_s4u_chat_history_prompts(
            params.message_list_before_now_long,
            params.target_user_info.get("user_id") if params.target_user_info else "",
        )

        context_data["core_dialogue_prompt"] = core_dialogue
        context_data["background_dialogue_prompt"] = background_dialogue

    async def _build_normal_chat_context(self, context_data: Dict[str, Any], params: SmartPromptParameters) -> None:
        """构建normal模式的聊天上下文 - 使用新参数结构"""
        if not params.chat_talking_prompt_short:
            return

        context_data["chat_info"] = f"""群里的聊天内容：
{params.chat_talking_prompt_short}"""

    async def _build_s4u_chat_history_prompts(
        self, message_list_before_now: List[Dict[str, Any]], target_user_id: str
    ) -> Tuple[str, str]:
        """构建S4U风格的分离对话prompt - 完整实现"""
        core_dialogue_list = []
        background_dialogue_list = []
        bot_id = str(global_config.bot.qq_account)

        # 过滤消息：分离bot和目标用户的对话 vs 其他用户的对话
        for msg_dict in message_list_before_now:
            try:
                msg_user_id = str(msg_dict.get("user_id"))
                reply_to = msg_dict.get("reply_to", "")
                _platform, reply_to_user_id = self._parse_reply_target(reply_to)
                if (msg_user_id == bot_id and reply_to_user_id == target_user_id) or msg_user_id == target_user_id:
                    # bot 和目标用户的对话
                    core_dialogue_list.append(msg_dict)
                else:
                    # 其他用户的对话
                    background_dialogue_list.append(msg_dict)
            except Exception as e:
                logger.error(f"处理消息记录时出错: {msg_dict}, 错误: {e}")

        # 构建背景对话 prompt
        background_dialogue_prompt = ""
        if background_dialogue_list:
            latest_25_msgs = background_dialogue_list[-int(global_config.chat.max_context_size * 0.5) :]
            background_dialogue_prompt_str = build_readable_messages(
                latest_25_msgs,
                replace_bot_name=True,
                timestamp_mode="normal",
                truncate=True,
            )
            background_dialogue_prompt = f"这是其他用户的发言：\n{background_dialogue_prompt_str}"

        # 构建核心对话 prompt
        core_dialogue_prompt = ""
        if core_dialogue_list:
            core_dialogue_list = core_dialogue_list[-int(global_config.chat.max_context_size * 2) :]  # 限制消息数量

            core_dialogue_prompt_str = build_readable_messages(
                core_dialogue_list,
                replace_bot_name=True,
                merge_messages=False,
                timestamp_mode="normal",
                read_mark=0.0,
                truncate=True,
                show_actions=True,
            )
            core_dialogue_prompt = core_dialogue_prompt_str

        return core_dialogue_prompt, background_dialogue_prompt

    async def _build_mai_think_context(self, params: SmartPromptParameters) -> Any:
        """构建mai_think上下文 - 完全继承DefaultReplyer功能"""
        from src.mais4u.mai_think import mai_thinking_manager

        # 获取mai_think实例
        mai_think = mai_thinking_manager.get_mai_think(params.chat_id)

        # 设置mai_think的上下文信息
        mai_think.memory_block = params.memory_block or ""
        mai_think.relation_info_block = params.relation_info_block or ""
        mai_think.time_block = params.time_block or f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # 设置聊天目标信息
        if params.is_group_chat:
            chat_target_1 = await global_prompt_manager.get_prompt_async("chat_target_group1")
            chat_target_2 = await global_prompt_manager.get_prompt_async("chat_target_group2")
        else:
            chat_target_name = "对方"
            if params.chat_target_info:
                chat_target_name = (
                    params.chat_target_info.get("person_name") or params.chat_target_info.get("user_nickname") or "对方"
                )
            chat_target_1 = await global_prompt_manager.format_prompt(
                "chat_target_private1", sender_name=chat_target_name
            )
            chat_target_2 = await global_prompt_manager.format_prompt(
                "chat_target_private2", sender_name=chat_target_name
            )

        mai_think.chat_target = chat_target_1
        mai_think.chat_target_2 = chat_target_2
        mai_think.chat_info = params.chat_talking_prompt_short or ""
        mai_think.mood_state = params.mood_prompt or ""
        mai_think.identity = params.identity_block or ""
        mai_think.sender = params.sender
        mai_think.target = params.target

        # 返回mai_think实例，以便后续使用
        return mai_think

    def _parse_reply_target_id(self, reply_to: str) -> str:
        """解析回复目标中的用户ID"""
        if not reply_to:
            return ""

        # 复用_parse_reply_target方法的逻辑
        sender, _ = self._parse_reply_target(reply_to)
        if not sender:
            return ""

        # 获取用户ID
        person_info_manager = get_person_info_manager()
        person_id = person_info_manager.get_person_id_by_person_name(sender)
        if person_id:
            user_id = person_info_manager.get_value_sync(person_id, "user_id")
            return str(user_id) if user_id else ""

    async def _build_expression_habits(self, params: SmartPromptParameters) -> Dict[str, Any]:
        """构建表达习惯 - 使用共享工具类，完全继承DefaultReplyer功能"""
        # 检查是否允许在此聊天流中使用表达
        use_expression, _, _ = global_config.expression.get_expression_config_for_chat(params.chat_id)
        if not use_expression:
            return {"expression_habits_block": ""}

        from src.chat.express.expression_selector import expression_selector

        style_habits = []
        grammar_habits = []

        # 使用从处理器传来的选中表达方式
        # LLM模式：调用LLM选择5-10个，然后随机选5个
        try:
            selected_expressions = await expression_selector.select_suitable_expressions_llm(
                params.chat_id, params.chat_talking_prompt_short, max_num=8, min_num=2, target_message=params.target
            )
        except Exception as e:
            logger.error(f"选择表达方式失败: {e}")
            selected_expressions = []

        if selected_expressions:
            logger.debug(f"使用处理器选中的{len(selected_expressions)}个表达方式")
            for expr in selected_expressions:
                if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                    expr_type = expr.get("type", "style")
                    if expr_type == "grammar":
                        grammar_habits.append(f"当{expr['situation']}时，使用 {expr['style']}")
                    else:
                        style_habits.append(f"当{expr['situation']}时，使用 {expr['style']}")
        else:
            logger.debug("没有从处理器获得表达方式，将使用空的表达方式")
            # 不再在replyer中进行随机选择，全部交给处理器处理

        style_habits_str = "\n".join(style_habits)
        grammar_habits_str = "\n".join(grammar_habits)

        # 动态构建expression habits块
        expression_habits_block = ""
        expression_habits_title = ""
        if style_habits_str.strip():
            expression_habits_title = (
                "你可以参考以下的语言习惯，当情景合适就使用，但不要生硬使用，以合理的方式结合到你的回复中："
            )
            expression_habits_block += f"{style_habits_str}\n"
        if grammar_habits_str.strip():
            expression_habits_title = (
                "你可以选择下面的句法进行回复，如果情景合适就使用，不要盲目使用,不要生硬使用，以合理的方式使用："
            )
            expression_habits_block += f"{grammar_habits_str}\n"

        if style_habits_str.strip() and grammar_habits_str.strip():
            expression_habits_title = "你可以参考以下的语言习惯和句法，如果情景合适就使用，不要盲目使用,不要生硬使用，以合理的方式结合到你的回复中。"

        return {"expression_habits_block": f"{expression_habits_title}\n{expression_habits_block}"}

    async def _build_memory_block(self, params: SmartPromptParameters) -> Dict[str, Any]:
        """构建记忆块 - 使用共享工具类，完全继承DefaultReplyer功能"""
        if not global_config.memory.enable_memory:
            return {"memory_block": ""}

        from src.chat.memory_system.memory_activator import MemoryActivator
        from src.chat.memory_system.vector_instant_memory import VectorInstantMemoryV2

        instant_memory = None

        # 初始化记忆激活器
        try:
            memory_activator = MemoryActivator()

            # 获取长期记忆
            running_memories = await memory_activator.activate_memory_with_chat_history(
                target_message=params.target, chat_history_prompt=params.chat_talking_prompt_short
            )
        except Exception as e:
            logger.error(f"激活记忆失败: {e}")
            running_memories = []

        # 处理瞬时记忆
        if global_config.memory.enable_instant_memory:
            # 使用异步记忆包装器（最优化的非阻塞模式）
            try:
                from src.chat.memory_system.async_instant_memory_wrapper import get_async_instant_memory

                # 获取异步记忆包装器
                async_memory = get_async_instant_memory(params.chat_id)

                # 后台存储聊天历史（完全非阻塞）
                async_memory.store_memory_background(params.chat_talking_prompt_short)

                # 快速检索记忆，最大超时2秒
                instant_memory = await async_memory.get_memory_with_fallback(params.target, max_timeout=2.0)

                logger.info(f"异步瞬时记忆：{instant_memory}")

            except ImportError:
                # 如果异步包装器不可用，尝试使用异步记忆管理器
                try:
                    from src.chat.memory_system.async_memory_optimizer import (
                        retrieve_memory_nonblocking,
                        store_memory_nonblocking,
                    )

                    # 异步存储聊天历史（非阻塞）
                    asyncio.create_task(
                        store_memory_nonblocking(chat_id=params.chat_id, content=params.chat_talking_prompt_short)
                    )

                    # 尝试从缓存获取瞬时记忆
                    instant_memory = await retrieve_memory_nonblocking(chat_id=params.chat_id, query=params.target)

                    # 如果没有缓存结果，快速检索一次
                    if instant_memory is None:
                        try:
                            # 使用VectorInstantMemoryV2实例
                            instant_memory_system = VectorInstantMemoryV2(chat_id=params.chat_id, retention_hours=1)
                            instant_memory = await asyncio.wait_for(
                                instant_memory_system.get_memory_for_context(params.target), timeout=1.5
                            )
                        except asyncio.TimeoutError:
                            logger.warning("瞬时记忆检索超时，使用空结果")
                            instant_memory = ""

                        logger.info(f"向量瞬时记忆：{instant_memory}")

                except ImportError:
                    # 最后的fallback：使用原有逻辑但加上超时控制
                    logger.warning("异步记忆系统不可用，使用带超时的同步方式")

                    # 使用VectorInstantMemoryV2实例
                    instant_memory_system = VectorInstantMemoryV2(chat_id=params.chat_id, retention_hours=1)

                    # 异步存储聊天历史
                    asyncio.create_task(instant_memory_system.store_message(params.chat_talking_prompt_short))

                    # 带超时的记忆检索
                    try:
                        instant_memory = await asyncio.wait_for(
                            instant_memory_system.get_memory_for_context(params.target),
                            timeout=1.0,  # 最保守的1秒超时
                        )
                    except asyncio.TimeoutError:
                        logger.warning("瞬时记忆检索超时，跳过记忆获取")
                        instant_memory = ""
                    except Exception as e:
                        logger.error(f"瞬时记忆检索失败: {e}")
                        instant_memory = ""

                    logger.info(f"同步瞬时记忆：{instant_memory}")

            except Exception as e:
                logger.error(f"瞬时记忆系统异常: {e}")
                instant_memory = ""

        # 构建记忆字符串，即使某种记忆为空也要继续
        memory_str = ""
        has_any_memory = False

        # 添加长期记忆
        if running_memories:
            if not memory_str:
                memory_str = "以下是当前在聊天中，你回忆起的记忆：\n"
            for running_memory in running_memories:
                memory_str += f"- {running_memory['content']}\n"
            has_any_memory = True

        # 添加瞬时记忆
        if instant_memory:
            if not memory_str:
                memory_str = "以下是当前在聊天中，你回忆起的记忆：\n"
            memory_str += f"- {instant_memory}\n"
            has_any_memory = True

        # 注入视频分析结果引导语
        memory_str = self._inject_video_prompt_if_needed(params.target, memory_str)

        # 只有当完全没有任何记忆时才返回空字符串
        return {"memory_block": memory_str if has_any_memory else ""}

    def _inject_video_prompt_if_needed(self, target: str, memory_str: str) -> str:
        """统一视频分析结果注入逻辑"""
        if target and ("[视频内容]" in target or "好的，我将根据您提供的" in target):
            video_prompt_injection = (
                "\n请注意，以上内容是你刚刚观看的视频，请以第一人称分享你的观后感，而不是在分析一份报告。"
            )
            return memory_str + video_prompt_injection
        return memory_str

    async def _build_relation_info(self, params: SmartPromptParameters) -> Dict[str, Any]:
        """构建关系信息 - 使用共享工具类"""
        try:
            relation_info = await PromptUtils.build_relation_info(params.chat_id, params.reply_to)
            return {"relation_info_block": relation_info}
        except Exception as e:
            logger.error(f"构建关系信息失败: {e}")
            return {"relation_info_block": ""}

    async def _build_tool_info(self, params: SmartPromptParameters) -> Dict[str, Any]:
        """构建工具信息 - 使用共享工具类，完全继承DefaultReplyer功能"""
        if not params.enable_tool:
            return {"tool_info_block": ""}

        if not params.reply_to:
            return {"tool_info_block": ""}

        sender, text = PromptUtils.parse_reply_target(params.reply_to)

        if not text:
            return {"tool_info_block": ""}

        from src.plugin_system.core.tool_use import ToolExecutor

        # 使用工具执行器获取信息
        try:
            tool_executor = ToolExecutor(chat_id=params.chat_id)
            tool_results, _, _ = await tool_executor.execute_from_chat_message(
                sender=sender, target_message=text, chat_history=params.chat_talking_prompt_short, return_details=False
            )

            if tool_results:
                tool_info_str = "以下是你通过工具获取到的实时信息：\n"
                for tool_result in tool_results:
                    tool_name = tool_result.get("tool_name", "unknown")
                    content = tool_result.get("content", "")
                    result_type = tool_result.get("type", "tool_result")

                    tool_info_str += f"- 【{tool_name}】{result_type}: {content}\n"

                tool_info_str += "以上是你获取到的实时信息，请在回复时参考这些信息。"
                logger.info(f"获取到 {len(tool_results)} 个工具结果")

                return {"tool_info_block": tool_info_str}
            else:
                logger.debug("未获取到任何工具结果")
                return {"tool_info_block": ""}

        except Exception as e:
            logger.error(f"工具信息获取失败: {e}")
            return {"tool_info_block": ""}

    async def _build_knowledge_info(self, params: SmartPromptParameters) -> Dict[str, Any]:
        """构建知识信息 - 使用共享工具类，完全继承DefaultReplyer功能"""
        if not params.reply_to:
            logger.debug("没有回复对象，跳过获取知识库内容")
            return {"knowledge_prompt": ""}

        sender, content = PromptUtils.parse_reply_target(params.reply_to)
        if not content:
            logger.debug("回复对象内容为空，跳过获取知识库内容")
            return {"knowledge_prompt": ""}

        logger.debug(
            f"获取知识库内容，元消息：{params.chat_talking_prompt_short[:30]}...，消息长度: {len(params.chat_talking_prompt_short)}"
        )

        # 从LPMM知识库获取知识
        try:
            # 检查LPMM知识库是否启用
            if not global_config.lpmm_knowledge.enable:
                logger.debug("LPMM知识库未启用，跳过获取知识库内容")
                return {"knowledge_prompt": ""}

            from src.plugins.built_in.knowledge.lpmm_get_knowledge import SearchKnowledgeFromLPMMTool
            from src.plugin_system.apis import llm_api
            from src.config.config import model_config

            time_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            bot_name = global_config.bot.nickname

            prompt = await global_prompt_manager.format_prompt(
                "lpmm_get_knowledge_prompt",
                bot_name=bot_name,
                time_now=time_now,
                chat_history=params.chat_talking_prompt_short,
                sender=sender,
                target_message=content,
            )

            _, _, _, _, tool_calls = await llm_api.generate_with_model_with_tools(
                prompt,
                model_config=model_config.model_task_config.tool_use,
                tool_options=[SearchKnowledgeFromLPMMTool.get_tool_definition()],
            )

            if tool_calls:
                from src.plugin_system.core.tool_use import ToolExecutor

                tool_executor = ToolExecutor(chat_id=params.chat_id)
                result = await tool_executor.execute_tool_call(tool_calls[0], SearchKnowledgeFromLPMMTool())

                if not result or not result.get("content"):
                    logger.debug("从LPMM知识库获取知识失败，返回空知识...")
                    return {"knowledge_prompt": ""}

                found_knowledge_from_lpmm = result.get("content", "")
                logger.debug(
                    f"从LPMM知识库获取知识，相关信息：{found_knowledge_from_lpmm[:100]}...，信息长度: {len(found_knowledge_from_lpmm)}"
                )

                return {
                    "knowledge_prompt": f"你有以下这些**知识**：\n{found_knowledge_from_lpmm}\n请你**记住上面的知识**，之后可能会用到。\n"
                }
            else:
                logger.debug("从LPMM知识库获取知识失败，可能是从未导入过知识，返回空知识...")
                return {"knowledge_prompt": ""}

        except Exception as e:
            logger.error(f"获取知识库内容时发生异常: {str(e)}")
            return {"knowledge_prompt": ""}

    async def _build_cross_context(self, params: SmartPromptParameters) -> Dict[str, Any]:
        """构建跨群上下文 - 使用共享工具类"""
        try:
            cross_context = await PromptUtils.build_cross_context(
                params.chat_id, params.prompt_mode, params.target_user_info
            )
            return {"cross_context_block": cross_context}
        except Exception as e:
            logger.error(f"构建跨群上下文失败: {e}")
            return {"cross_context_block": ""}

    def _parse_reply_target(self, target_message: str) -> Tuple[str, str]:
        """解析回复目标消息 - 使用共享工具类"""
        return PromptUtils.parse_reply_target(target_message)


class SmartPrompt:
    """重构的智能提示词核心类 - 移除缓存机制和依赖检查，简化架构"""

    def __init__(
        self,
        template_name: Optional[str] = None,
        parameters: Optional[SmartPromptParameters] = None,
    ):
        self.parameters = parameters or SmartPromptParameters()
        self.template_name = template_name or self._get_default_template()
        self.builder = SmartPromptBuilder()

    def _get_default_template(self) -> str:
        """根据模式选择默认模板"""
        if self.parameters.prompt_mode == "s4u":
            return "s4u_style_prompt"
        elif self.parameters.prompt_mode == "normal":
            return "normal_style_prompt"
        else:
            return "default_expressor_prompt"

    async def build_prompt(self) -> str:
        """构建最终的Prompt文本 - 移除缓存机制和依赖检查"""
        # 参数验证
        errors = self.parameters.validate()
        if errors:
            logger.error(f"参数验证失败: {', '.join(errors)}")
            raise ValueError(f"参数验证失败: {', '.join(errors)}")

        start_time = time.time()
        try:
            # 构建基础上下文的完整映射
            context_data = await self.builder.build_context_data(self.parameters)

            # 检查关键上下文数据
            if not context_data or not isinstance(context_data, dict):
                logger.error("构建的上下文数据无效")
                raise ValueError("构建的上下文数据无效")

            # 获取模板
            template = await self._get_template()
            if template is None:
                logger.error("无法获取模板")
                raise ValueError("无法获取模板")

            # 根据模式传递不同的参数
            if self.parameters.prompt_mode == "s4u":
                result = await self._build_s4u_prompt(template, context_data)
            elif self.parameters.prompt_mode == "normal":
                result = await self._build_normal_prompt(template, context_data)
            else:
                result = await self._build_default_prompt(template, context_data)

            # 记录性能数据
            total_time = time.time() - start_time
            logger.debug(f"SmartPrompt构建完成，模式: {self.parameters.prompt_mode}, 耗时: {total_time:.2f}s")

            return result

        except asyncio.TimeoutError as e:
            logger.error(f"构建Prompt超时: {e}")
            raise TimeoutError(f"构建Prompt超时: {e}")
        except Exception as e:
            logger.error(f"构建Prompt失败: {e}")
            raise RuntimeError(f"构建Prompt失败: {e}")

    async def _get_template(self) -> Optional[Prompt]:
        """获取模板"""
        try:
            return await global_prompt_manager.get_prompt_async(self.template_name)
        except Exception as e:
            logger.error(f"获取模板 {self.template_name} 失败: {e}")
            raise RuntimeError(f"获取模板 {self.template_name} 失败: {e}")

    async def _build_s4u_prompt(self, template: Prompt, context_data: Dict[str, Any]) -> str:
        """构建S4U模式的完整Prompt - 使用新参数结构"""
        params = {
            **context_data,
            "expression_habits_block": context_data.get("expression_habits_block", ""),
            "tool_info_block": context_data.get("tool_info_block", ""),
            "knowledge_prompt": context_data.get("knowledge_prompt", ""),
            "memory_block": context_data.get("memory_block", ""),
            "relation_info_block": context_data.get("relation_info_block", ""),
            "extra_info_block": self.parameters.extra_info_block or context_data.get("extra_info_block", ""),
            "cross_context_block": context_data.get("cross_context_block", ""),
            "identity": self.parameters.identity_block or context_data.get("identity", ""),
            "action_descriptions": self.parameters.action_descriptions or context_data.get("action_descriptions", ""),
            "sender_name": self.parameters.sender,
            "mood_state": self.parameters.mood_prompt or context_data.get("mood_state", ""),
            "background_dialogue_prompt": context_data.get("background_dialogue_prompt", ""),
            "time_block": context_data.get("time_block", ""),
            "core_dialogue_prompt": context_data.get("core_dialogue_prompt", ""),
            "reply_target_block": context_data.get("reply_target_block", ""),
            "reply_style": global_config.personality.reply_style,
            "keywords_reaction_prompt": self.parameters.keywords_reaction_prompt
            or context_data.get("keywords_reaction_prompt", ""),
            "moderation_prompt": self.parameters.moderation_prompt_block or context_data.get("moderation_prompt", ""),
        }
        return await global_prompt_manager.format_prompt(self.template_name, **params)

    async def _build_normal_prompt(self, template: Prompt, context_data: Dict[str, Any]) -> str:
        """构建Normal模式的完整Prompt - 使用新参数结构"""
        params = {
            **context_data,
            "expression_habits_block": context_data.get("expression_habits_block", ""),
            "tool_info_block": context_data.get("tool_info_block", ""),
            "knowledge_prompt": context_data.get("knowledge_prompt", ""),
            "memory_block": context_data.get("memory_block", ""),
            "relation_info_block": context_data.get("relation_info_block", ""),
            "extra_info_block": self.parameters.extra_info_block or context_data.get("extra_info_block", ""),
            "cross_context_block": context_data.get("cross_context_block", ""),
            "identity": self.parameters.identity_block or context_data.get("identity", ""),
            "action_descriptions": self.parameters.action_descriptions or context_data.get("action_descriptions", ""),
            "schedule_block": self.parameters.schedule_block or context_data.get("schedule_block", ""),
            "time_block": context_data.get("time_block", ""),
            "chat_info": context_data.get("chat_info", ""),
            "reply_target_block": context_data.get("reply_target_block", ""),
            "config_expression_style": global_config.personality.reply_style,
            "mood_state": self.parameters.mood_prompt or context_data.get("mood_state", ""),
            "keywords_reaction_prompt": self.parameters.keywords_reaction_prompt
            or context_data.get("keywords_reaction_prompt", ""),
            "moderation_prompt": self.parameters.moderation_prompt_block or context_data.get("moderation_prompt", ""),
        }
        return await global_prompt_manager.format_prompt(self.template_name, **params)

    async def _build_default_prompt(self, template: Prompt, context_data: Dict[str, Any]) -> str:
        """构建默认模式的Prompt - 使用新参数结构"""
        params = {
            "expression_habits_block": context_data.get("expression_habits_block", ""),
            "relation_info_block": context_data.get("relation_info_block", ""),
            "chat_target": "",
            "time_block": context_data.get("time_block", ""),
            "chat_info": context_data.get("chat_info", ""),
            "identity": self.parameters.identity_block or context_data.get("identity", ""),
            "chat_target_2": "",
            "reply_target_block": context_data.get("reply_target_block", ""),
            "raw_reply": self.parameters.target,
            "reason": "",
            "mood_state": self.parameters.mood_prompt or context_data.get("mood_state", ""),
            "reply_style": global_config.personality.reply_style,
            "keywords_reaction_prompt": self.parameters.keywords_reaction_prompt
            or context_data.get("keywords_reaction_prompt", ""),
            "moderation_prompt": self.parameters.moderation_prompt_block or context_data.get("moderation_prompt", ""),
        }
        return await global_prompt_manager.format_prompt(self.template_name, **params)


# 工厂函数 - 简化创建 - 更新参数结构
def create_smart_prompt(
    chat_id: str = "", sender_name: str = "", target_message: str = "", reply_to: str = "", **kwargs
) -> SmartPrompt:
    """快速创建智能Prompt实例的工厂函数 - 使用新参数结构"""

    # 使用新的参数结构
    parameters = SmartPromptParameters(
        chat_id=chat_id, sender=sender_name, target=target_message, reply_to=reply_to, **kwargs
    )

    return SmartPrompt(parameters=parameters)


class SmartPromptHealthChecker:
    """SmartPrompt健康检查器 - 移除依赖检查"""

    @staticmethod
    async def check_system_health() -> Dict[str, Any]:
        """检查系统健康状态 - 移除依赖检查"""
        health_status = {"status": "healthy", "components": {}, "issues": []}

        try:
            # 检查配置
            try:
                from src.config.config import global_config

                health_status["components"]["config"] = "ok"

                # 检查关键配置项
                if not hasattr(global_config, "personality") or not hasattr(global_config.personality, "prompt_mode"):
                    health_status["issues"].append("缺少personality.prompt_mode配置")
                    health_status["status"] = "degraded"

                if not hasattr(global_config, "memory") or not hasattr(global_config.memory, "enable_memory"):
                    health_status["issues"].append("缺少memory.enable_memory配置")

            except Exception as e:
                health_status["components"]["config"] = f"failed: {str(e)}"
                health_status["issues"].append("配置加载失败")
                health_status["status"] = "unhealthy"

            # 检查Prompt模板
            try:
                required_templates = ["s4u_style_prompt", "normal_style_prompt", "default_expressor_prompt"]
                for template_name in required_templates:
                    try:
                        await global_prompt_manager.get_prompt_async(template_name)
                        health_status["components"][f"template_{template_name}"] = "ok"
                    except Exception as e:
                        health_status["components"][f"template_{template_name}"] = f"failed: {str(e)}"
                        health_status["issues"].append(f"模板{template_name}加载失败")
                        health_status["status"] = "degraded"

            except Exception as e:
                health_status["components"]["prompt_templates"] = f"failed: {str(e)}"
                health_status["issues"].append("Prompt模板检查失败")
                health_status["status"] = "unhealthy"

            return health_status

        except Exception as e:
            return {"status": "unhealthy", "components": {}, "issues": [f"健康检查异常: {str(e)}"]}

    @staticmethod
    async def run_performance_test() -> Dict[str, Any]:
        """运行性能测试"""
        test_results = {"status": "completed", "tests": {}, "summary": {}}

        try:
            # 创建测试参数
            test_params = SmartPromptParameters(
                chat_id="test_chat",
                sender="test_user",
                target="test_message",
                reply_to="test_user:test_message",
                prompt_mode="s4u",
            )

            # 测试不同模式下的构建性能
            modes = ["s4u", "normal", "minimal"]
            for mode in modes:
                test_params.prompt_mode = mode
                smart_prompt = SmartPrompt(parameters=test_params)

                # 运行多次测试取平均值
                times = []
                for _ in range(3):
                    start_time = time.time()
                    try:
                        await smart_prompt.build_prompt()
                        end_time = time.time()
                        times.append(end_time - start_time)
                    except Exception as e:
                        times.append(float("inf"))
                        logger.error(f"性能测试失败 (模式: {mode}): {e}")

                # 计算统计信息
                valid_times = [t for t in times if t != float("inf")]
                if valid_times:
                    avg_time = sum(valid_times) / len(valid_times)
                    min_time = min(valid_times)
                    max_time = max(valid_times)

                    test_results["tests"][mode] = {
                        "avg_time": avg_time,
                        "min_time": min_time,
                        "max_time": max_time,
                        "success_rate": len(valid_times) / len(times),
                    }
                else:
                    test_results["tests"][mode] = {
                        "avg_time": float("inf"),
                        "min_time": float("inf"),
                        "max_time": float("inf"),
                        "success_rate": 0,
                    }

            # 计算总体统计
            all_avg_times = [
                test["avg_time"] for test in test_results["tests"].values() if test["avg_time"] != float("inf")
            ]
            if all_avg_times:
                test_results["summary"] = {
                    "overall_avg_time": sum(all_avg_times) / len(all_avg_times),
                    "fastest_mode": min(test_results["tests"].items(), key=lambda x: x[1]["avg_time"])[0],
                    "slowest_mode": max(test_results["tests"].items(), key=lambda x: x[1]["avg_time"])[0],
                }

            return test_results

        except Exception as e:
            return {"status": "failed", "tests": {}, "summary": {}, "error": str(e)}
