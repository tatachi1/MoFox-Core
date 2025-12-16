import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.memory_graph.manager_singleton import get_unified_memory_manager
from src.common.logger import get_logger

logger = get_logger("memory_transfer_check")


def print_section(title: str):
    """打印分节标题"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


async def check_short_term_status():
    """检查短期记忆状态"""
    print_section("1. 短期记忆状态检查")
    
    manager = get_unified_memory_manager()
    short_term = manager.short_term_manager
    
    # 获取统计信息
    stats = short_term.get_statistics()
    
    print(f"📊 当前记忆数量: {stats['total_memories']}/{stats['max_memories']}")
    
    # 计算占用率
    if stats['max_memories'] > 0:
        occupancy = stats['total_memories'] / stats['max_memories']
        print(f"📈 容量占用率: {occupancy:.1%}")
        
        # 根据占用率给出建议
        if occupancy >= 1.0:
            print("⚠️  警告：已达到容量上限！应该触发紧急转移")
        elif occupancy >= 0.5:
            print("✅ 占用率超过50%，符合自动转移条件")
        else:
            print(f"ℹ️  占用率未达到50%阈值，当前 {occupancy:.1%}")
    
    print(f"🎯 可转移记忆数: {stats['transferable_count']}")
    print(f"📏 转移重要性阈值: {stats['transfer_threshold']}")
    
    return stats


async def check_transfer_candidates():
    """检查当前可转移的候选记忆"""
    print_section("2. 转移候选记忆分析")
    
    manager = get_unified_memory_manager()
    short_term = manager.short_term_manager
    
    # 获取转移候选
    candidates = short_term.get_memories_for_transfer()
    
    print(f"🎫 当前转移候选: {len(candidates)} 条\n")
    
    if not candidates:
        print("❌ 没有记忆符合转移条件！")
        print("\n可能原因：")
        print("  1. 所有记忆的重要性都低于阈值")
        print("  2. 短期记忆数量未超过容量限制")
        print("  3. 短期记忆列表为空")
        return []
    
    # 显示前5条候选的详细信息
    print("前 5 条候选记忆：\n")
    for i, mem in enumerate(candidates[:5], 1):
        print(f"{i}. 记忆ID: {mem.id[:8]}...")
        print(f"   重要性: {mem.importance:.3f}")
        print(f"   内容: {mem.content[:50]}...")
        print(f"   创建时间: {mem.created_at}")
        print()
    
    if len(candidates) > 5:
        print(f"... 还有 {len(candidates) - 5} 条候选记忆\n")
    
    # 分析重要性分布
    importance_levels = {
        "高 (>=0.8)": sum(1 for m in candidates if m.importance >= 0.8),
        "中 (0.6-0.8)": sum(1 for m in candidates if 0.6 <= m.importance < 0.8),
        "低 (<0.6)": sum(1 for m in candidates if m.importance < 0.6),
    }
    
    print("📊 重要性分布：")
    for level, count in importance_levels.items():
        print(f"  {level}: {count} 条")
    
    return candidates


async def check_auto_transfer_task():
    """检查自动转移任务状态"""
    print_section("3. 自动转移任务状态")
    
    manager = get_unified_memory_manager()
    
    # 检查任务是否存在
    if not hasattr(manager, '_auto_transfer_task') or manager._auto_transfer_task is None:
        print("❌ 自动转移任务未创建！")
        print("\n建议：调用 manager.initialize() 初始化系统")
        return False
    
    task = manager._auto_transfer_task
    
    # 检查任务状态
    if task.done():
        print("❌ 自动转移任务已结束！")
        try:
            exception = task.exception()
            if exception:
                print(f"\n任务异常: {exception}")
        except:
            pass
        print("\n建议：重启系统或手动重启任务")
        return False
    
    print("✅ 自动转移任务正在运行")
    
    # 检查转移缓存
    if hasattr(manager, '_transfer_cache'):
        cache_size = len(manager._transfer_cache) if manager._transfer_cache else 0
        print(f"📦 转移缓存: {cache_size} 条记忆")
    
    # 检查上次转移时间
    if hasattr(manager, '_last_transfer_time'):
        from datetime import datetime
        last_time = manager._last_transfer_time
        if last_time:
            time_diff = (datetime.now() - last_time).total_seconds()
            print(f"⏱️  距上次转移: {time_diff:.1f} 秒前")
    
    return True


async def check_long_term_status():
    """检查长期记忆状态"""
    print_section("4. 长期记忆图谱状态")
    
    manager = get_unified_memory_manager()
    long_term = manager.long_term_manager
    
    # 获取图谱统计
    stats = long_term.get_statistics()
    
    print(f"👥 人物节点数: {stats.get('person_count', 0)}")
    print(f"📅 事件节点数: {stats.get('event_count', 0)}")
    print(f"🔗 关系边数: {stats.get('edge_count', 0)}")
    print(f"💾 向量存储数: {stats.get('vector_count', 0)}")
    
    return stats


async def manual_transfer_test():
    """手动触发转移测试"""
    print_section("5. 手动转移测试")
    
    manager = get_unified_memory_manager()
    
    # 询问用户是否执行
    print("⚠️  即将手动触发一次记忆转移")
    print("这将把当前符合条件的短期记忆转移到长期记忆")
    response = input("\n是否继续? (y/n): ").strip().lower()
    
    if response != 'y':
        print("❌ 已取消手动转移")
        return None
    
    print("\n🚀 开始手动转移...")
    
    try:
        # 执行手动转移
        result = await manager.manual_transfer()
        
        print("\n✅ 转移完成！")
        print(f"\n转移结果：")
        print(f"  已处理: {result.get('processed_count', 0)} 条")
        print(f"  成功转移: {len(result.get('transferred_memory_ids', []))} 条")
        print(f"  失败: {result.get('failed_count', 0)} 条")
        print(f"  跳过: {result.get('skipped_count', 0)} 条")
        
        if result.get('errors'):
            print(f"\n错误信息：")
            for error in result['errors'][:3]:  # 只显示前3个错误
                print(f"  - {error}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ 转移失败: {e}")
        logger.exception("手动转移失败")
        return None


async def check_configuration():
    """检查相关配置"""
    print_section("6. 配置参数检查")
    
    from src.config.config import global_config
    
    config = global_config.memory
    
    print("📋 当前配置：")
    print(f"  短期记忆容量: {config.short_term_max_memories}")
    print(f"  转移重要性阈值: {config.short_term_transfer_threshold}")
    print(f"  批量转移大小: {config.long_term_batch_size}")
    print(f"  自动转移间隔: {config.long_term_auto_transfer_interval} 秒")
    print(f"  启用泄压清理: {config.short_term_enable_force_cleanup}")
    
    # 给出配置建议
    print("\n💡 配置建议：")
    
    if config.short_term_transfer_threshold > 0.6:
        print("  ⚠️  转移阈值较高(>0.6)，可能导致记忆难以转移")
        print("     建议：降低到 0.4-0.5")
    
    if config.long_term_batch_size > 10:
        print("  ⚠️  批量大小较大(>10)，可能延迟转移触发")
        print("     建议：设置为 5-10")
    
    if config.long_term_auto_transfer_interval > 300:
        print("  ⚠️  转移间隔较长(>5分钟)，可能导致转移不及时")
        print("     建议：设置为 60-180 秒")


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  MoFox-Bot 记忆转移诊断工具")
    print("=" * 60)
    
    try:
        # 初始化管理器
        print("\n⚙️  正在初始化记忆管理器...")
        manager = get_unified_memory_manager()
        await manager.initialize()
        print("✅ 初始化完成\n")
        
        # 执行各项检查
        await check_short_term_status()
        candidates = await check_transfer_candidates()
        task_running = await check_auto_transfer_task()
        await check_long_term_status()
        await check_configuration()
        
        # 综合诊断
        print_section("7. 综合诊断结果")
        
        issues = []
        
        if not candidates:
            issues.append("❌ 没有符合条件的转移候选")
        
        if not task_running:
            issues.append("❌ 自动转移任务未运行")
        
        if issues:
            print("🚨 发现以下问题：\n")
            for issue in issues:
                print(f"  {issue}")
            
            print("\n建议操作：")
            print("  1. 检查短期记忆的重要性评分是否合理")
            print("  2. 降低配置中的转移阈值")
            print("  3. 查看日志文件排查错误")
            print("  4. 尝试手动触发转移测试")
        else:
            print("✅ 系统运行正常，转移机制已就绪")
            
            if candidates:
                print(f"\n当前有 {len(candidates)} 条记忆等待转移")
                print("转移将在满足以下任一条件时自动触发：")
                print("  • 转移缓存达到批量大小")
                print("  • 短期记忆占用率超过 50%")
                print("  • 距上次转移超过最大延迟")
                print("  • 短期记忆达到容量上限")
        
        # 询问是否手动触发转移
        if candidates:
            print()
            await manual_transfer_test()
        
        print_section("检查完成")
        print("详细诊断报告: docs/memory_transfer_diagnostic_report.md")
        
    except Exception as e:
        print(f"\n❌ 检查过程出错: {e}")
        logger.exception("检查脚本执行失败")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
