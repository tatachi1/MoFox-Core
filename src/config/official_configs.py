from typing import Literal, Optional, List
from pydantic import Field

from src.config.config_base import ValidatedConfigBase

"""
须知：
1. 本文件中记录了所有的配置项
2. 重要的配置类继承自ValidatedConfigBase进行Pydantic验证
3. 所有新增的class都应在config.py中的Config类中添加字段
4. 对于新增的字段，若为可选项，则应在其后添加field()并设置default_factory或default
"""



class DatabaseConfig(ValidatedConfigBase):
    """数据库配置类"""

    database_type: Literal["sqlite", "mysql"] = Field(default="sqlite", description="数据库类型")
    sqlite_path: str = Field(default="data/MaiBot.db", description="SQLite数据库文件路径")
    mysql_host: str = Field(default="localhost", description="MySQL服务器地址")
    mysql_port: int = Field(default=3306, ge=1, le=65535, description="MySQL服务器端口")
    mysql_database: str = Field(default="maibot", description="MySQL数据库名")
    mysql_user: str = Field(default="root", description="MySQL用户名")
    mysql_password: str = Field(default="", description="MySQL密码")
    mysql_charset: str = Field(default="utf8mb4", description="MySQL字符集")
    mysql_unix_socket: str = Field(default="", description="MySQL Unix套接字路径")
    mysql_ssl_mode: Literal["DISABLED", "PREFERRED", "REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY"] = Field(default="DISABLED", description="SSL模式")
    mysql_ssl_ca: str = Field(default="", description="SSL CA证书路径")
    mysql_ssl_cert: str = Field(default="", description="SSL客户端证书路径")
    mysql_ssl_key: str = Field(default="", description="SSL客户端密钥路径")
    mysql_autocommit: bool = Field(default=True, description="自动提交事务")
    mysql_sql_mode: str = Field(default="TRADITIONAL", description="SQL模式")
    connection_pool_size: int = Field(default=10, ge=1, description="连接池大小")
    connection_timeout: int = Field(default=10, ge=1, description="连接超时时间")


class BotConfig(ValidatedConfigBase):
    """QQ机器人配置类"""

    platform: str = Field(..., description="平台")
    qq_account: int = Field(..., description="QQ账号")
    nickname: str = Field(..., description="昵称")
    alias_names: List[str] = Field(default_factory=list, description="别名列表")


class PersonalityConfig(ValidatedConfigBase):
    """人格配置类"""

    personality_core: str = Field(..., description="核心人格")
    personality_side: str = Field(..., description="人格侧写")
    identity: str = Field(default="", description="身份特征")
    reply_style: str = Field(default="", description="表达风格")
    prompt_mode: Literal["s4u", "normal"] = Field(default="s4u", description="Prompt模式")
    compress_personality: bool = Field(default=True, description="是否压缩人格")
    compress_identity: bool = Field(default=True, description="是否压缩身份")



class RelationshipConfig(ValidatedConfigBase):
    """关系配置类"""

    enable_relationship: bool = Field(default=True, description="是否启用关系")
    relation_frequency: float = Field(default=1.0, description="关系频率")



class ChatConfig(ValidatedConfigBase):
    """聊天配置类"""

    max_context_size: int = Field(default=18, description="最大上下文大小")
    replyer_random_probability: float = Field(default=0.5, description="回复者随机概率")
    thinking_timeout: int = Field(default=40, description="思考超时时间")
    talk_frequency: float = Field(default=1.0, description="聊天频率")
    mentioned_bot_inevitable_reply: bool = Field(default=False, description="提到机器人的必然回复")
    at_bot_inevitable_reply: bool = Field(default=False, description="@机器人的必然回复")
    talk_frequency_adjust: list[list[str]] = Field(default_factory=lambda: [], description="聊天频率调整")
    focus_value: float = Field(default=1.0, description="专注值")
    force_focus_private: bool = Field(default=False, description="强制专注私聊")
    group_chat_mode: Literal["auto", "normal", "focus"] = Field(default="auto", description="群聊模式")
    timestamp_display_mode: Literal["normal", "normal_no_YMD", "relative"] = Field(default="normal_no_YMD", description="时间戳显示模式")
    enable_proactive_thinking: bool = Field(default=False, description="启用主动思考")
    proactive_thinking_interval: int = Field(default=1500, description="主动思考间隔")
    proactive_thinking_prompt_template: str = Field(default="", description="主动思考提示模板")



