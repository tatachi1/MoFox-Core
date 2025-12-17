# 增强命令系统使用指南

> ⚠️ **重要：插件命令必须使用 PlusCommand！**
> 
> - ✅ **推荐**：`PlusCommand` - 插件开发的标准基类
> - ❌ **禁止**：`BaseCommand` - 仅供框架内部使用
> 
> 如果你直接使用 `BaseCommand`，将需要手动处理参数解析、正则匹配等复杂逻辑，并且 `execute()` 方法签名也不同。

## 概述

增强命令系统是MoFox-Bot插件系统的一个扩展，让命令的定义和使用变得更加简单直观。你不再需要编写复杂的正则表达式，只需要定义命令名、别名和参数处理逻辑即可。

## 核心特性

- **无需正则表达式**：只需定义命令名和别名
- **自动参数解析**：提供`CommandArgs`类处理参数
- **命令别名支持**：一个命令可以有多个别名
- **优先级控制**：支持命令优先级设置
- **聊天类型限制**：可限制命令在群聊或私聊中使用
- **消息拦截**：可选择是否拦截消息进行后续处理

## 快速开始

### 1. 创建基础命令

```python
from src.plugin_system import PlusCommand, CommandArgs, ChatType
from typing import Tuple, Optional

class EchoCommand(PlusCommand):
    """Echo命令示例"""
    
    command_name = "echo"
    command_description = "回显命令"
    command_aliases = ["say", "repeat"]  # 可选：命令别名
    priority = 5  # 可选：优先级，数字越大优先级越高
    chat_type_allow = ChatType.ALL  # 可选：ALL, GROUP, PRIVATE
    intercept_message = True  # 可选：是否拦截消息

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        """执行命令"""
        if args.is_empty():
            await self.send_text("❓ 请提供要回显的内容\\n用法: /echo <内容>")
            return True, "参数不足", True
        
        content = args.get_raw()
        await self.send_text(f"🔊 {content}")
        
        return True, "Echo命令执行成功", True
```

### 2. 在插件中注册命令

```python
from src.plugin_system import BasePlugin, create_plus_command_adapter, register_plugin

@register_plugin
class MyPlugin(BasePlugin):
    plugin_name = "my_plugin"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"

    def get_plugin_components(self):
        components = []
        
        # 使用工厂函数创建适配器
        echo_adapter = create_plus_command_adapter(EchoCommand)
        components.append((EchoCommand.get_command_info(), echo_adapter))
        
        return components
```

## CommandArgs 类详解

`CommandArgs`类提供了丰富的参数处理功能：

### 基础方法

```python
# 获取原始参数字符串
raw_text = args.get_raw()

# 获取解析后的参数列表（按空格分割，支持引号）
arg_list = args.get_args()

# 检查是否有参数
if args.is_empty():
    # 没有参数的处理

# 获取参数数量
count = args.count()
```

### 获取特定参数

```python
# 获取第一个参数
first_arg = args.get_first("默认值")

# 获取指定索引的参数
second_arg = args.get_arg(1, "默认值")

# 获取从指定位置开始的剩余参数
remaining = args.get_remaining(1)  # 从第2个参数开始
```

### 标志参数处理

```python
# 检查是否包含标志
if args.has_flag("--verbose"):
    # 处理verbose模式

# 获取标志的值
output_file = args.get_flag_value("--output", "default.txt")
name = args.get_flag_value("--name", "Anonymous")
```

## 高级示例

### 1. 带子命令的复杂命令

```python
class TestCommand(PlusCommand):
    command_name = "test"
    command_description = "测试命令，展示参数解析功能"
    command_aliases = ["t"]

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        if args.is_empty():
            await self.send_text("用法: /test <子命令> [参数]")
            return True, "显示帮助", True
        
        subcommand = args.get_first().lower()
        
        if subcommand == "args":
            result = f"""
🔍 参数解析结果:
原始字符串: '{args.get_raw()}'
解析后参数: {args.get_args()}
参数数量: {args.count()}
第一个参数: '{args.get_first()}'
剩余参数: '{args.get_remaining()}'
            """
            await self.send_text(result)
            
        elif subcommand == "flags":
            result = f"""
🏴 标志测试结果:
包含 --verbose: {args.has_flag('--verbose')}
包含 -v: {args.has_flag('-v')}
--output 的值: '{args.get_flag_value('--output', '未设置')}'
--name 的值: '{args.get_flag_value('--name', '未设置')}'
            """
            await self.send_text(result)
            
        else:
            await self.send_text(f"❓ 未知的子命令: {subcommand}")
        
        return True, "Test命令执行成功", True
```

### 2. 聊天类型限制示例

```python
class PrivateOnlyCommand(PlusCommand):
    command_name = "private"
    command_description = "仅私聊可用的命令"
    chat_type_allow = ChatType.PRIVATE

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        await self.send_text("这是一个仅私聊可用的命令")
        return True, "私聊命令执行", True

class GroupOnlyCommand(PlusCommand):
    command_name = "group"
    command_description = "仅群聊可用的命令"
    chat_type_allow = ChatType.GROUP

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        await self.send_text("这是一个仅群聊可用的命令")
        return True, "群聊命令执行", True
```

### 3. 配置驱动的命令

