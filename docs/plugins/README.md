# 📚 MoFox-Bot 插件开发文档导航

欢迎来到 MoFox-Bot 插件系统开发文档！本文档帮助你快速找到所需的学习资源。

---

## 🎯 我应该从哪里开始？

### 第一次接触插件开发？
👉 **从这里开始**：[快速开始指南](quick-start.md)

这是一个循序渐进的教程，带你从零开始创建第一个插件，包含完整的代码示例。

### 遇到问题了？
👉 **先看这里**：[故障排除指南](troubleshooting-guide.md) ⭐

包含10个最常见问题的解决方案，可能5分钟就能解决你的问题。

### 想深入了解特定功能？
👉 **查看下方分类导航**，找到你需要的文档。

---

## 📖 学习路径建议

### 🌟 新手路径（按顺序阅读）

1. **[快速开始指南](quick-start.md)** ⭐ 必读
   - 创建插件目录和配置
   - 实现第一个 Action 组件
   - 实现第一个 Command 组件
   - 添加配置文件
   - 预计阅读时间：30-45分钟

2. **[增强命令指南](PLUS_COMMAND_GUIDE.md)** ⭐ 必读
   - 理解 PlusCommand 与 BaseCommand 的区别
   - 学习命令参数处理
   - 掌握返回值规范
   - 预计阅读时间：20-30分钟

3. **[Action 组件详解](action-components.md)** ⭐ 必读
   - 理解 Action 的激活机制
   - 学习自定义激活逻辑
   - 掌握 Action 的使用场景
   - 预计阅读时间：25-35分钟

4. **[故障排除指南](troubleshooting-guide.md)** ⭐ 建议收藏
   - 常见错误及解决方案
   - 最佳实践速查
   - 调试技巧
   - 随时查阅

---

### 🚀 进阶路径（根据需求选择）

#### 需要配置系统？
- **[配置文件系统指南](configuration-guide.md)**
  - 自动生成配置文件
  - 配置 Schema 定义
  - 配置读取和验证

#### 需要响应事件？
- **[事件系统指南](event-system-guide.md)**
  - 订阅系统事件
  - 创建自定义事件
  - 事件处理器实现

#### 需要集成外部功能？
- **[Tool 组件指南](tool_guide.md)**
  - 为 LLM 提供工具调用能力
  - 函数调用集成
  - Tool 参数定义

#### 需要依赖其他插件？
- **[依赖管理指南](dependency-management.md)**
  - 声明插件依赖
  - Python 包依赖
  - 依赖版本管理

#### 需要高级激活控制？
- **[Action 激活机制重构指南](action-activation-guide.md)**
  - 自定义激活逻辑
  - 关键词匹配激活
  - LLM 智能判断激活
  - 随机激活策略

---

## 📂 文档结构说明

### 核心文档（必读）

```
📄 quick-start.md              快速开始指南 ⭐ 新手必读
📄 PLUS_COMMAND_GUIDE.md       增强命令系统指南 ⭐ 必读
📄 action-components.md        Action 组件详解 ⭐ 必读
📄 troubleshooting-guide.md    故障排除指南 ⭐ 遇到问题先看这个
```

### 进阶文档（按需阅读）

```
📄 configuration-guide.md      配置系统详解
📄 event-system-guide.md       事件系统详解
📄 tool_guide.md               Tool 组件详解
📄 action-activation-guide.md  Action 激活机制详解
📄 dependency-management.md    依赖管理详解
📄 manifest-guide.md           Manifest 文件规范
```

### API 参考文档

```
📁 api/                        API 参考文档目录
  ├── 消息相关
  │   ├── send-api.md          消息发送 API
  │   ├── message-api.md       消息处理 API
  │   └── chat-api.md          聊天流 API
  │
  ├── AI 相关
  │   ├── llm-api.md           LLM 交互 API
  │   └── generator-api.md     回复生成 API
  │
  ├── 数据相关
  │   ├── database-api.md      数据库操作 API
  │   ├── config-api.md        配置读取 API
  │   └── person-api.md        人物关系 API
  │
  ├── 组件相关
  │   ├── plugin-manage-api.md 插件管理 API
  │   └── component-manage-api.md 组件管理 API
  │
  └── 其他
      ├── emoji-api.md         表情包 API
      ├── tool-api.md          工具 API
      └── logging-api.md       日志 API
```

### 其他文件

```
📄 index.md                    文档索引（旧版，建议查看本 README）
```

---

## 🎓 按功能查找文档

### 我想创建...