class MessageReceiveConfig(ValidatedConfigBase):
    """消息接收配置类"""

    ban_words: set[str] = Field(default_factory=lambda: set(), description="禁用词列表")
    ban_msgs_regex: set[str] = Field(default_factory=lambda: set(), description="禁用消息正则列表")



class NormalChatConfig(ValidatedConfigBase):
    """普通聊天配置类"""

    willing_mode: str = Field(default="classical", description="意愿模式")



class ExpressionConfig(ValidatedConfigBase):
    """表达配置类"""

    expression_learning: list[list] = Field(default_factory=lambda: [], description="表达学习")
    expression_groups: list[list[str]] = Field(default_factory=list, description="表达组")



class ToolConfig(ValidatedConfigBase):
    """工具配置类"""

    enable_tool: bool = Field(default=False, description="启用工具")



class VoiceConfig(ValidatedConfigBase):
    """语音识别配置类"""

    enable_asr: bool = Field(default=False, description="启用语音识别")



class EmojiConfig(ValidatedConfigBase):
    """表情包配置类"""

    emoji_chance: float = Field(default=0.6, description="表情包出现概率")
    emoji_activate_type: str = Field(default="random", description="表情包激活类型")
    max_reg_num: int = Field(default=200, description="最大表情包数量")
    do_replace: bool = Field(default=True, description="是否替换表情包")
    check_interval: int = Field(default=120, description="检查间隔")
    steal_emoji: bool = Field(default=True, description="是否偷取表情包")
    content_filtration: bool = Field(default=False, description="内容过滤")
    filtration_prompt: str = Field(default="符合公序良俗", description="过滤提示")
    enable_emotion_analysis: bool = Field(default=True, description="启用情感分析")



class MemoryConfig(ValidatedConfigBase):
    """记忆配置类"""

    enable_memory: bool = Field(default=True, description="启用记忆")
    memory_build_interval: int = Field(default=600, description="记忆构建间隔")
    memory_build_distribution: tuple = Field(default_factory=lambda: (6.0, 3.0, 0.6, 32.0, 12.0, 0.4), description="记忆构建分布")
    memory_build_sample_num: int = Field(default=8, description="记忆构建样本数量")
    memory_build_sample_length: int = Field(default=40, description="记忆构建样本长度")
    memory_compress_rate: float = Field(default=0.1, description="记忆压缩率")
    forget_memory_interval: int = Field(default=1000, description="遗忘记忆间隔")
    memory_forget_time: int = Field(default=24, description="记忆遗忘时间")
    memory_forget_percentage: float = Field(default=0.01, description="记忆遗忘百分比")
    consolidate_memory_interval: int = Field(default=1000, description="记忆巩固间隔")
    consolidation_similarity_threshold: float = Field(default=0.7, description="巩固相似性阈值")
    consolidate_memory_percentage: float = Field(default=0.01, description="巩固记忆百分比")
    memory_ban_words: list[str] = Field(default_factory=lambda: ["表情包", "图片", "回复", "聊天记录"], description="记忆禁用词")
    enable_instant_memory: bool = Field(default=True, description="启用即时记忆")



class MoodConfig(ValidatedConfigBase):
    """情绪配置类"""

    enable_mood: bool = Field(default=False, description="启用情绪")
    mood_update_threshold: float = Field(default=1.0, description="情绪更新阈值")



class KeywordRuleConfig(ValidatedConfigBase):
    """关键词规则配置类"""

    keywords: list[str] = Field(default_factory=lambda: [], description="关键词列表")
    regex: list[str] = Field(default_factory=lambda: [], description="正则表达式列表")
    reaction: str = Field(default="", description="反应内容")

    def __post_init__(self):
        import re
        if not self.keywords and not self.regex:
            raise ValueError("关键词规则必须至少包含keywords或regex中的一个")
        if not self.reaction:
            raise ValueError("关键词规则必须包含reaction")
        for pattern in self.regex:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"无效的正则表达式 '{pattern}': {str(e)}") from e



