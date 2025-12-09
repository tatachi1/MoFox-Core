# 数据库缓存系统使用指南

## 概述

MoFox Bot 数据库系统集成了可插拔的缓存架构，支持多种缓存后端：

- **内存缓存（Memory）**: 多级 LRU 缓存，适合单机部署
- **Redis 缓存**: 分布式缓存，适合多实例部署或需要持久化缓存的场景

## 缓存后端选择

在 `bot_config.toml` 中配置：

```toml
[database]
enable_database_cache = true  # 是否启用缓存
cache_backend = "memory"      # 缓存后端: "memory" 或 "redis"
```

### 后端对比

| 特性 | 内存缓存 (memory) | Redis 缓存 (redis) |
|------|-------------------|-------------------|
| 部署复杂度 | 低（无额外依赖） | 中（需要 Redis 服务） |
| 分布式支持 | ❌ | ✅ |
| 持久化 | ❌ | ✅ |
| 性能 | 极高（本地内存） | 高（网络开销） |
| 适用场景 | 单机部署 | 多实例/集群部署 |

---

## 内存缓存架构

### 多级缓存（Multi-Level Cache）

- **L1 缓存（热数据）**
  - 容量：1000 项（可配置）
  - TTL：300 秒（可配置）
  - 用途：最近访问的热点数据

- **L2 缓存（温数据）**
  - 容量：10000 项（可配置）
  - TTL：1800 秒（可配置）
  - 用途：较常访问但不是最热的数据

### LRU 驱逐策略

两级缓存都使用 LRU（Least Recently Used）算法：
- 缓存满时自动驱逐最少使用的项
- 保证最常用数据始终在缓存中

---

## Redis 缓存架构

### 特性

- **分布式**: 多个 Bot 实例可共享缓存
- **持久化**: Redis 支持 RDB/AOF 持久化
- **TTL 管理**: 使用 Redis 原生过期机制
- **模式删除**: 支持通配符批量删除缓存
- **原子操作**: 支持 INCR/DECR 等原子操作

### 配置参数

```toml
[database]
# Redis缓存配置（cache_backend = "redis" 时生效）
redis_host = "localhost"          # Redis服务器地址
redis_port = 6379                 # Redis服务器端口
redis_password = ""               # Redis密码（留空表示无密码）
redis_db = 0                      # Redis数据库编号 (0-15)
redis_key_prefix = "mofox:"       # 缓存键前缀
redis_default_ttl = 600           # 默认过期时间（秒）
redis_connection_pool_size = 10   # 连接池大小
```

### 安装 Redis 依赖

```bash
pip install redis
```

---

## 使用方法

### 1. 使用 @cached 装饰器（推荐）

最简单的方式，自动适配所有缓存后端：

```python
from src.common.database.utils.decorators import cached

@cached(ttl=600, key_prefix="person_info")
async def get_person_info(platform: str, person_id: str):
    """获取人员信息（带10分钟缓存）"""
    return await _person_info_crud.get_by(
        platform=platform,
        person_id=person_id,
    )
```

#### 参数说明

- `ttl`: 缓存过期时间（秒），None 表示永不过期
- `key_prefix`: 缓存键前缀，用于命名空间隔离
- `use_args`: 是否将位置参数包含在缓存键中（默认 True）
- `use_kwargs`: 是否将关键字参数包含在缓存键中（默认 True）

### 2. 手动缓存管理

需要更精细控制时，可以手动管理缓存：

```python
from src.common.database.optimization import get_cache

async def custom_query():
    cache = await get_cache()
    
    # 尝试从缓存获取
    result = await cache.get("my_key")
    if result is not None:
        return result
    
    # 缓存未命中，执行查询
    result = await execute_database_query()
    
    # 写入缓存（可指定自定义 TTL）
    await cache.set("my_key", result, ttl=300)
    
    return result
```

### 3. 使用 get_or_load 方法

简化的缓存加载模式：

```python
cache = await get_cache()

# 自动处理：缓存命中返回，未命中则执行 loader 并缓存结果
result = await cache.get_or_load(
    "my_key",
    loader=lambda: fetch_data_from_db(),
    ttl=600
)
```

### 4. 缓存失效

更新数据后需要主动使缓存失效：

```python
from src.common.database.optimization import get_cache
from src.common.database.utils.decorators import generate_cache_key

async def update_person_affinity(platform: str, person_id: str, affinity_delta: float):
    # 执行更新
    await _person_info_crud.update(person.id, {"affinity": new_affinity})
    
    # 使缓存失效
    cache = await get_cache()
    cache_key = generate_cache_key("person_info", platform, person_id)
    await cache.delete(cache_key)
```

