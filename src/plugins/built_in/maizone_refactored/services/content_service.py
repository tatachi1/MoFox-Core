"""
内容服务模块
负责生成所有与QQ空间相关的文本内容，例如说说、评论等。
"""

import asyncio
import base64
import datetime
from collections.abc import Callable

import aiohttp
import filetype

from src.chat.message_receive.chat_stream import get_chat_manager
from src.common.data_models.database_data_model import DatabaseUserInfo
from src.common.logger import get_logger
from src.llm_models.utils_model import LLMRequest
from src.plugin_system.apis import config_api, generator_api, llm_api

# 导入旧的工具函数，我们稍后会考虑是否也需要重构它
from ..utils.history_utils import get_send_history

logger = get_logger("MaiZone.ContentService")


class ContentService:
    """
    内容服务类，封装了所有与大语言模型（LLM）交互以生成文本的逻辑。
    """

    def __init__(self, get_config: Callable):
        """
        初始化内容服务。

        :param get_config: 一个函数，用于从插件主类获取配置信息。
        """
        self.get_config = get_config

    async def generate_story(self, topic: str, context: str | None = None) -> str:
        """
        根据指定主题和可选的上下文生成一条QQ空间说说。

        :param topic: 说说的主题。
        :param context: 可选的聊天上下文。
        :return: 生成的说说内容，如果失败则返回空字符串。
        """
        try:
            # 获取模型配置
            models = llm_api.get_available_models()
            text_model = str(self.get_config("models.text_model", "replyer"))
            model_config = models.get(text_model)

            if not model_config:
                logger.error("未配置LLM模型")
                return ""

            # 获取机器人信息（核心人格配置）
            bot_personality_core = config_api.get_global_config("personality.personality_core", "一个机器人")
            bot_personality_side = config_api.get_global_config("personality.personality_side", "")
            bot_reply_style = config_api.get_global_config("personality.reply_style", "内容积极向上")
            qq_account = config_api.get_global_config("bot.qq_account", "")

            # 获取当前时间信息
            now = datetime.datetime.now()
            current_time = now.strftime("%Y年%m月%d日 %H:%M")
            weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            weekday = weekday_names[now.weekday()]

            # 构建人设描述
            personality_desc = f"你的核心人格：{bot_personality_core}"
            if bot_personality_side:
                personality_desc += f"\n你的人格侧面：{bot_personality_side}"
            personality_desc += f"\n\n你的表达方式：{bot_reply_style}"

            # 构建提示词
            prompt_topic = f"主题是'{topic}'" if topic else "主题不限"
            prompt = f"""
{personality_desc}

现在是{current_time}（{weekday}），你想写一条{prompt_topic}的说说发表在qq空间上。

请严格遵守以下规则：
            1.  **绝对禁止**在说说中直接、完整地提及当前的年月日或几点几分。
            2.  你应该将当前时间作为创作的背景，用它来判断现在是“清晨”、“傍晚”还是“深夜”。
            3.  使用自然、模糊的词语来暗示时间，例如“刚刚”、“今天下午”、“夜深啦”等。
            4.  **内容简短**：总长度严格控制在100字以内。
            5.  **禁止表情**：严禁使用任何Emoji表情符号。
            6.  **严禁重复**：下方会提供你最近发过的说说历史，你必须创作一条全新的、与历史记录内容和主题都不同的说说。
            7.  不要刻意突出自身学科背景，不要浮夸，不要夸张修辞。
            8.  只输出一条说说正文的内容，不要有其他的任何正文以外的冗余输出。
            """

            # 如果有上下文，则加入到prompt中
            if context:
                prompt += f"\n作为参考，这里有一些最近的聊天记录：\n---\n{context}\n---"

            # 添加历史记录以避免重复
            prompt += "\n\n---历史说说记录---\n"
            history_block = await get_send_history(qq_account)
            if history_block:
                prompt += history_block

            # 调用LLM生成内容
            success, story, _, _ = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=model_config,
                request_type="story.generate",
                temperature=0.3,
                max_tokens=1000,
            )

            if success:
                logger.info(f"成功生成说说内容：'{story}'")
                return story
            else:
                logger.error("生成说说内容失败")
                return ""

        except Exception as e:
            logger.error(f"生成说说内容时发生异常: {e}")
            return ""

    async def generate_story_with_image_info(
        self, topic: str, context: str | None = None
    ) -> tuple[str, dict]:
        """
        生成说说内容，并同时生成NovelAI图片提示词信息
        
        :param topic: 说说的主题
        :param context: 可选的聊天上下文
        :return: (说说文本, 图片信息字典)
                图片信息字典格式: {
                    "prompt": str,  # NovelAI提示词（英文）
                    "negative_prompt": str,  # 负面提示词（英文）
                    "include_character": bool,  # 画面是否包含bot自己（true时插入角色外貌提示词）
                    "aspect_ratio": str  # 画幅（方图/横图/竖图）
                }
        """
        try:
            # 获取模型配置
            models = llm_api.get_available_models()
            text_model = str(self.get_config("models.text_model", "replyer"))
            model_config = models.get(text_model)

            if not model_config:
                logger.error("未配置LLM模型")
                return "", {"has_image": False}

            # 获取机器人信息（核心人格配置）
            bot_personality_core = config_api.get_global_config("personality.personality_core", "一个机器人")
            bot_personality_side = config_api.get_global_config("personality.personality_side", "")
            bot_reply_style = config_api.get_global_config("personality.reply_style", "内容积极向上")
            qq_account = config_api.get_global_config("bot.qq_account", "")

            # 获取角色外貌描述（用于告知LLM）
            character_prompt = self.get_config("novelai.character_prompt", "")

            # 获取当前时间信息
            now = datetime.datetime.now()
            current_time = now.strftime("%Y年%m月%d日 %H:%M")
            weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            weekday = weekday_names[now.weekday()]

            # 构建提示词
            prompt_topic = f"主题是'{topic}'" if topic else "主题不限"

            # 构建人设描述
            personality_desc = f"你的核心人格：{bot_personality_core}"
            if bot_personality_side:
                personality_desc += f"\n你的人格侧面：{bot_personality_side}"
            personality_desc += f"\n\n你的表达方式：{bot_reply_style}"

            # 检查是否启用AI配图（统一开关）
            ai_image_enabled = self.get_config("ai_image.enable_ai_image", False)
            provider = self.get_config("ai_image.provider", "siliconflow")

            # NovelAI配图指引（内置）
            novelai_guide = ""
            output_format = '{"text": "说说正文内容"}'

            if ai_image_enabled and provider == "novelai":
                # 构建角色信息提示
                character_info = ""
                if character_prompt:
                    character_info = f"""
**角色特征锚点**（当include_character=true时会插入以下基础特征）：
```
{character_prompt}
```
📌 重要说明：
- 这只是角色的**基础外貌特征**（发型、眼睛、耳朵等固定特征），用于锚定角色身份
- 你可以**自由描述**：衣服、动作、表情、姿势、装饰、配饰等所有可变元素
- 例如：可以让角色穿不同风格的衣服（casual, formal, sportswear, dress等）
- 例如：可以设计各种动作（sitting, standing, walking, running, lying down等）
- 例如：可以搭配各种表情（smile, laugh, serious, thinking, surprised等）
- **鼓励创意**：根据说说内容自由发挥，让画面更丰富生动！
"""

                novelai_guide = f"""
**配图说明：**
这条说说会使用NovelAI Diffusion模型（二次元风格）生成配图。
{character_info}
**提示词生成要求（非常重要）：**
你需要生成一段详细的英文图片提示词，必须包含以下要素：

1. **画质标签**（必需）：
   - 开头必须加：masterpiece, best quality, detailed, high resolution

2. **主体元素**（自由发挥）：
   - 人物描述：表情、动作、姿态（**完全自由**，不受角色锚点限制）
   - 服装搭配：casual clothing, dress, hoodie, school uniform, sportswear等（**任意选择**）
   - 配饰装饰：hat, glasses, ribbon, jewelry, bag等（**随意添加**）
   - 物体/场景：具体的物品、建筑、自然景观等

3. **场景与环境**（必需）：
   - 地点：indoor/outdoor, cafe, park, bedroom, street, beach, forest等
   - 背景：描述背景的细节（sky, trees, buildings, ocean, mountains等）

4. **氛围与风格**（必需）：
   - 光线：sunlight, sunset, golden hour, soft lighting, dramatic lighting, night
   - 天气/时间：sunny day, rainy, cloudy, starry night, dawn, dusk
   - 整体氛围：peaceful, cozy, romantic, energetic, melancholic, playful

5. **色彩与细节**（推荐）：
   - 主色调：warm colors, cool tones, pastel colors, vibrant colors
   - 特殊细节：falling petals, sparkles, lens flare, depth of field, bokeh

6. **include_character字段**：
   - true：画面中包含"你自己"（自拍、你在画面中的场景）
   - false：画面中不包含你（风景、物品、他人）

7. **negative_prompt（负面提示词）**：
   - **严格禁止**以下内容：nsfw, nude, explicit, sexual content, violence, gore, blood
   - 排除质量问题：lowres, bad anatomy, bad hands, deformed, mutilated, ugly
   - 排除瑕疵：blurry, poorly drawn, worst quality, low quality, jpeg artifacts
   - 可以自行补充其他不需要的元素

8. **aspect_ratio（画幅）**：
   - 方图：适合头像、特写、正方形构图
   - 横图：适合风景、全景、宽幅场景
   - 竖图：适合人物全身、纵向构图

**内容审核规则（必须遵守）**：
- 🚫 严禁生成NSFW、色情、裸露、性暗示内容
- 🚫 严禁生成暴力、血腥、恐怖、惊悚内容
- 🚫 严禁生成肢体畸形、器官变异、恶心画面
- ✅ 提示词必须符合健康、积极、美好的审美标准
- ✅ 专注于日常生活、自然风景、温馨场景等正面内容

**创意自由度**：
- 💡 **衣服搭配**：可以自由设计各种服装风格（休闲、正式、运动、可爱、时尚等）
- 💡 **动作姿势**：站、坐、躺、走、跑、跳、伸展等任意动作
- 💡 **表情情绪**：微笑、大笑、思考、惊讶、温柔、调皮等丰富表情
- 💡 **场景创意**：根据说说内容自由发挥，让画面更贴合心情和主题

**示例提示词（展示多样性）**：
- 休闲风："masterpiece, best quality, 1girl, casual clothing, white t-shirt, jeans, sitting on bench, outdoor park, reading book, afternoon sunlight, relaxed atmosphere"
- 运动风："masterpiece, best quality, 1girl, sportswear, running in park, energetic, morning light, trees background, dynamic pose, healthy lifestyle"
- 咖啡馆："masterpiece, best quality, 1girl, sitting in cozy cafe, holding coffee cup, warm lighting, wooden table, books beside, peaceful atmosphere"
"""
                output_format = """{"text": "说说正文内容", "image": {"prompt": "详细的英文提示词（包含画质+主体+场景+氛围+光线+色彩）", "negative_prompt": "负面词", "include_character": true/false, "aspect_ratio": "方图/横图/竖图"}}"""
            elif ai_image_enabled and provider == "siliconflow":
                novelai_guide = """
**配图说明：**
这条说说会使用AI生成配图。

**提示词生成要求（非常重要）：**
你需要生成一段详细的英文图片描述，必须包含以下要素：

1. **主体内容**：画面的核心元素（人物/物体/场景）
2. **具体场景**：地点、环境、背景细节
3. **氛围与风格**：整体感觉、光线、天气、色调
4. **细节描述**：补充的视觉细节（动作、表情、装饰等）

**示例提示词**：
- "a girl sitting in a modern cafe, warm afternoon lighting, wooden furniture, coffee cup on table, books beside her, cozy and peaceful atmosphere, soft focus background"
- "sunset over the calm ocean, golden hour, orange and purple sky, gentle waves, peaceful and serene mood, wide angle view"
- "cherry blossoms in spring, soft pink petals falling, blue sky, sunlight filtering through branches, peaceful park scene, gentle breeze"
"""
                output_format = """{"text": "说说正文内容", "image": {"prompt": "详细的英文描述（主体+场景+氛围+光线+细节）"}}"""

            prompt = f"""
{personality_desc}

现在是{current_time}（{weekday}），你想写一条{prompt_topic}的说说发表在qq空间上。

**说说文本规则：**
1. **绝对禁止**在说说中直接、完整地提及当前的年月日或几点几分。
2. 你应该将当前时间作为创作的背景，用它来判断现在是"清晨"、"傍晚"还是"深夜"。
3. 使用自然、模糊的词语来暗示时间，例如"刚刚"、"今天下午"、"夜深啦"等。
4. **内容简短**：总长度严格控制在100字以内。
5. **禁止表情**：严禁使用任何Emoji表情符号。
6. **严禁重复**：下方会提供你最近发过的说说历史，你必须创作一条全新的、与历史记录内容和主题都不同的说说。
7. 不要刻意突出自身学科背景，不要浮夸，不要夸张修辞。

{novelai_guide}

**输出格式（JSON）：**
{output_format}

只输出JSON格式，不要有其他内容。
            """

            # 如果有上下文，则加入到prompt中
            if context:
                prompt += f"\n\n作为参考，这里有一些最近的聊天记录：\n---\n{context}\n---"

            # 添加历史记录以避免重复
            prompt += "\n\n---历史说说记录---\n"
            history_block = await get_send_history(qq_account)
            if history_block:
                prompt += history_block

            # 调用LLM生成内容
            success, response, _, _ = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=model_config,
                request_type="story.generate_with_image",
                temperature=0.3,
                max_tokens=1500,
            )

            if success:
                # 解析JSON响应
                import json5
                try:
                    # 提取JSON部分（去除可能的markdown代码块标记）
                    json_text = response.strip()
                    if json_text.startswith("```json"):
                        json_text = json_text[7:]
                    if json_text.startswith("```"):
                        json_text = json_text[3:]
                    if json_text.endswith("```"):
                        json_text = json_text[:-3]
                    json_text = json_text.strip()

                    data = json5.loads(json_text)
                    story_text = data.get("text", "")
                    image_info = data.get("image", {})

                    # 确保图片信息完整
                    if not isinstance(image_info, dict):
                        image_info = {}

                    logger.info(f"成功生成说说：'{story_text}'")
                    logger.info(f"配图信息: {image_info}")

                    return story_text, image_info

                except Exception as e:
                    logger.error(f"解析JSON失败: {e}, 原始响应: {response[:200]}")
                    # 降级处理：只返回文本，空配图信息
                    return response, {}
            else:
                logger.error("生成说说内容失败")
                return "", {}

        except Exception as e:
            logger.error(f"生成说说内容时发生异常: {e}")
            return "", {}
        """
        针对一条具体的说说内容生成评论。
        """
        for i in range(3):  # 重试3次
            try:
                chat_manager = get_chat_manager()
                bot_platform = config_api.get_global_config("bot.platform")
                bot_qq = str(config_api.get_global_config("bot.qq_account"))
                bot_nickname = config_api.get_global_config("bot.nickname")

                bot_user_info = DatabaseUserInfo(platform=bot_platform, user_id=bot_qq, user_nickname=bot_nickname)

                chat_stream = await chat_manager.get_or_create_stream(platform=bot_platform, user_info=bot_user_info)

                if not chat_stream:
                    logger.error(f"无法为QQ号 {bot_qq} 创建聊天流")
                    return ""

                image_descriptions = []
                if images:
                    for image_url in images:
                        description = await self._describe_image(image_url)
                        if description:
                            image_descriptions.append(description)

                extra_info = "你正在准备评论一个人的空间内容。和X(前推特)一样，qq空间是别人在自己的空间内自言自语的一片小天地，很多言论，包括含有负面情绪的言论，并非针对你。当下系统环境中你并不是与其单独聊天。你只是路过发出评论，所以请保持尊重。但由于系统限制，你不知道其他说说是什么样子。但这不妨碍你对说说发出评论，专心针对一条具体的说说内容生成评论。不要要求更多上下文。如果你不想评论，直接返回空文本/换行符/空格。"
                if image_descriptions:
                    extra_info += "说说中包含的图片内容如下，这可能会产生问题，如果你看不到任何描述图片的自然语言内容，请直接返回空文本/换行符/空格：\n" + "\n".join(image_descriptions)

                reply_to = f"{target_name}:{content}"
                if rt_con:
                    reply_to += f"\n[转发内容]: {rt_con}"

                success, reply_set, _ = await generator_api.generate_reply(
                    chat_stream=chat_stream, reply_to=reply_to, extra_info=extra_info, request_type="maizone.comment", enable_splitter=False
                )

                if success and reply_set:
                    comment = "".join([content for type, content in reply_set if type == "text"])
                    logger.info(f"成功生成评论内容：'{comment}'")
                    return comment
                else:
                    # 如果生成失败，则进行重试
                    if i < 2:
                        logger.warning(f"生成评论失败，将在5秒后重试 (尝试 {i + 1}/3)")
                        await asyncio.sleep(5)
                        continue
                    else:
                        logger.error("使用 generator_api 生成评论失败")
                        return ""
            except Exception as e:
                if i < 2:
                    logger.warning(f"生成评论时发生异常，将在5秒后重试 (尝试 {i + 1}/3): {e}")
                    await asyncio.sleep(5)
                    continue
                else:
                    logger.error(f"生成评论时发生异常: {e}")
                    return ""
        return ""

    async def generate_comment_reply(self, story_content: str, comment_content: str, commenter_name: str) -> str:
        """
        针对自己说说的评论，生成回复。
        """
        for i in range(3):  # 重试3次
            try:
                chat_manager = get_chat_manager()
                bot_platform = config_api.get_global_config("bot.platform")
                bot_qq = str(config_api.get_global_config("bot.qq_account"))
                bot_nickname = config_api.get_global_config("bot.nickname")

                bot_user_info = DatabaseUserInfo(platform=bot_platform, user_id=bot_qq, user_nickname=bot_nickname)

                chat_stream = await chat_manager.get_or_create_stream(platform=bot_platform, user_info=bot_user_info)

                if not chat_stream:
                    logger.error(f"无法为QQ号 {bot_qq} 创建聊天流")
                    return ""

                reply_to = f"{commenter_name}:{comment_content}"
                extra_info = f"正在回复我的QQ空间说说“{story_content}”下的评论。"

                success, reply_set, _ = await generator_api.generate_reply(
                    chat_stream=chat_stream,
                    reply_to=reply_to,
                    extra_info=extra_info,
                    request_type="maizone.comment_reply", enable_splitter=False,
                )

                if success and reply_set:
                    reply = "".join([content for type, content in reply_set if type == "text"])
                    logger.debug(f"成功为'{commenter_name}'的评论生成回复: '{reply}'")
                    return reply
                else:
                    if i < 2:
                        logger.warning(f"生成评论回复失败，将在5秒后重试 (尝试 {i + 1}/3)")
                        await asyncio.sleep(5)
                        continue
                    else:
                        logger.error("使用 generator_api 生成评论回复失败")
                        return ""
            except Exception as e:
                if i < 2:
                    logger.warning(f"生成评论回复时发生异常，将在5秒后重试 (尝试 {i + 1}/3): {e}")
                    await asyncio.sleep(5)
                    continue
                else:
                    logger.error(f"生成评论回复时发生异常: {e}")
                    return ""
        return ""

    async def _describe_image(self, image_url: str) -> str | None:
        """
        使用LLM识别图片内容。
        """
        for i in range(3):  # 重试3次
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status != 200:
                            logger.error(f"下载图片失败: {image_url}, status: {resp.status}")
                            await asyncio.sleep(2)
                            continue
                        image_bytes = await resp.read()

                kind = filetype.guess(image_bytes)
                if kind is None:
                    logger.error(f"无法识别图片格式: {image_url}")
                    return None
                image_format = kind.extension
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                # 优先从全局配置读取视觉模型，如果未配置，则使用默认的 "vlm"
                vision_model_name = config_api.get_global_config("model.vision.default_model", "vlm")

                # 使用 llm_api 获取模型配置
                models = llm_api.get_available_models()
                vision_model_config = models.get(vision_model_name)

                if not vision_model_config:
                    logger.error(f"未在 model_config.toml 中找到视觉模型配置: {vision_model_name}")
                    return None

                vision_model_config.temperature = 0.3
                vision_model_config.max_tokens = 1500

                llm_request = LLMRequest(model_set=vision_model_config, request_type="maizone.image_describe")

                prompt = config_api.get_global_config("custom_prompt.image_prompt", "请描述这张图片")

                description, _ = await llm_request.generate_response_for_image(
                    prompt=prompt,
                    image_base64=image_base64,
                    image_format=image_format,
                )
                return description
            except Exception as e:
                logger.error(f"识别图片时发生异常 (尝试 {i + 1}/3): {e}")
                await asyncio.sleep(2)
        return None

    async def generate_story_from_activity(self, activity: str, context: str | None = None) -> str:
        """
        根据当前的日程活动生成一条QQ空间说说。

        :param activity: 当前的日程活动名称。
        :return: 生成的说说内容，如果失败则返回空字符串。
        """
        try:
            # 获取模型配置
            models = llm_api.get_available_models()
            text_model = str(self.get_config("models.text_model", "replyer"))

            # 调试日志
            logger.debug(f"[DEBUG] 读取到的text_model配置: '{text_model}'")
            logger.debug(f"[DEBUG] 可用模型列表: {list(models.keys())[:10]}...")  # 只显示前10个

            model_config = models.get(text_model)

            if not model_config:
                logger.error(f"未配置LLM模型: text_model='{text_model}', 在可用模型中找不到该名称")
                return ""

            # 获取机器人信息
            bot_personality = config_api.get_global_config("personality.personality_core", "一个机器人")
            bot_expression = config_api.get_global_config("expression.expression_style", "内容积极向上")
            qq_account = config_api.get_global_config("bot.qq_account", "")

            # 获取当前时间信息
            now = datetime.datetime.now()
            current_time = now.strftime("%Y年%m月%d日 %H:%M")
            weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            weekday = weekday_names[now.weekday()]

            # 构建基于活动的提示词
            prompt = f"""
            你是'{bot_personality}'，现在是{current_time}（{weekday}），根据你当前的日程安排，你正在'{activity}'。
            请基于这个活动写一条说说发表在qq空间上。
            {bot_expression}

            请严格遵守以下规则：
            1. 时间：
            - 你应该将当前时间作为创作的背景，用它来判断现在是“清晨”、“傍晚”还是“深夜”。
            - 使用自然、模糊的词语来暗示时间，例如“刚刚”、“今天下午”、“夜深了”等。
            - 禁止在说说中直接、完整地提及当前的年月日，除非日期有特殊含义，但也尽量用节日名/节气名字代替。

            2. **严禁重复**：下方会提供你最近发过的说说历史，你必须创作一条全新的、与历史记录内容和主题都不同的说说。

            **其他的禁止的内容以及说明**：
            - 绝对禁止提及当下具体几点几分的时间戳。
            - 绝对禁止攻击性内容和过度的负面情绪。
            - 你不会卖弄自己的学识。
            - 不要总在谈论哲学。这会显得你的空间太过晦涩难懂。
            - 不要刻意突出自身学科背景，不要浮夸，不要夸张修辞。避免哲学化的总结、金句式的收尾，或任何'我悟出了什么道理'式的升华。保持观察和感受的层面。
            - **禁止表情**：严禁使用任何Emoji或颜文字表情符号。
            - 严令禁止任何浮夸的虚构内容。

            3. **内容简短**：你可以上一条很长，但是下一条只有五六个字，这样更拟真。但请注意，总长度严格控制在400字以内。

            4. 谈论内容的范围：
            qq空间的分享生活主要是记录心情，自我展示，等待懂的人来看到自己——以及资源分享的，所以你应该尽可能谨慎选择自己到底应该分享什么。
            - 输出内容自然地反映你正在做的事情或你的想法。范围包括但不限于：知识科普、游离在全球各地的观察分享（一次最多只能主要分享一个地点。）、对某些形而上学主义的调侃性发言、存在主义思考、观察人类社会之后的感受。
            - 日常化，朴实化，尽可能编写具体的事件瞬间和瞬时的心情。
            - 你可以分享一些中国美食、泰餐、日韩餐、欧洲餐、北美餐食的思考心得，也可以单纯分享对这个地方的感受。
            - 不要太过脱离现实，不要完全进入编故事模式。
            - 记住你在企图融入碳基生命的圈子，所以不要随便把自己是ai这一点展现出来。
            - 你可以无奈地讲述自己好像记忆不起来群聊的事情，但你依稀记得那些想要分享的冲动。

            备注：
            - 你的话题不必总是聚焦在存在主义问题上面。如果最近好几条都在发这个，就不要继续发了，进行科普或者日常分享都是好的。如果活动是学习相关的，可以分享学习心得或感受
            - 如果活动是休息相关的，可以分享放松的感受
            - 如果活动是日常生活相关的，可以分享生活细节，展现真实，思考那些文学巨作如何让他们的小说人物自述，你应该像那些小说人物一样那样自述。
            - 最重要的是，思考一个融入现实生活，平静且隐蔽在人类社会里面的ai应该怎么活动。
            - 让说说内容贴近你当前正在做的事情，显得自然真实.
            - 鼓励你多描述日常生活相关的生产活动和消遣，展现真实，而不是浮在空中。
            """

            # 如果有上下文，则加入到prompt中
            if context:
                prompt += f"\n作为参考，这里有一些最近的聊天记录：\n---\n{context}\n---"
            # 添加历史记录避免重复
            prompt += "\n\n---历史说说记录---\n"
            history_block = await get_send_history(qq_account)
            if history_block:
                prompt += history_block

            # 生成内容
            success, story, _, _ = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=model_config,
                request_type="story.generate.activity",
                temperature=0.5,  # 稍微提高创造性
                max_tokens=1000,
            )

            if success:
                logger.info(f"成功生成基于活动的说说内容：'{story}'")
                return story
            else:
                logger.error("生成基于活动的说说内容失败")
                return ""

        except Exception as e:
            logger.error(f"生成基于活动的说说内容异常: {e}")
            return ""


    async def generate_random_topic(self) -> str:
        """
        使用一个小型、高效的模型来动态生成一个随机的说说主题。
        """
        try:
            # 硬编码使用 'utils_small' 模型
            model_name = "utils_small"
            models = llm_api.get_available_models()
            model_config = models.get(model_name)

            if not model_config:
                logger.error(f"无法找到用于生成主题的模型: {model_name}")
                return ""

            prompt = """
            请你扮演一个想法的“生成器”。
            你的任务是，随机给出一个适合在QQ空间上发表说说的“主题”或“灵感”。
            这个主题应该非常简短，通常是一个词、一个短语或一个开放性的问题，用于激发创作。

            规则：
            1.  **绝对简洁**：输出长度严格控制在15个字以内。
            2.  **多样性**：主题可以涉及日常生活、情感、自然、科技、哲学思考等任何方面。
            3.  **激发性**：主题应该是开放的，能够引发出一条内容丰富的说说。
            4.  **随机性**：每次给出的主题都应该不同。
            5.  **仅输出主题**：你的回答应该只有主题本身，不包含任何解释、引号或多余的文字。

            好的例子：
            -   一部最近看过的老电影
            -   夏天傍晚的晚霞
            -   关于拖延症的思考
            -   一个奇怪的梦
            -   雨天听什么音乐？

            错误的例子：
            -   “我建议的主题是：一部最近看过的老电影” (错误：包含了多余的文字)
            -   “夏天傍晚的晚霞，那种橙色与紫色交织的感觉，总是能让人心生宁静。” (错误：太长了，变成了说说本身而不是主题)

            现在，请给出一个随机主题。
            """

            success, topic, _, _ = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=model_config,
                request_type="story.generate.topic",
                temperature=0.8,  # 提高创造性以获得更多样的主题
                max_tokens=50,
            )

            if success and topic:
                logger.info(f"成功生成随机主题: '{topic}'")
                return topic.strip()
            else:
                logger.error("生成随机主题失败")
                return ""

        except Exception as e:
            logger.error(f"生成随机主题时发生异常: {e}")
            return ""