class KeywordReactionConfig(ValidatedConfigBase):
    """关键词配置类"""

    keyword_rules: list[KeywordRuleConfig] = Field(default_factory=lambda: [], description="关键词规则列表")
    regex_rules: list[KeywordRuleConfig] = Field(default_factory=lambda: [], description="正则表达式规则列表")



class CustomPromptConfig(ValidatedConfigBase):
    """自定义提示词配置类"""

    image_prompt: str = Field(default="", description="图片提示词")
    planner_custom_prompt_enable: bool = Field(default=False, description="启用规划器自定义提示词")
    planner_custom_prompt_content: str = Field(default="", description="规划器自定义提示词内容")



class ResponsePostProcessConfig(ValidatedConfigBase):
    """回复后处理配置类"""

    enable_response_post_process: bool = Field(default=True, description="启用回复后处理")


class ChineseTypoConfig(ValidatedConfigBase):
    """中文错别字配置类"""

    enable: bool = Field(default=True, description="启用")
    error_rate: float = Field(default=0.01, description="错误率")
    min_freq: int = Field(default=9, description="最小频率")
    tone_error_rate: float = Field(default=0.1, description="语调错误率")
    word_replace_rate: float = Field(default=0.006, description="词语替换率")


class ResponseSplitterConfig(ValidatedConfigBase):
    """回复分割器配置类"""

    enable: bool = Field(default=True, description="启用")
    max_length: int = Field(default=256, description="最大长度")
    max_sentence_num: int = Field(default=3, description="最大句子数")
    enable_kaomoji_protection: bool = Field(default=False, description="启用颜文字保护")


class TelemetryConfig(ValidatedConfigBase):
    """遥测配置类"""

    enable: bool = Field(default=True, description="启用")


class DebugConfig(ValidatedConfigBase):
    """调试配置类"""

    show_prompt: bool = Field(default=False, description="显示提示")


class ExperimentalConfig(ValidatedConfigBase):
    """实验功能配置类"""

    enable_friend_chat: bool = Field(default=False, description="启用好友聊天")
    pfc_chatting: bool = Field(default=False, description="启用PFC聊天")


class MaimMessageConfig(ValidatedConfigBase):
    """maim_message配置类"""

    use_custom: bool = Field(default=False, description="启用自定义")
    host: str = Field(default="127.0.0.1", description="主机")
    port: int = Field(default=8090, description="端口")
    mode: Literal["ws", "tcp"] = Field(default="ws", description="模式")
    use_wss: bool = Field(default=False, description="启用WSS")
    cert_file: str = Field(default="", description="证书文件")
    key_file: str = Field(default="", description="密钥文件")
    auth_token: list[str] = Field(default_factory=lambda: [], description="认证令牌列表")



class LPMMKnowledgeConfig(ValidatedConfigBase):
    """LPMM知识库配置类"""

    enable: bool = Field(default=True, description="启用")
    rag_synonym_search_top_k: int = Field(default=10, description="RAG同义词搜索Top K")
    rag_synonym_threshold: float = Field(default=0.8, description="RAG同义词阈值")
    info_extraction_workers: int = Field(default=3, description="信息提取工作线程数")
    qa_relation_search_top_k: int = Field(default=10, description="QA关系搜索Top K")
    qa_relation_threshold: float = Field(default=0.75, description="QA关系阈值")
    qa_paragraph_search_top_k: int = Field(default=1000, description="QA段落搜索Top K")
    qa_paragraph_node_weight: float = Field(default=0.05, description="QA段落节点权重")
    qa_ent_filter_top_k: int = Field(default=10, description="QA实体过滤Top K")
    qa_ppr_damping: float = Field(default=0.8, description="QA PPR阻尼系数")
    qa_res_top_k: int = Field(default=10, description="QA结果Top K")
    embedding_dimension: int = Field(default=1024, description="嵌入维度")



class ScheduleConfig(ValidatedConfigBase):
    """日程配置类"""

    enable: bool = Field(default=True, description="启用")
    guidelines: Optional[str] = Field(default=None, description="指导方针")