---

## 已缓存的查询

### PersonInfo（人员信息）

- **函数**: `get_or_create_person()`
- **缓存时间**: 10 分钟
- **缓存键**: `person_info:args:<hash>`
- **失效时机**: `update_person_affinity()` 更新好感度时

### UserRelationships（用户关系）

- **函数**: `get_user_relationship()`
- **缓存时间**: 5 分钟
- **缓存键**: `user_relationship:args:<hash>`
- **失效时机**: `update_relationship_affinity()` 更新关系时

### ChatStreams（聊天流）

- **函数**: `get_or_create_chat_stream()`
- **缓存时间**: 5 分钟
- **缓存键**: `chat_stream:args:<hash>`
- **失效时机**: 流更新时（如有需要）

## 缓存统计

### 内存缓存统计

```python
cache = await get_cache()
stats = await cache.get_stats()

if cache.backend_type == "memory":
    print(f"L1: {stats['l1'].item_count}项, 命中率 {stats['l1'].hit_rate:.2%}")
    print(f"L2: {stats['l2'].item_count}项, 命中率 {stats['l2'].hit_rate:.2%}")
```

### Redis 缓存统计

```python
if cache.backend_type == "redis":
    print(f"命中率: {stats['hit_rate']:.2%}")
    print(f"键数量: {stats['key_count']}")
```

### 检查当前后端类型

```python
from src.common.database.optimization import get_cache_backend_type

backend = get_cache_backend_type()  # "memory" 或 "redis"
```

---

## 最佳实践

### 1. 选择合适的 TTL

- **频繁变化的数据**: 60-300 秒（如在线状态）
- **中等变化的数据**: 300-600 秒（如用户信息、关系）
- **稳定数据**: 600-1800 秒（如配置、元数据）

### 2. 缓存键设计

- 使用有意义的前缀：`person_info:`, `user_rel:`, `chat_stream:`
- 确保唯一性：包含所有查询参数
- 避免键冲突：使用 `generate_cache_key()` 辅助函数

### 3. 及时失效

- **写入时失效**: 数据更新后立即删除缓存
- **批量失效**: 使用通配符或前缀批量删除相关缓存
- **惰性失效**: 依赖 TTL 自动过期（适用于非关键数据）

### 4. 监控缓存效果

定期检查缓存统计：

- 命中率 > 70% - 缓存效果良好 ✅
- 命中率 50-70% - 可以优化 TTL 或缓存策略 ⚠️
- 命中率 < 50% - 考虑是否需要缓存该查询 ❌

---

## 性能提升数据

基于测试结果：

- **PersonInfo 查询**: 缓存命中时减少 **90%+** 数据库访问
- **关系查询**: 高频场景下减少 **80%+** 数据库连接
- **聊天流查询**: 活跃会话期间减少 **75%+** 重复查询

## 注意事项

1. **缓存一致性**: 更新数据后务必使缓存失效
2. **内存占用**: 监控缓存大小，避免占用过多内存
3. **序列化**: 缓存的对象需要可序列化
   - 内存缓存：直接存储 Python 对象
   - Redis 缓存：默认使用 JSON，复杂对象自动回退到 Pickle
4. **并发安全**: 两种后端都是协程安全的
5. **无自动回退**: Redis 连接失败时会抛出异常，不会自动回退到内存缓存（确保配置正确）

---

## 故障排除

### 缓存未生效

1. 检查 `enable_database_cache = true`
2. 检查是否正确导入装饰器
3. 确认 TTL 设置合理
4. 查看日志中的缓存消息

### 数据不一致

1. 检查更新操作是否正确使缓存失效
2. 确认缓存键生成逻辑一致
3. 考虑缩短 TTL 时间

### 内存占用过高（内存缓存）

1. 检查缓存统计中的项数
2. 调整 L1/L2 缓存大小
3. 缩短 TTL 加快驱逐

### Redis 连接失败

1. 检查 Redis 服务是否运行
2. 确认连接参数（host/port/password）
3. 检查防火墙/网络设置
4. 查看日志中的错误信息

---

## 扩展阅读

- [缓存后端抽象](../src/common/database/optimization/cache_backend.py)
- [内存缓存实现](../src/common/database/optimization/cache_manager.py)
- [Redis 缓存实现](../src/common/database/optimization/redis_cache.py)
- [缓存装饰器](../src/common/database/utils/decorators.py)
