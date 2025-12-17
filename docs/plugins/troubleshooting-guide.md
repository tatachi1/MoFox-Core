# 🔧 插件开发故障排除指南

本指南帮助你快速解决 MoFox-Bot 插件开发中的常见问题。

---

## 📋 快速诊断清单

遇到问题时，首先按照以下步骤检查：

1. ✅ 检查日志文件 `logs/app_*.jsonl`
2. ✅ 确认插件已在 `_manifest.json` 中正确配置
3. ✅ 验证你使用的是 `PlusCommand` 而不是 `BaseCommand`
4. ✅ 检查 `execute()` 方法签名是否正确
5. ✅ 确认返回值格式正确

---

## 🔴 严重问题：插件无法加载

### 错误 #1: "未检测到插件"

**症状**：
- 插件目录存在，但日志中没有加载信息
- `get_plugin_components()` 返回空列表

**可能原因与解决方案**：

#### ❌ 缺少 `@register_plugin` 装饰器

```python
# 错误 - 缺少装饰器
class MyPlugin(BasePlugin):  # 不会被检测到
    pass

# 正确 - 添加装饰器
@register_plugin  # 必须添加！
class MyPlugin(BasePlugin):
    pass
```

#### ❌ `plugin.py` 文件不存在或位置错误

```
plugins/
  └── my_plugin/
      ├── _manifest.json     ✅
      └── plugin.py           ✅ 必须在这里
```

#### ❌ `_manifest.json` 格式错误

```json
{
  "manifest_version": 1,
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "插件描述",
  "author": {
    "name": "Your Name"
  }
}
```

---

### 错误 #2: "ActionInfo.__init__() missing required argument: 'component_type'"

**症状**：
```
TypeError: ActionInfo.__init__() missing 1 required positional argument: 'component_type'
```

**原因**：手动创建 `ActionInfo` 时未指定 `component_type` 参数

**解决方案**：

```python
from src.plugin_system import ActionInfo, ComponentType

# ❌ 错误 - 缺少 component_type
action_info = ActionInfo(
    name="my_action",
    description="我的动作"
)

# ✅ 正确方法 1 - 使用自动生成（推荐）
class MyAction(BaseAction):
    action_name = "my_action"
    action_description = "我的动作"

def get_plugin_components(self):
    return [
        (MyAction.get_action_info(), MyAction)  # 自动生成，推荐！
    ]

# ✅ 正确方法 2 - 手动指定 component_type
action_info = ActionInfo(
    name="my_action",
    description="我的动作",
    component_type=ComponentType.ACTION  # 必须指定！
)
```

---

## 🟡 命令问题：命令无响应

### 错误 #3: 命令被识别但不执行

**症状**：
- 输入 `/mycommand` 后没有任何反应
- 日志显示命令已匹配但未执行

**可能原因与解决方案**：

#### ❌ 使用了 `BaseCommand` 而不是 `PlusCommand`

```python
# ❌ 错误 - 使用 BaseCommand
from src.plugin_system import BaseCommand

class MyCommand(BaseCommand):  # 不推荐！
    command_name = "mycommand"
    command_pattern = r"^/mycommand$"  # 需要手动写正则
    
    async def execute(self):  # 签名错误！
        pass

# ✅ 正确 - 使用 PlusCommand
from src.plugin_system import PlusCommand, CommandArgs

class MyCommand(PlusCommand):  # 推荐！
    command_name = "mycommand"
    # 不需要 command_pattern，会自动生成！
    
    async def execute(self, args: CommandArgs):  # 正确签名
        await self.send_text("命令执行成功")
        return True, "执行了mycommand", True
```

#### ❌ `execute()` 方法签名错误

```python
# ❌ 错误的签名（缺少 args 参数）
async def execute(self) -> Tuple[bool, Optional[str], bool]:
    pass

# ❌ 错误的签名（参数类型错误）
async def execute(self, args: list[str]) -> Tuple[bool, Optional[str], bool]:
    pass

# ✅ 正确的签名
async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
    await self.send_text("响应用户")
    return True, "日志描述", True
```

---

### 错误 #4: 命令发送了消息但用户没收到

**症状**：
- 日志显示命令执行成功
- 但用户没有收到任何消息

**原因**：在返回值中返回消息，而不是使用 `self.send_text()`

**解决方案**：

```python
# ❌ 错误 - 在返回值中返回消息
async def execute(self, args: CommandArgs):
    message = "这是给用户的消息"
    return True, message, True  # 这不会发送给用户！

# ✅ 正确 - 使用 self.send_text()
async def execute(self, args: CommandArgs):
    # 发送消息给用户
    await self.send_text("这是给用户的消息")
    
    # 返回日志描述（不是用户消息）
    return True, "执行了某个操作", True
```

---

### 错误 #5: "notice处理失败" 或重复消息

**症状**：
- 日志中出现 "notice处理失败"
- 用户收到重复的消息

**原因**：同时使用了 `send_api.send_text()` 和返回消息

**解决方案**：

```python
# ❌ 错误 - 混用不同的发送方式
from src.plugin_system.apis.chat_api import send_api

async def execute(self, args: CommandArgs):
    await send_api.send_text(self.stream_id, "消息1")  # 不要这样做
    return True, "消息2", True  # 也不要返回消息

# ✅ 正确 - 只使用 self.send_text()
async def execute(self, args: CommandArgs):
    await self.send_text("这是唯一的消息")  # 推荐方式
    return True, "日志：执行成功", True  # 仅用于日志
```