class DependencyManagementConfig(ValidatedConfigBase):
    """插件Python依赖管理配置类"""

    auto_install: bool = Field(default=True, description="启用自动安装")
    auto_install_timeout: int = Field(default=300, description="自动安装超时时间")
    use_mirror: bool = Field(default=False, description="使用镜像")
    mirror_url: str = Field(default="", description="镜像URL")
    use_proxy: bool = Field(default=False, description="使用代理")
    proxy_url: str = Field(default="", description="代理URL")
    pip_options: list[str] = Field(default_factory=lambda: ["--no-warn-script-location", "--disable-pip-version-check"], description="Pip选项")
    prompt_before_install: bool = Field(default=False, description="安装前提示")
    install_log_level: str = Field(default="INFO", description="安装日志级别")



class ExaConfig(ValidatedConfigBase):
    """EXA搜索引擎配置类"""

    api_keys: list[str] = Field(default_factory=lambda: [], description="API密钥列表")



class TavilyConfig(ValidatedConfigBase):
    """Tavily搜索引擎配置类"""

    api_keys: list[str] = Field(default_factory=lambda: [], description="API密钥列表")



class VideoAnalysisConfig(ValidatedConfigBase):
    """视频分析配置类"""

    enable: bool = Field(default=True, description="启用")
    analysis_mode: str = Field(default="batch_frames", description="分析模式")
    max_frames: int = Field(default=8, description="最大帧数")
    frame_quality: int = Field(default=85, description="帧质量")
    max_image_size: int = Field(default=800, description="最大图像大小")
    enable_frame_timing: bool = Field(default=True, description="启用帧时间")
    batch_analysis_prompt: str = Field(default="", description="批量分析提示")


class WebSearchConfig(ValidatedConfigBase):
    """联网搜索组件配置类"""

    enable_web_search_tool: bool = Field(default=True, description="启用网络搜索工具")
    enable_url_tool: bool = Field(default=True, description="启用URL工具")
    enabled_engines: list[str] = Field(default_factory=lambda: ["ddg"], description="启用的搜索引擎")
    search_strategy: str = Field(default="single", description="搜索策略")


class AntiPromptInjectionConfig(ValidatedConfigBase):
    """LLM反注入系统配置类"""

    enabled: bool = Field(default=True, description="启用")
    enabled_LLM: bool = Field(default=True, description="启用LLM")
    enabled_rules: bool = Field(default=True, description="启用规则")
    process_mode: str = Field(default="lenient", description="处理模式")
    whitelist: list[list[str]] = Field(default_factory=list, description="白名单")
    llm_detection_enabled: bool = Field(default=True, description="启用LLM检测")
    llm_model_name: str = Field(default="anti_injection", description="LLM模型名称")
    llm_detection_threshold: float = Field(default=0.7, description="LLM检测阈值")
    cache_enabled: bool = Field(default=True, description="启用缓存")
    cache_ttl: int = Field(default=3600, description="缓存TTL")
    max_message_length: int = Field(default=4096, description="最大消息长度")
    stats_enabled: bool = Field(default=True, description="启用统计信息")
    auto_ban_enabled: bool = Field(default=True, description="启用自动禁用")
    auto_ban_violation_threshold: int = Field(default=3, description="自动禁用违规阈值")
    auto_ban_duration_hours: int = Field(default=2, description="自动禁用持续时间（小时）")
    shield_prefix: str = Field(default="🛡️ ", description="保护前缀")
    shield_suffix: str = Field(default=" 🛡️", description="保护后缀")
    enable_command_skip_list: bool = Field(default=True, description="启用命令跳过列表")
    auto_collect_plugin_commands: bool = Field(default=True, description="启用自动收集插件命令")
    manual_skip_patterns: list[str] = Field(default_factory=list, description="手动跳过模式")
    skip_system_commands: bool = Field(default=True, description="启用跳过系统命令")



class PluginsConfig(ValidatedConfigBase):
    """插件配置"""

    centralized_config: bool = Field(default=True, description="是否启用插件配置集中化管理")