| 目标 | 推荐文档 | 难度 |
|------|----------|------|
| **一个简单的命令** | [快速开始](quick-start.md) → [增强命令指南](PLUS_COMMAND_GUIDE.md) | ⭐ 入门 |
| **一个智能 Action** | [快速开始](quick-start.md) → [Action 组件](action-components.md) | ⭐⭐ 中级 |
| **带复杂参数的命令** | [增强命令指南](PLUS_COMMAND_GUIDE.md) | ⭐⭐ 中级 |
| **需要配置的插件** | [配置系统指南](configuration-guide.md) | ⭐⭐ 中级 |
| **响应系统事件的插件** | [事件系统指南](event-system-guide.md) | ⭐⭐⭐ 高级 |
| **为 LLM 提供工具** | [Tool 组件指南](tool_guide.md) | ⭐⭐⭐ 高级 |
| **依赖其他插件的插件** | [依赖管理指南](dependency-management.md) | ⭐⭐ 中级 |

### 我想学习...

| 主题 | 相关文档 |
|------|----------|
| **如何发送消息** | [发送 API](api/send-api.md) / [增强命令指南](PLUS_COMMAND_GUIDE.md) |
| **如何处理参数** | [增强命令指南](PLUS_COMMAND_GUIDE.md) |
| **如何使用 LLM** | [LLM API](api/llm-api.md) |
| **如何操作数据库** | [数据库 API](api/database-api.md) |
| **如何读取配置** | [配置 API](api/config-api.md) / [配置系统指南](configuration-guide.md) |
| **如何获取消息历史** | [消息 API](api/message-api.md) / [聊天流 API](api/chat-api.md) |
| **如何发送表情包** | [表情包 API](api/emoji-api.md) |
| **如何记录日志** | [日志 API](api/logging-api.md) |

---

## 🆘 遇到问题？

### 第一步：查看故障排除指南
👉 [故障排除指南](troubleshooting-guide.md) 包含10个最常见问题的解决方案

### 第二步：查看相关文档
- **插件无法加载？** → [快速开始指南](quick-start.md)
- **命令无响应？** → [增强命令指南](PLUS_COMMAND_GUIDE.md)
- **Action 不触发？** → [Action 组件详解](action-components.md)
- **配置不生效？** → [配置系统指南](configuration-guide.md)

### 第三步：检查日志
查看 `logs/app_*.jsonl` 获取详细错误信息

### 第四步：寻求帮助
- 在线文档：https://mofox-studio.github.io/MoFox-Bot-Docs/
- GitHub Issues：提交详细的问题报告
- 社区讨论：加入开发者社区

---

## 📌 重要提示

### ⚠️ 常见陷阱

1. **不要使用 `BaseCommand`** 
   - ✅ 使用：`PlusCommand`
   - ❌ 避免：`BaseCommand`（仅供框架内部使用）

2. **不要在返回值中返回用户消息**
   - ✅ 使用：`await self.send_text("消息")`
   - ❌ 避免：`return True, "消息", True`

3. **手动创建 ComponentInfo 时必须指定 component_type**
   - ✅ 推荐：使用 `get_action_info()` 自动生成
   - ⚠️ 手动创建时：必须指定 `component_type=ComponentType.ACTION`

### 💡 最佳实践

- ✅ 总是使用类型注解
- ✅ 为 `execute()` 方法添加文档字符串
- ✅ 使用 `self.get_config()` 读取配置
- ✅ 使用异步操作 `async/await`
- ✅ 在发送消息前验证参数
- ✅ 提供清晰的错误提示

---

## 🔄 文档更新记录

### v1.1.0 (2024-12-17)
- ✨ 新增 [故障排除指南](troubleshooting-guide.md)
- ✅ 修复 [快速开始指南](quick-start.md) 中的 BaseCommand 示例
- ✅ 增强 [增强命令指南](PLUS_COMMAND_GUIDE.md) 的返回值说明
- ✅ 完善 [Action 组件](action-components.md) 的 component_type 说明
- 📝 创建本导航文档

### v1.0.0 (2024-11)
- 📚 初始文档发布

---

## 📞 反馈与贡献

如果你发现文档中的错误或有改进建议：

1. **提交 Issue**：在 GitHub 仓库提交文档问题
2. **提交 PR**：直接修改文档并提交 Pull Request
3. **社区反馈**：在社区讨论中提出建议

你的反馈对我们改进文档至关重要！🙏

---

## 🎉 开始你的插件开发之旅

准备好了吗？从这里开始：

1. 📖 阅读 [快速开始指南](quick-start.md)
2. 💻 创建你的第一个插件
3. 🔧 遇到问题查看 [故障排除指南](troubleshooting-guide.md)
4. 🚀 探索更多高级功能

**祝你开发愉快！** 🎊

---

**最后更新**：2024-12-17  
**文档版本**：v1.1.0
