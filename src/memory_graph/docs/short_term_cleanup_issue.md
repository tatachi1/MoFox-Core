# 短期记忆转长期记忆失败问题诊断指南

## 问题概述

运行系统很长一段时间后，发现**没有生成长期记忆**。这不一定是转移机制失败，更可能是**短期记忆被清除而无法转移到长期**。

## 已知问题（暂不修复）

### 冷启动短期记忆超限并触发大批量嵌入计算

现象：
- 启动时短期记忆文件 `short_term_memory.json` 会被完整加载，不裁剪到上限；随后 `_reload_embeddings()` 会为所有缺失向量的短期记忆重新生成嵌入。
- 若持久化数量大于配置上限（默认 30），会被立刻视为“满额”并触发整批转长期；同时两次大批量嵌入调用放大冷启动耗时与成本。

为什么暂不修复：
- 当前行为保证历史短期记忆完整恢复；修改为加载前裁剪或延迟转移可能改变已有用户的数据流转路径，需要进一步评估。

建议的临时规避手段（手工操作，不改代码）：
- 控制 `short_term_memory.json` 大小：定期人工备份并清理低重要性条目，保持条目数不超过上限。
- 如需调高容量，临时在配置将 `short_term_max_memories` 提升到高于现有持久化条目数，待启动完成后再按需调回。

结论：问题已知，但为了避免引入新的行为变更，暂不在代码层修复，后续会在评估后再处理。

## 核心原因分析

### 1. 短期记忆满额触发转移 ✅

系统设计中，当短期记忆数量达到上限时才会触发转移：

```python
# unified_manager.py - _auto_transfer_loop()
if len(self.short_term_manager.memories) >= self.max_memories:
    # 转移全部短期记忆到长期
    result = await self.long_term_manager.transfer_from_short_term(batch)
```

**默认配置：**
- `short_term_max_memories = 30` 条
- 当达到30条时触发转移

**问题：** 如果短期记忆始终 < 30 条，就**永远不会转移**

---

### 2. DISCARD决策直接丢弃 ❌

在短期记忆提取时，LLM可能决策该记忆重复或价值低，直接丢弃：

```python
# short_term_manager.py - _execute_decision()
if decision.operation == ShortTermOperation.DISCARD:
    logger.debug(f"丢弃低价值记忆: {decision.reasoning}")
    return None  # ← 记忆被删除，不进入短期列表
```

**影响：** 即使记忆被提取，也可能在短期阶段就被丢弃，无法积累到30条

**诊断关键词：** 查找日志中的 `"丢弃低价值记忆"`

---

### 3. 转移后清理低重要性记忆 ❌

这是**最隐蔽的陷阱**。当转移完成后，系统会进一步删除低重要性的短期记忆：

```python
# short_term_manager.py - clear_transferred_memories()
if self.overflow_strategy == "transfer_all":
    low_importance_memories = [
        mem for mem in self.memories
        if mem.importance < self.transfer_importance_threshold  # 默认 0.6
    ]
    
    if low_importance_memories:
        # 直接删除，不转移到长期！
        to_delete = {mem.id for mem in low_importance_memories}
        self.memories = [mem for mem in self.memories if mem.id not in to_delete]
        logger.info(f"额外删除了 {len(to_delete)} 条低重要性记忆")
```

**参数影响：**
```python
short_term_transfer_threshold = 0.6  # 重要性阈值
overflow_strategy = "transfer_all"   # 清理策略
```

**问题：** 如果短期记忆重要性都 < 0.6，会被**额外删除而不是转移到长期**

**诊断关键词：** 查找日志中的 `"额外删除了.*条低重要性记忆"`

---

### 4. 强制清理溢出(Overflow Cleanup) ❌

当启用泄压功能且短期记忆超过容量时：

