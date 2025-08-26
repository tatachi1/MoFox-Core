<div align="center">
  
  # 麦麦Fork！MoFox_Bot
  
  <p>
    <strong>基于 MaiCore 的增强版智能体，提供更完善的功能和更好的使用体验</strong>
  </p>

  [![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&style=for-the-badge)](https://www.python.org/)
  [![License](https://img.shields.io/badge/License-GPLv3-blue?logo=gnu&style=for-the-badge)](https://github.com/MoFox-Studio/MoFox_Bot/blob/master/LICENSE)
  [![Contributors](https://img.shields.io/github/contributors/MaiBot-Plus/MaiMbot-Pro-Max.svg?style=for-the-badge&label=贡献者)](https://github.com/MoFox-Studio/MoFox_Bot/graphs/contributors)
  [![Stars](https://img.shields.io/github/stars/MaiBot-Plus/MaiMbot-Pro-Max?style=for-the-badge&label=星标数)](https://github.com/MoFox-Studio/MoFox_Bot/stargazers)


## 项目介绍

**MoFox_Bot** 是基于 MaiCore 的增强版智能体，在保留原版0.10.0 snapshot.5所有功能的基础上，提供了更完善的功能、更好的稳定性和更丰富的使用体验。

**请注意！这个版本的所有后续更新均为我们的第三方更新，不代表MaiBot官方立场**


> [!TIP]
> 请注意！ 从官方版本到 MoFox_Bot 版本迁移暂时存在问题，因为数据库结构有改变


### 原版功能（全部保留）

- **智能对话系统**：基于 LLM 的自然语言交互，支持normal和focus统一化处理
- **强大插件系统**：全面重构的插件架构，支持完整的管理API和权限控制
- **实时思维系统**：模拟人类思考过程
- **表达学习功能**：学习群友的说话风格和表达方式
- **情感表达系统**：情绪系统和表情包系统
- **持久记忆系统**：基于图的长期记忆存储
- **动态人格系统**：自适应的性格特征和表达方式
- **数据分析**：内置数据统计和分析功能，更好了解麦麦状态

### 拓展功能
- **数据库切换**: 支持SQLite与MySQL自由切换,采用 SQLAlchemy 2.0重新构建
- **反注入集成**: 内置一整套回复前注入过滤系统,为人格保价护航
- **视频分析**: 支持多种视频识别模式，拓展原版视觉
- **苏醒系统**: 能够睡觉, 失眠, 被吵醒,更具乐趣
- **日程系统**: 让墨狐规划每一天
- **完善的Event**: 支持动态事件注册和处理器订阅，并实现了聚合结果管理
- **内嵌魔改插件**: 内置联网搜索等诸多功能,等你来探索
- **还有更多**: 请参阅详细修改[(commits)](https://github.com/MoFox-Studio/MoFox_Bot/commits)
## 系统要求

在开始使用之前，请确保你的系统满足以下要求：

### 基础要求
- **操作系统**: Windows 10/11, macOS 10.14+, Linux (Ubuntu 18.04+)
- **Python版本**: Python 3.10 或更高版本
- **内存**: 建议 4GB 以上可用内存
- **存储空间**: 至少 2GB 可用空间

### 依赖服务
- **QQ协议端**: [NapCat](https://github.com/NapNeko/NapCatQQ) 或其他兼容协议端
- **数据库**: SQLite (内置) 或 MySQL (可选)，chat2db(可选)


## 致谢

- [MaiM-with-u](https://github.com/MaiM-with-u/MaiBot): 原版 MaiBot 项目，感谢提供优秀的基础框架
- [NapCat](https://github.com/NapNeko/NapCatQQ): 现代化的基于 NTQQ 的 Bot 协议端实现
- [Maizone](https://github.com/internetsb/Maizone): 魔改空间插件部分借鉴该插件
## 注意事项

> [!WARNING]
> 使用本项目前必须阅读和同意[用户协议](EULA.md)和[隐私协议](PRIVACY.md)。  
> 本应用生成内容来自人工智能模型，由 AI 生成，请仔细甄别，请勿用于违反法律的用途，AI 生成内容不代表本项目团队的观点和立场。

## License

GPL-3.0
