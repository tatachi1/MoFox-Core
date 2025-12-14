# MoFox Core 重构架构文档

MoFox src目录将被严格分为三个层级：

kernel - 内核/基础能力 层 - 提供“与具体业务无关的技术能力”
core - 核心层/领域/心智 层 - 用 kernel 的能力实现记忆、对话、行为等核心功能，不关心插件或具体平台
app - 应用/装配/插件 层 - 把 kernel 和 core 组装成可运行的 Bot 系统，对外提供高级 API 和插件扩展点

## kernel层：
包含以下模块：
db：底层数据库接口
    __init__.py：导出
    core：数据库核心
        __init__.py：导出
        dialect_adapter.py：数据库方言适配器
        engine.py：数据库引擎管理
        session.py：数据库会话管理
        exceptions.py：数据库异常定义
    optimization：数据库优化
        __init__.py：导出
        backends：缓存后端实现
            cache_backend.py：缓存后端抽象基类
            local_cache.py：本地缓存后端
            redis_cache.py：Redis缓存后端
        cache_manager.py：多级缓存管理器
    api：操作接口
        crud.py：统一的crud操作
        query.py：高级查询API
vector_db：底层向量存储接口
    __init__.py：导出＋工厂函数，初始化并返回向量数据库服务实例。
    base.py：向量数据库的抽象基类 (ABC)，定义了所有向量数据库实现必须遵循的接口
    chromadb_impl.py：chromadb的具体实现，遵循 VectorDBBase 接口
config：底层配置文件系统
    __init__.py：导出
    config_base.py：配置项基类
    config.py：配置的读取、修改、更新等
llm：底层llm网络请求系统
    __init__.py：导出
    utils.py：基本工具，如图片压缩，格式转换
    llm_request.py：与大语言模型（LLM）交互的所有核心逻辑
    exceptions.py：llm请求异常类
    client_registry.py：client注册管理
    model_client：client集合 
        base_client.py：client基类
        aiohttp_gemini_clinet.py：基于aiohttp实现的gemini client
        bedrock_client.py：aws client
        openai_client.py：openai client
    payload：标准负载构建
        message.py：标准消息构建
        resp_format.py：标准响应解析
        tool_option.py：标准工具负载构建
        standard_prompt.py：标准prompt（system等）
logger：日志系统
    __init__.py：导出
    core.py：日志系统主入口
    cleanup.py：日志清理/压缩相关
    metadata.py：日志元数据相关
    renderers.py：日志格式化器
    config.py：配置相关的辅助操作
    handlers.py：日志处理器（console handler、file handler等）
concurrency：底层异步管理
    __init__.py：导出
    task_manager.py：统一异步任务管理器
    watchdog.py：全局看门狗
storage：本地持久化数据管理
    __init__.py：导出
    json_store.py：统一的json本地持久化操作器

## core层：
包含以下模块：
components：基本插件组件管理
    __init__.py：导出
    base：组件基类
        __init__.py：导出
        action.py
        adapter.py
        chatter.py
        command.py
        event_handler.py
        router.py
        service.py
        plugin.py
        prompt.py
        tool.py
    managers：组件应用管理，实际能力调用
        __init__.py：导出
        action_manager.py：动作管理器
        adapter_manager.py：适配器管理
        chatter_manager.py：聊天器管理
        event_manager.py：事件管理器
        service_manager.py：服务管理器
        mcp_manager：MCP相关管理
            __init__.py：导出
            mcp_client_manager.py：MCP客户端管理器
            mcp_tool_manager.py：MCP工具管理器
        permission_manager.py：权限管理器
        plugin_manager.py：插件管理器
        tool_manager：工具相关管理
            tool_histoty.py：工具调用历史记录
            tool_use.py：实际工具调用器
    types.py：组件类型
    registry.py：组件注册管理
    state_manager.py：组件状态管理