```python
# short_term_manager.py - force_cleanup_overflow()
def force_cleanup_overflow(self, keep_ratio: float | None = None) -> int:
    """当短期记忆超过容量时，强制删除低重要性记忆以泄压"""
    
    if not self.enable_force_cleanup:  # 默认 True
        return 0
    
    current = len(self.memories)
    limit = int(self.max_memories * keep_ratio)  # 30 * 0.9 = 27
    
    if current > limit:
        # 删除最不重要的记忆（不转移！）
        sorted_memories = sorted(self.memories, key=lambda m: (m.importance, m.created_at))
        remove_count = current - limit
        to_remove = {mem.id for mem in sorted_memories[:remove_count]}
        
        self.memories = [mem for mem in self.memories if mem.id not in to_remove]
```

**默认配置：**
```python
short_term_enable_force_cleanup = true       # 泄压功能启用
short_term_cleanup_keep_ratio = 0.9          # 保留90%
```

**问题：** 当短期 > 27 条时，会直接删除最不重要的记忆，**不转移到长期**

**诊断关键词：** 查找日志中的 `"短期记忆压力泄压"`

---

## 四种清理方式对比

| 清理方式 | 触发条件 | 代码位置 | 转移长期？ | 删除规则 | 日志关键词 |
|--------|--------|--------|---------|--------|---------|
| **自动转移** | 短期 ≥ 30 | `_auto_transfer_loop` | ✅ 是 | 全部转移后删除 | `"短期记忆已满"` |
| **DISCARD决策** | LLM决策 | `_execute_decision` | ❌ 否 | 直接丢弃 | `"丢弃低价值记忆"` |
| **溢出泄压** | 短期>max*keep_ratio | `clear_transferred_memories` | ❌ 否 | 删除重要性<0.6 | `"额外删除了.*条低重要性记忆"` |
| **强制清理** | 短期>27且启用 | `force_cleanup_overflow` | ❌ 否 | 删除最不重要的 | `"短期记忆压力泄压"` |

---

## 完整转移流程图

```
感知记忆块 (Perceptual)
    ↓
    通过LLM提取 → 记忆被DISCARD → ❌ 丢弃（不进入短期）
    ↓
短期记忆 (Short-term)
    ↓
    [积累到30条]
    ↓
自动转移循环触发
    ↓
    LLM决策图操作
    ↓
执行图操作 → 创建长期记忆 ✅
    ↓
清除已转移的短期记忆
    ↓
检查：是否有重要性 < 0.6 的记忆？
    ↓ 是
    额外删除（不转移）❌
    ↓ 否
完成 ✅
```

---

## 诊断方法

### 方法1: 查看日志关键词

```bash
# 查找是否有记忆被丢弃
grep "丢弃低价值记忆" logs/app_*.log

# 查找是否有记忆被清理
grep "额外删除了" logs/app_*.log
grep "短期记忆压力泄压" logs/app_*.log

# 查找是否有长期转移发生
grep "短期记忆已满" logs/app_*.log
grep "创建长期记忆" logs/app_*.log
```

### 方法2: 查看内存统计

```python
async def diagnose_short_term_issue():
    """诊断短期记忆问题"""
    
    stats = unified_manager.get_statistics()
    short_term_stats = stats['short_term']
    
    print(f"""
    === 短期记忆诊断 ===
    当前数量: {short_term_stats['total_memories']}
    最大容量: {short_term_stats['max_memories']}
    平均重要性: {short_term_stats['avg_importance']:.2f}
    可转移数量: {short_term_stats['transferable_count']}
    转移阈值: {short_term_stats['transfer_threshold']:.2f}
    """)
    
    # 判断：为什么没有长期记忆？
    if short_term_stats['total_memories'] < short_term_stats['max_memories']:
        print("❌ 原因1: 短期记忆未满，无法触发转移")
        print(f"   需要 {short_term_stats['max_memories'] - short_term_stats['total_memories']} 更多记忆")
    
    if short_term_stats['avg_importance'] < 0.6:
        print("❌ 原因2: 短期记忆重要性太低，会被清理而不是转移")
        print(f"   平均重要性 {short_term_stats['avg_importance']:.2f} < 0.6")
    
    if short_term_stats['transferable_count'] == 0:
        print("❌ 原因3: 没有可转移的记忆")
    
    # 查看长期记忆
    long_term_stats = stats['long_term']
    print(f"\n长期记忆数量: {long_term_stats['total_memories']}")
```

