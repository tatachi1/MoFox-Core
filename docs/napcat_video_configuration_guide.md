# Napcat 视频处理配置指南

## 概述

本指南说明如何在 MoFox-Bot 中配置和控制 Napcat 适配器的视频消息处理功能。

**相关 Issue**: [#10 - 强烈请求有个开关选择是否下载视频](https://github.com/MoFox-Studio/MoFox-Core/issues/10)

---

## 快速开始

### 关闭视频下载（推荐用于低配机器或有限带宽）

编辑 `config/bot_config.toml`，找到 `[napcat_adapter.features]` 段落，修改：

```toml
[napcat_adapter.features]
enable_video_processing = false  # 改为 false 关闭视频处理
```

**效果**：视频消息会显示为 `[视频消息]`，不会进行下载。

---

## 配置选项详解

### 主开关：`enable_video_processing`

| 属性 | 值 |
|------|-----|
| **类型** | 布尔值 (`true` / `false`) |
| **默认值** | `true` |
| **说明** | 是否启用视频消息的下载和处理 |

**启用 (`true`)**：
- ✅ 自动下载视频
- ✅ 将视频转换为 base64 并发送给 AI
- ⚠️ 消耗网络带宽和 CPU 资源

**禁用 (`false`)**：
- ✅ 跳过视频下载
- ✅ 显示 `[视频消息]` 占位符
- ✅ 显著降低带宽和 CPU 占用

### 高级选项

#### `video_max_size_mb`

| 属性 | 值 |
|------|-----|
| **类型** | 整数 |
| **默认值** | `100` (MB) |
| **建议范围** | 10 - 500 MB |
| **说明** | 允许下载的最大视频文件大小 |

**用途**：防止下载过大的视频文件。

**建议**：
- **低配机器** (2GB RAM): 设置为 10-20 MB
- **中等配置** (8GB RAM): 设置为 50-100 MB
- **高配机器** (16GB+ RAM): 设置为 100-500 MB

```toml
# 只允许下载 50MB 以下的视频
video_max_size_mb = 50
```

#### `video_download_timeout`

| 属性 | 值 |
|------|-----|
| **类型** | 整数 |
| **默认值** | `60` (秒) |
| **建议范围** | 30 - 180 秒 |
| **说明** | 视频下载超时时间 |

**用途**：防止卡住等待无法下载的视频。

**建议**：
- **网络较差** (2-5 Mbps): 设置为 120-180 秒
- **网络一般** (5-20 Mbps): 设置为 60-120 秒
- **网络较好** (20+ Mbps): 设置为 30-60 秒

```toml
# 下载超时时间改为 120 秒
video_download_timeout = 120
```

---

## 常见配置场景

### 场景 1：服务器带宽有限

**症状**：群聊消息中经常出现大量视频，导致网络流量爆满。

**解决方案**：
```toml
[napcat_adapter.features]
enable_video_processing = false  # 完全关闭
```

### 场景 2：机器性能较低

**症状**：处理视频消息时 CPU 占用率高，其他功能响应变慢。

**解决方案**：
```toml
[napcat_adapter.features]
enable_video_processing = true
video_max_size_mb = 20         # 限制小视频
video_download_timeout = 30    # 快速超时
```

### 场景 3：特定时间段关闭视频处理

如果需要在特定时间段内关闭视频处理，可以：

1. 修改配置文件
2. 调用 API 重新加载配置（如果支持）

例如：在工作时间关闭，下班后打开。

### 场景 4：保留所有视频处理（默认行为）

```toml
[napcat_adapter.features]
enable_video_processing = true
video_max_size_mb = 100
video_download_timeout = 60
```

---

## 工作原理

### 启用视频处理的流程

```
消息到达
  ↓
检查 enable_video_processing
  ├─ false → 返回 [视频消息] 占位符 ✓
  └─ true  ↓
      检查文件大小
        ├─ > video_max_size_mb → 返回错误信息 ✓
        └─ ≤ video_max_size_mb ↓
            开始下载（最多等待 video_download_timeout 秒）
              ├─ 成功 → 返回视频数据 ✓
              ├─ 超时 → 返回超时错误 ✓
              └─ 失败 → 返回错误信息 ✓
```

### 禁用视频处理的流程

```
消息到达
  ↓
检查 enable_video_processing
  └─ false → 立即返回 [视频消息] 占位符 ✓
           （节省带宽和 CPU）
```

---

## 错误处理

当视频处理出现问题时，用户会看到以下占位符消息：

| 消息 | 含义 |
|------|------|
| `[视频消息]` | 视频处理已禁用或信息不完整 |
| `[视频消息] (文件过大)` | 视频大小超过限制 |
| `[视频消息] (下载失败)` | 网络错误或服务不可用 |
| `[视频消息处理出错]` | 其他异常错误 |

这些占位符确保消息不会因为视频处理失败而导致程序崩溃。

---

## 性能对比

| 配置 | 带宽消耗 | CPU 占用 | 内存占用 | 响应速度 |
|------|----------|---------|---------|----------|
| **禁用** (`false`) | 🟢 极低 | 🟢 极低 | 🟢 极低 | 🟢 极快 |
| **启用，小视频** (≤20MB) | 🟡 中等 | 🟡 中等 | 🟡 中等 | 🟡 一般 |
| **启用，大视频** (≤100MB) | 🔴 较高 | 🔴 较高 | 🔴 较高 | 🔴 较慢 |

---

## 监控和调试

### 检查配置是否生效

启动 bot 后，查看日志中是否有类似信息：

```
[napcat_adapter] 视频下载器已初始化: max_size=100MB, timeout=60s
```

如果看到这条信息，说明配置已成功加载。

### 监控视频处理

当处理视频消息时，日志中会记录：

```
[video_handler] 开始下载视频: https://...
[video_handler] 视频下载成功，大小: 25.50 MB
```

或者：

```
[napcat_adapter] 视频消息处理已禁用，跳过
```

---

## 常见问题

### Q1: 关闭视频处理会影响 AI 的回复吗？

**A**: 不会。AI 仍然能看到 `[视频消息]` 占位符，可以根据上下文判断是否涉及视频内容。

### Q2: 可以为不同群组设置不同的视频处理策略吗？

**A**: 当前版本不支持。所有群组使用相同的配置。如需支持，请在 Issue 或讨论中提出。

### Q3: 视频下载会影响消息处理延迟吗？

**A**: 会。下载大视频可能需要几秒钟。建议：
- 设置合理的 `video_download_timeout`
- 或禁用视频处理以获得最快响应

### Q4: 修改配置后需要重启吗？

**A**: 是的。需要重启 bot 才能应用新配置。

### Q5: 如何快速诊断视频下载问题？

**A**:
1. 检查日志中的错误信息
2. 验证网络连接
3. 检查 `video_max_size_mb` 是否设置过小
4. 尝试增加 `video_download_timeout`

---

## 最佳实践

1. **新用户建议**：先启用视频处理，如果出现性能问题再调整参数或关闭。

2. **生产环境建议**：
   - 定期监控日志中的视频处理错误
   - 根据实际网络和 CPU 情况调整参数
   - 在高峰期可考虑关闭视频处理

3. **开发调试**：
   - 启用日志中的 DEBUG 级别输出
   - 测试各个 `video_max_size_mb` 值的实际表现
   - 检查超时时间是否符合网络条件

---

## 相关链接

- **GitHub Issue #10**: [强烈请求有个开关选择是否下载视频](https://github.com/MoFox-Studio/MoFox-Core/issues/10)
- **配置文件**: `config/bot_config.toml`
- **实现代码**: 
  - `src/plugins/built_in/napcat_adapter/plugin.py`
  - `src/plugins/built_in/napcat_adapter/src/handlers/to_core/message_handler.py`
  - `src/plugins/built_in/napcat_adapter/src/handlers/video_handler.py`

---

## 反馈和建议

如有其他问题或建议，欢迎在 GitHub Issue 中提出。

**版本**: v2.1.0  
**最后更新**: 2025-12-16
