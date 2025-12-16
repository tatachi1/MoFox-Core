"""工具：清空短期记忆存储。

用法：
    python scripts/clear_short_term_memory.py [--remove-file]

- 按配置的数据目录加载短期记忆管理器
- 清空内存缓存并写入空的 short_term_memory.json
- 可选：直接删除存储文件而不是写入空文件
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 让从仓库根目录运行时能够正确导入模块
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.config import global_config  # noqa: E402
from src.memory_graph.short_term_manager import ShortTermMemoryManager  # noqa: E402


def resolve_data_dir() -> Path:
    """从配置解析记忆数据目录，带安全默认值。"""
    memory_cfg = getattr(global_config, "memory", None)
    base_dir = getattr(memory_cfg, "data_dir", "data/memory_graph") if memory_cfg else "data/memory_graph"
    return PROJECT_ROOT / base_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="清空短期记忆 (示例: python scripts/clear_short_term_memory.py --remove-file)"
    )
    parser.add_argument(
        "--remove-file",
        action="store_true",
        help="删除 short_term_memory.json 文件（默认写入空文件）",
    )
    return parser.parse_args()


async def clear_short_term_memories(remove_file: bool = False) -> None:
    data_dir = resolve_data_dir()
    storage_file = data_dir / "short_term_memory.json"

    manager = ShortTermMemoryManager(data_dir=data_dir)
    await manager.initialize()

    removed_count = len(manager.memories)

    # 清空内存状态
    manager.memories.clear()
    manager._memory_id_index.clear()  # 内部索引缓存
    manager._similarity_cache.clear()  # 相似度缓存

    if remove_file and storage_file.exists():
        storage_file.unlink()
        print(f"Removed storage file: {storage_file}")
    else:
        # 写入空文件，保留结构
        await manager._save_to_disk()
        print(f"Wrote empty short-term memory file: {storage_file}")

    print(f"Cleared {removed_count} short-term memories")


async def main() -> None:
    args = parse_args()
    await clear_short_term_memories(remove_file=args.remove_file)


if __name__ == "__main__":
    asyncio.run(main())