### 方法3: 检查配置

```python
from src.config.config import global_config

print(f"""
=== 内存配置检查 ===
short_term_max_memories: {global_config.memory.short_term_max_memories}
short_term_transfer_threshold: {global_config.memory.short_term_transfer_threshold}
short_term_enable_force_cleanup: {global_config.memory.short_term_enable_force_cleanup}
short_term_cleanup_keep_ratio: {global_config.memory.short_term_cleanup_keep_ratio}
short_term_overflow_strategy: {global_config.memory.short_term_overflow_strategy}
""")
```

---

## 根本原因与解决方案

### 问题1: 短期记忆始终 < 30 条

**根本原因：**
- 对话量不够或记忆提取率低
- LLM决策时DISCARD太多

**解决方案：**

**方案A: 降低转移阈值（推荐）**
```python
# config/bot_config.toml
short_term_max_memories = 10  # 改为10条就转移
```

**方案B: 手动触发转移**
```python
result = await unified_manager.manual_transfer()
```

**方案C: 检查DISCARD情况**
```bash
grep "丢弃低价值记忆" logs/app_*.log | wc -l
# 如果数量很多，说明LLM决策太严格
```

---

### 问题2: 短期记忆被额外清理而不转移

**根本原因：**
- 短期记忆重要性普遍 < 0.6
- LLM在评估重要性时评分过低

**解决方案：**

**方案A: 禁用额外清理（快速修复）**
```python
# config/bot_config.toml
short_term_enable_force_cleanup = false
```

**方案B: 提高转移阈值（允许更低重要性转移）**
```python
# config/bot_config.toml
short_term_transfer_threshold = 0.3  # 改为0.3，只删除特别低的
```

**方案C: 改进LLM评估**
- 检查 `memory_short_term_builder` 模型的提示词
- 确保LLM给出合理的重要性分数（0.0-1.0范围）

---

### 问题3: 强制清理删除了记忆

**根本原因：**
- 短期记忆快速积累超过27条（30 * 0.9）
- 泄压功能激活删除

**解决方案：**

**方案A: 禁用泄压功能**
```python
# config/bot_config.toml
short_term_enable_force_cleanup = false
```

**方案B: 提高保留比例**
```python
# config/bot_config.toml
short_term_cleanup_keep_ratio = 0.95  # 改为保留95%
```

**方案C: 降低转移阈值（更快转移）**
```python
# config/bot_config.toml
short_term_max_memories = 20  # 更早触发转移
```

---

## 推荐配置

### 保守配置（确保记忆转移）

```toml
# config/bot_config.toml

[memory]
short_term_max_memories = 15              # 较早转移
short_term_transfer_threshold = 0.3       # 允许较低重要性转移
short_term_enable_force_cleanup = false   # 禁用泄压
short_term_cleanup_keep_ratio = 0.9       # 保留比例（无效，已禁用）
short_term_overflow_strategy = "transfer_all"
```

**特点：** 会更频繁地转移记忆，确保长期记忆快速积累

### 平衡配置（推荐）

```toml
# config/bot_config.toml

[memory]
short_term_max_memories = 20              # 中等转移频率
short_term_transfer_threshold = 0.4       # 允许低重要性转移
short_term_enable_force_cleanup = false   # 禁用泄压
short_term_cleanup_keep_ratio = 0.9       # 保留比例（无效，已禁用）
short_term_overflow_strategy = "transfer_all"
```

**特点：** 平衡了转移频率和记忆积累

---

## 完整诊断脚本