---

## 🟢 配置问题

### 错误 #6: 配置警告 "配置中不存在字空间或键"

**症状**：
```
获取全局配置 plugins.my_plugin 失败: "配置中不存在字空间或键 'plugins'"
```

**这是正常的吗？**

✅ **是的，这是正常行为！** 不需要修复。

**说明**：
- 系统首先尝试从全局配置加载：`config/plugins/my_plugin/config.toml`
- 如果不存在，会自动回退到插件本地配置：`plugins/my_plugin/config.toml`
- 这个警告可以安全忽略

**如果你想消除警告**：
1. 在 `config/plugins/` 目录创建你的插件配置目录
2. 或者直接忽略 - 使用本地配置完全正常

---

## 🔧 返回值问题

### 错误 #7: 返回值格式错误

**Action 返回值** (2个元素)：
```python
async def execute(self) -> Tuple[bool, str]:
    await self.send_text("消息")
    return True, "日志描述"  # 2个元素
```

**Command 返回值** (3个元素)：
```python
async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
    await self.send_text("消息")
    return True, "日志描述", True  # 3个元素（增加了拦截标志）
```

**对比表格**：

| 组件类型 | 返回值 | 元素说明 |
|----------|--------|----------|
| **Action** | `(bool, str)` | (成功标志, 日志描述) |
| **Command** | `(bool, str, bool)` | (成功标志, 日志描述, 拦截标志) |

---

## 🎯 参数解析问题

### 错误 #8: 无法获取命令参数

**症状**：
- `args` 为空或不包含预期的参数

**解决方案**：

```python
async def execute(self, args: CommandArgs):
    # 检查是否有参数
    if args.is_empty():
        await self.send_text("❌ 缺少参数\n用法: /command <参数>")
        return True, "缺少参数", True
    
    # 获取原始参数字符串
    raw_input = args.get_raw()
    
    # 获取解析后的参数列表
    arg_list = args.get_args()
    
    # 获取第一个参数
    first_arg = args.get_first("默认值")
    
    # 获取指定索引的参数
    second_arg = args.get_arg(1, "默认值")
    
    # 检查标志
    if args.has_flag("--verbose"):
        # 处理 --verbose 模式
        pass
    
    # 获取标志的值
    output = args.get_flag_value("--output", "default.txt")
```

---

## 📝 类型注解问题

### 错误 #9: IDE 报类型错误

**解决方案**：确保使用正确的类型导入

```python
from typing import Tuple, Optional, List, Type
from src.plugin_system import (
    BasePlugin,
    PlusCommand,
    BaseAction,
    CommandArgs,
    ComponentInfo,
    CommandInfo,
    ActionInfo,
    ComponentType
)

# 正确的类型注解
def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
    return [
        (MyCommand.get_command_info(), MyCommand),
        (MyAction.get_action_info(), MyAction)
    ]
```

---

## 🚀 性能问题

### 错误 #10: 插件响应缓慢

**可能原因**：

1. **阻塞操作**：在 `execute()` 中使用了同步 I/O
2. **大量数据处理**：在主线程处理大文件或复杂计算
3. **频繁的数据库查询**：每次都查询数据库

**解决方案**：

```python
import asyncio

async def execute(self, args: CommandArgs):
    # ✅ 使用异步操作
    result = await some_async_function()
    
    # ✅ 对于同步操作，使用 asyncio.to_thread
    result = await asyncio.to_thread(blocking_function)
    
    # ✅ 批量数据库操作
    from src.common.database.optimization.batch_scheduler import get_batch_scheduler
    scheduler = get_batch_scheduler()
    await scheduler.schedule_batch_insert(Model, data_list)
    
    return True, "执行成功", True
```

---

## 📞 获取帮助

如果以上方案都无法解决你的问题：

1. **查看日志**：检查 `logs/app_*.jsonl` 获取详细错误信息
2. **查阅文档**：
   - [快速开始指南](./quick-start.md)
   - [增强命令指南](./PLUS_COMMAND_GUIDE.md)
   - [Action组件指南](./action-components.md)
3. **在线文档**：https://mofox-studio.github.io/MoFox-Bot-Docs/
4. **提交 Issue**：在 GitHub 仓库提交详细的问题报告

---

## 🎓 最佳实践速查

| 场景 | 推荐做法 | 避免 |
|------|----------|------|
| 创建命令 | 使用 `PlusCommand` | ❌ 使用 `BaseCommand` |
| 发送消息 | `await self.send_text()` | ❌ 在返回值中返回消息 |
| 注册组件 | 使用 `get_action_info()` | ❌ 手动创建不带 `component_type` 的 Info |
| 参数处理 | 使用 `CommandArgs` 方法 | ❌ 手动解析字符串 |
| 异步操作 | 使用 `async/await` | ❌ 使用同步阻塞操作 |
| 配置读取 | `self.get_config()` | ❌ 硬编码配置值 |

---

**最后更新**：2024-12-17  
**版本**：v1.0.0

有问题欢迎反馈，帮助我们改进这份指南！