```python
class ConfigurableCommand(PlusCommand):
    command_name = "config_cmd"
    command_description = "可配置的命令"

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        # 从插件配置中获取设置
        max_length = self.get_config("commands.max_length", 100)
        enabled_features = self.get_config("commands.features", [])
        
        if args.is_empty():
            await self.send_text("请提供参数")
            return True, "无参数", True
            
        content = args.get_raw()
        if len(content) > max_length:
            await self.send_text(f"内容过长，最大允许 {max_length} 字符")
            return True, "内容过长", True
            
        # 根据配置决定功能
        if "uppercase" in enabled_features:
            content = content.upper()
            
        await self.send_text(f"处理结果: {content}")
        return True, "配置命令执行", True
```

## 支持的命令前缀

系统支持以下命令前缀（在`config/bot_config.toml`中配置）：

- `/` - 斜杠（默认）
- `!` - 感叹号
- `.` - 点号
- `#` - 井号

例如，对于echo命令，以下调用都是有效的：
- `/echo Hello`
- `!echo Hello`
- `.echo Hello`
- `#echo Hello`

## 返回值说明

`execute`方法必须返回一个三元组：

```python
async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
    # ... 你的逻辑 ...
    return (执行成功标志, 日志描述, 是否拦截消息)
```

### 返回值详解

| 位置 | 类型 | 名称 | 说明 |
|------|------|------|------|
| 1 | `bool` | 执行成功标志 | `True` = 命令执行成功<br>`False` = 命令执行失败 |
| 2 | `Optional[str]` | 日志描述 | 用于内部日志记录的描述性文本<br>⚠️ **不是发给用户的消息！** |
| 3 | `bool` | 是否拦截消息 | `True` = 拦截，阻止后续处理（推荐）<br>`False` = 不拦截，继续后续处理 |

### 重要：消息发送 vs 日志描述

⚠️ **常见错误：在返回值中返回用户消息**

```python
# ❌ 错误做法 - 不要这样做！
async def execute(self, args: CommandArgs):
    message = "你好，这是给用户的消息"
    return True, message, True  # 这个消息不会发给用户！

# ✅ 正确做法 - 使用 self.send_text()
async def execute(self, args: CommandArgs):
    await self.send_text("你好，这是给用户的消息")  # 发送给用户
    return True, "执行了问候命令", True  # 日志描述
```

### 完整示例

```python
async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
    """execute 方法的完整示例"""
    
    # 1. 参数验证
    if args.is_empty():
        await self.send_text("⚠️ 请提供参数")
        return True, "缺少参数", True
    
    # 2. 执行逻辑
    user_input = args.get_raw()
    result = process_input(user_input)
    
    # 3. 发送消息给用户
    await self.send_text(f"✅ 处理结果：{result}")
    
    # 4. 返回：成功、日志描述、拦截消息
    return True, f"处理了用户输入: {user_input[:20]}", True
```

### 拦截标志使用指导

- **返回 `True`**（推荐）：命令已完成处理，不需要后续处理（如 LLM 回复）
- **返回 `False`**：允许系统继续处理（例如让 LLM 也回复）

## 最佳实践

### 1. 命令设计
- ✅ **命令命名**：使用简短、直观的命令名（如 `time`、`help`、`status`）
- ✅ **别名设置**：为常用命令提供简短别名（如 `echo` -> `e`、`say`）
- ✅ **聊天类型**：根据命令功能选择 `ChatType.ALL`/`GROUP`/`PRIVATE`

### 2. 参数处理
- ✅ **总是验证**：使用 `args.is_empty()`、`args.count()` 检查参数
- ✅ **友好提示**：参数错误时提供清晰的用法说明
- ✅ **默认值**：为可选参数提供合理的默认值

### 3. 消息发送
- ✅ **使用 `self.send_text()`**：发送消息给用户
- ❌ **不要在返回值中返回用户消息**：返回值是日志描述
- ✅ **拦截消息**：大多数情况返回 `True` 作为第三个参数

### 4. 错误处理
- ✅ **Try-Catch**：捕获并处理可能的异常
- ✅ **清晰反馈**：告诉用户发生了什么问题
- ✅ **记录日志**：在返回值中提供有用的调试信息

### 5. 配置管理
- ✅ **可配置化**：重要设置应该通过 `self.get_config()` 读取
- ✅ **提供默认值**：即使配置缺失也能正常工作

### 6. 代码质量
- ✅ **类型注解**：使用完整的类型提示
- ✅ **文档字符串**：为 `execute()` 方法添加文档说明
- ✅ **代码注释**：为复杂逻辑添加必要的注释

## 完整示例

完整的插件示例请参考 `plugins/echo_example/plugin.py` 文件。

## 与传统BaseCommand的区别

| 特性 | PlusCommand | BaseCommand |
|------|-------------|-------------|
| 正则表达式 | 自动生成 | 手动编写 |
| 参数解析 | CommandArgs类 | 手动处理 |
| 别名支持 | 内置支持 | 需要在正则中处理 |
| 代码复杂度 | 简单 | 复杂 |
| 学习曲线 | 平缓 | 陡峭 |

增强命令系统让插件开发变得更加简单和高效，特别适合新手开发者快速上手。