```python
import asyncio
from src.memory_graph.unified_manager import UnifiedMemoryManager
from src.config.config import global_config

async def full_diagnosis():
    """完整诊断脚本"""
    
    # 初始化
    manager = UnifiedMemoryManager()
    await manager.initialize()
    
    # 1. 获取统计
    stats = manager.get_statistics()
    
    print("\n" + "="*60)
    print("长期记忆转移问题诊断")
    print("="*60)
    
    # 2. 统计信息
    print(f"\n【统计信息】")
    print(f"感知记忆块: {stats['perceptual']['total_blocks']}")
    print(f"短期记忆: {stats['short_term']['total_memories']} / {stats['short_term']['max_memories']}")
    print(f"长期记忆: {stats['long_term']['total_memories']}")
    
    # 3. 关键参数
    print(f"\n【关键参数】")
    print(f"重要性阈值: {stats['short_term']['transfer_threshold']}")
    print(f"平均重要性: {stats['short_term']['avg_importance']:.3f}")
    print(f"可转移数量: {stats['short_term']['transferable_count']}")
    
    # 4. 配置检查
    print(f"\n【配置检查】")
    print(f"force_cleanup: {global_config.memory.short_term_enable_force_cleanup}")
    print(f"cleanup_ratio: {global_config.memory.short_term_cleanup_keep_ratio}")
    print(f"overflow_strategy: {global_config.memory.short_term_overflow_strategy}")
    
    # 5. 诊断逻辑
    print(f"\n【诊断结果】")
    
    stm_count = stats['short_term']['total_memories']
    stm_max = stats['short_term']['max_memories']
    avg_importance = stats['short_term']['avg_importance']
    ltm_count = stats['long_term']['total_memories']
    
    issues = []
    
    # 问题1: 短期未满
    if stm_count < stm_max:
        issues.append(f"❌ 短期记忆未满 ({stm_count}/{stm_max})")
    
    # 问题2: 重要性太低
    if avg_importance < 0.6:
        issues.append(f"❌ 平均重要性过低 ({avg_importance:.3f} < 0.6)")
    
    # 问题3: 没有长期记忆
    if ltm_count == 0:
        issues.append(f"❌ 没有生成长期记忆")
    
    if not issues:
        print("✅ 系统正常，未发现问题")
    else:
        for issue in issues:
            print(issue)
    
    # 6. 建议
    print(f"\n【建议】")
    if not issues:
        print("系统工作正常，继续运行")
    else:
        print("1. 检查日志中的关键词:")
        print("   - '丢弃低价值记忆' → LLM决策过严")
        print("   - '额外删除了' → 清理机制删除了")
        print("   - '短期记忆压力泄压' → 强制清理删除了")
        print("\n2. 建议修改:")
        if stm_count < stm_max:
            print(f"   - 降低 short_term_max_memories 到 {max(5, stm_count//2)}")
        if avg_importance < 0.6:
            print(f"   - 禁用 short_term_enable_force_cleanup")
            print(f"   - 降低 short_term_transfer_threshold 到 0.3")
    
    print("\n" + "="*60 + "\n")

# 运行
if __name__ == "__main__":
    asyncio.run(full_diagnosis())
```

---

## 快速参考

### 日志关键词速查表

| 关键词 | 含义 | 问题 |
|--------|------|------|
| `"丢弃低价值记忆"` | 短期提取时LLM决策丢弃 | DISCARD太多 |
| `"短期记忆已满"` | 触发自动转移 | 正常 ✅ |
| `"创建长期记忆"` | 长期记忆被创建 | 正常 ✅ |
| `"额外删除了.*条低重要性记忆"` | 转移后清理低重要性 | 重要性<0.6被删 |
| `"短期记忆压力泄压"` | 强制清理溢出 | 泄压删除 |

### 参数速查表

| 参数 | 默认值 | 影响 | 建议值 |
|-----|--------|------|--------|
| `short_term_max_memories` | 30 | 转移频率 | 10-20 |
| `short_term_transfer_threshold` | 0.6 | 清理范围 | 0.3-0.4 |
| `short_term_enable_force_cleanup` | true | 泄压开关 | false |
| `short_term_cleanup_keep_ratio` | 0.9 | 保留比例 | 0.95 |

---

## 参考代码位置

- 短期记忆管理: [short_term_manager.py](../short_term_manager.py)
- 统一管理器: [unified_manager.py](../unified_manager.py)
- 长期记忆管理: [long_term_manager.py](../long_term_manager.py)
- 配置文件: [config/bot_config.toml](../../config/bot_config.toml)
