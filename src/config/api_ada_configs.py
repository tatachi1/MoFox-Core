from typing import List, Dict, Any
from pydantic import Field, field_validator

from src.config.config_base import ValidatedConfigBase


class APIProvider(ValidatedConfigBase):
    """API提供商配置类"""

    name: str = Field(..., min_length=1, description="API提供商名称")
    base_url: str = Field(..., description="API基础URL")
    api_key: str = Field(..., min_length=1, description="API密钥")
    client_type: str = Field(default="openai", description="客户端类型（如openai/google等，默认为openai）")
    max_retry: int = Field(default=2, ge=0, description="最大重试次数（单个模型API调用失败，最多重试的次数）")
    timeout: int = Field(default=10, ge=1, description="API调用的超时时长（超过这个时长，本次请求将被视为'请求超时'，单位：秒）")
    retry_interval: int = Field(default=10, ge=0, description="重试间隔（如果API调用失败，重试的间隔时间，单位：秒）")
    enable_content_obfuscation: bool = Field(default=False, description="是否启用内容混淆（用于特定场景下的内容处理）")
    obfuscation_intensity: int = Field(default=1, ge=1, le=3, description="混淆强度（1-3级，数值越高混淆程度越强）")

    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, v):
        """验证base_url，确保URL格式正确"""
        if v and not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError("base_url必须以http://或https://开头")
        return v

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v):
        """验证API密钥不能为空"""
        if not v or not v.strip():
            raise ValueError("API密钥不能为空")
        return v

    @field_validator('client_type')
    @classmethod
    def validate_client_type(cls, v):
        """验证客户端类型"""
        allowed_types = ["openai", "gemini"]
        if v not in allowed_types:
            raise ValueError(f"客户端类型必须是以下之一: {allowed_types}")
        return v

    def get_api_key(self) -> str:
        return self.api_key


class ModelInfo(ValidatedConfigBase):
    """单个模型信息配置类"""

    model_identifier: str = Field(..., min_length=1, description="模型标识符（用于URL调用）")
    name: str = Field(..., min_length=1, description="模型名称（用于模块调用）")
    api_provider: str = Field(..., min_length=1, description="API提供商（如OpenAI、Azure等）")
    price_in: float = Field(default=0.0, ge=0, description="每M token输入价格")
    price_out: float = Field(default=0.0, ge=0, description="每M token输出价格")
    force_stream_mode: bool = Field(default=False, description="是否强制使用流式输出模式")
    extra_params: Dict[str, Any] = Field(default_factory=dict, description="额外参数（用于API调用时的额外配置）")

    @field_validator('price_in', 'price_out')
    @classmethod
    def validate_prices(cls, v):
        """验证价格必须为非负数"""
        if v < 0:
            raise ValueError("价格不能为负数")
        return v

    @field_validator('model_identifier')
    @classmethod
    def validate_model_identifier(cls, v):
        """验证模型标识符不能为空且不能包含特殊字符"""
        if not v or not v.strip():
            raise ValueError("模型标识符不能为空")
        # 检查是否包含危险字符
        if any(char in v for char in [' ', '\n', '\t', '\r']):
            raise ValueError("模型标识符不能包含空格或换行符")
        return v

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """验证模型名称不能为空"""
        if not v or not v.strip():
            raise ValueError("模型名称不能为空")
        return v


class TaskConfig(ValidatedConfigBase):
    """任务配置类"""

    model_list: List[str] = Field(default_factory=list, description="任务使用的模型列表")
    max_tokens: int = Field(default=1024, ge=1, le=100000, description="任务最大输出token数")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0, description="模型温度")
    concurrency_count: int = Field(default=1, ge=1, le=10, description="并发请求数量，默认为1（不并发）")

    @field_validator('model_list')
    @classmethod
    def validate_model_list(cls, v):
        """验证模型列表不能为空"""
        if not v:
            raise ValueError("模型列表不能为空")
        if len(v) != len(set(v)):
            raise ValueError("模型列表中不能有重复的模型")
        return v

    @field_validator('max_tokens')
    @classmethod
    def validate_max_tokens(cls, v):
        """验证最大token数"""
        if v <= 0:
            raise ValueError("最大token数必须大于0")
        if v > 100000:
            raise ValueError("最大token数不能超过100000")
        return v


class ModelTaskConfig(ValidatedConfigBase):
    """模型配置类"""

    utils: TaskConfig = Field(..., description="组件模型配置")
    
    # 可选配置项（有默认值） 
    utils_small: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["qwen3-8b"],
            max_tokens=800,
            temperature=0.7
        ),
        description="组件小模型配置"
    )
    replyer_1: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=800,
            temperature=0.2
        ),
        description="normal_chat首要回复模型模型配置"
    )
    replyer_2: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=800,
            temperature=0.7
        ),
        description="normal_chat次要回复模型配置"
    )
    maizone: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=800,
            temperature=0.3
        ),
        description="maizone专用模型"
    )
    emotion: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=800,
            temperature=0.7
        ),
        description="情绪模型配置"
    )
    vlm: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["qwen2.5-vl-72b"],
            max_tokens=1500,
            temperature=0.3
        ),
        description="视觉语言模型配置"
    )
    voice: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=800,
            temperature=0.3
        ),
        description="语音识别模型配置"
    )
    tool_use: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=800,
            temperature=0.1
        ),
        description="专注工具使用模型配置"
    )
    planner: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=800,
            temperature=0.3
        ),
        description="规划模型配置"
    )
    embedding: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["text-embedding-3-large"],
            max_tokens=1024,
            temperature=0.0
        ),
        description="嵌入模型配置"
    )
    lpmm_entity_extract: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=2000,
            temperature=0.1
        ),
        description="LPMM实体提取模型配置"
    )
    lpmm_rdf_build: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=2000,
            temperature=0.1
        ),
        description="LPMM RDF构建模型配置"
    )
    lpmm_qa: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=2000,
            temperature=0.3
        ),
        description="LPMM问答模型配置"
    )
    schedule_generator: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["siliconflow-deepseek-v3"],
            max_tokens=1500,
            temperature=0.3
        ),
        description="日程生成模型配置"
    )

    # 可选配置项（有默认值）
    video_analysis: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["qwen2.5-vl-72b"],
            max_tokens=1500,
            temperature=0.3
        ),
        description="视频分析模型配置"
    )
    emoji_vlm: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["qwen2.5-vl-72b"],
            max_tokens=800
        ),
        description="表情包识别模型配置"
    )
    anti_injection: TaskConfig = Field(
        default_factory=lambda: TaskConfig(
            model_list=["qwen2.5-vl-72b"],
            max_tokens=200,
            temperature=0.1
        ),
        description="反注入检测专用模型配置"
    )

    def get_task(self, task_name: str) -> TaskConfig:
        """获取指定任务的配置"""
        if hasattr(self, task_name):
            config = getattr(self, task_name)
            if config is None:
                raise ValueError(f"任务 '{task_name}' 未配置")
            return config
        raise ValueError(f"任务 '{task_name}' 未找到对应的配置")
