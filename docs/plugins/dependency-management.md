# 插件Python依赖管理系统

## 概述

插件系统现在支持自动检查和安装Python包依赖。当插件初始化时，系统会：

1. 检查插件所需的Python包是否已安装
2. 验证包版本是否满足要求
3. 自动安装缺失的依赖包（可配置）
4. 提供详细的错误信息和日志

## 配置依赖

### 方式1: 简单字符串列表（向后兼容）

```python
from src.plugin_system import BasePlugin

@register_plugin
class MyPlugin(BasePlugin):
    # 简单的字符串列表格式
    python_dependencies: List[str] = [
        "requests", 
        "beautifulsoup4>=4.9.0",
        "httpx[socks]"
    ]
```

### 方式2: 详细的PythonDependency对象（推荐）

```python
from src.plugin_system import BasePlugin, PythonDependency

@register_plugin
class MyPlugin(BasePlugin):
    python_dependencies: List[PythonDependency] = [
        PythonDependency(
            package_name="requests",
            version=">=2.25.0",
            description="HTTP请求库",
            optional=False
        ),
        PythonDependency(
            package_name="beautifulsoup4",
            version=">=4.9.0", 
            description="HTML解析库",
            optional=False
        ),
        PythonDependency(
            package_name="httpx",
            install_name="httpx[socks]",  # 安装时使用的名称
            description="支持SOCKS代理的HTTP客户端",
            optional=True
        )
    ]
```

## PythonDependency参数说明

- `package_name`: 包名称（用于import检查）
- `version`: 版本要求，支持PEP 440格式（如 ">=1.0.0", "==2.1.3"）
- `install_name`: pip安装时使用的名称（如果与package_name不同）
- `description`: 依赖描述，用于日志和错误信息
- `optional`: 是否为可选依赖，可选依赖缺失不会阻止插件加载

## 全局配置

创建 `mmc/config/dependency_config.toml` 文件来配置依赖管理行为：

```toml
[dependency_management]
# 是否启用自动安装（主开关）
auto_install = true

# 安装超时时间（秒）
auto_install_timeout = 300

# 是否使用代理
use_proxy = false
proxy_url = ""

# pip安装选项
pip_options = [
    "--no-warn-script-location",
    "--disable-pip-version-check"
]

# 安装前是否提示用户
prompt_before_install = false

# 日志级别
install_log_level = "INFO"
```

## 代理配置

如果需要通过代理安装包，可以配置：

```toml
[dependency_management]
use_proxy = true
proxy_url = "http://proxy.example.com:8080"
# 或者 SOCKS5 代理
# proxy_url = "socks5://proxy.example.com:1080"
```

## 编程方式配置

也可以通过代码动态配置依赖管理：

```python
from src.plugin_system.utils.dependency_config import configure_dependency_settings

# 禁用自动安装
configure_dependency_settings(auto_install=False)

# 设置代理
configure_dependency_settings(
    use_proxy=True,
    proxy_url="http://proxy.example.com:8080"
)

# 修改超时时间
configure_dependency_settings(auto_install_timeout=600)
```

## 工作流程

1. **插件初始化**: 当插件类被实例化时，系统自动检查依赖
2. **依赖标准化**: 将字符串格式的依赖转换为PythonDependency对象
3. **检查已安装**: 尝试导入每个依赖包并检查版本
4. **自动安装**: 如果启用，自动安装缺失的依赖
5. **错误处理**: 记录详细的错误信息和安装日志

## 日志输出示例

```
[Plugin:web_search_tool] 开始自动安装Python依赖: ['asyncddgs', 'httpx[socks]']
[Plugin:web_search_tool] ✅ 成功安装: asyncddgs
[Plugin:web_search_tool] ✅ 成功安装: httpx[socks]
[Plugin:web_search_tool] 🎉 所有依赖安装完成
[Plugin:web_search_tool] Python依赖检查通过
```

## 错误处理

当依赖检查失败时，系统会：

1. 记录详细的错误信息
2. 如果是可选依赖缺失，仅记录警告
3. 如果是必需依赖缺失且自动安装失败，阻止插件加载
4. 提供清晰的解决建议

## 最佳实践

1. **使用详细的PythonDependency对象** 以获得更好的控制和文档
2. **合理设置可选依赖** 避免非核心功能阻止插件加载
3. **指定版本要求** 确保兼容性
4. **添加描述信息** 帮助用户理解依赖的用途
5. **测试依赖配置** 在不同环境中验证依赖是否正确

## 安全考虑

- 自动安装功能默认启用，但可以通过`auto_install=false`配置禁用
- 所有安装操作都有详细的日志记录
- 支持设置安装超时以避免长时间挂起
- 通过单一的`auto_install`开关控制所有自动安装行为

## 故障排除

### 依赖安装失败

1. 检查网络连接
2. 验证代理设置
3. 检查pip配置
4. 查看详细的错误日志

### 版本冲突

1. 检查现有包的版本
2. 调整版本要求
3. 考虑使用虚拟环境

### 导入错误

1. 确认包名与导入名一致
2. 检查可选依赖配置
3. 验证安装是否成功

