"""兴趣值计算组件管理器

管理兴趣值计算组件的生命周期，确保系统只能有一个兴趣值计算组件实例运行
"""

import asyncio
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.plugin_system.base.base_interest_calculator import BaseInterestCalculator, InterestCalculationResult

if TYPE_CHECKING:
    from src.common.data_models.database_data_model import DatabaseMessages

logger = get_logger("interest_manager")


class InterestManager:
    """兴趣值计算组件管理器"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._current_calculator: BaseInterestCalculator | None = None
            self._calculator_lock = asyncio.Lock()
            self._last_calculation_time = 0.0
            self._total_calculations = 0
            self._failed_calculations = 0
            self._calculation_queue = asyncio.Queue()
            self._worker_task = None
            self._shutdown_event = asyncio.Event()

            # 性能优化相关字段
            self._result_cache: OrderedDict[str, InterestCalculationResult] = OrderedDict()  # LRU缓存
            self._cache_max_size = 1000  # 最大缓存数量
            self._cache_ttl = 300  # 缓存TTL（秒）
            self._batch_queue: asyncio.Queue = asyncio.Queue(maxsize=100)  # 批处理队列
            self._batch_size = 10  # 批处理大小
            self._batch_timeout = 0.1  # 批处理超时（秒）
            self._batch_task = None
            self._is_warmed_up = False  # 预热状态标记

            # 性能统计
            self._cache_hits = 0
            self._cache_misses = 0
            self._batch_calculations = 0
            self._total_calculation_time = 0.0

            self._initialized = True

    async def initialize(self):
        """初始化管理器"""
        # 启动批处理工作线程
        if self._batch_task is None or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._batch_processing_worker())
            logger.info("批处理工作线程已启动")

    async def shutdown(self):
        """关闭管理器"""
        self._shutdown_event.set()

        # 取消批处理任务
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass

        if self._current_calculator:
            await self._current_calculator.cleanup()
            self._current_calculator = None

        # 清理缓存
        self._result_cache.clear()

        logger.info("兴趣值管理器已关闭")

    async def register_calculator(self, calculator: BaseInterestCalculator) -> bool:
        """注册兴趣值计算组件（系统只能有一个活跃的兴趣值计算器）

        Args:
            calculator: 兴趣值计算组件实例

        Returns:
            bool: 注册是否成功
        """
        async with self._calculator_lock:
            try:
                # 检查是否已有相同的计算器
                if self._current_calculator and self._current_calculator.component_name == calculator.component_name:
                    logger.warning(f"兴趣值计算组件 {calculator.component_name} 已经注册，跳过重复注册")
                    return True

                # 如果已有组件在运行，先清理并替换
                if self._current_calculator:
                    logger.info(
                        f"替换现有兴趣值计算组件: {self._current_calculator.component_name} -> {calculator.component_name}"
                    )
                    await self._current_calculator.cleanup()
                else:
                    logger.info(f"注册新的兴趣值计算组件: {calculator.component_name}")

                # 初始化新组件
                if await calculator.initialize():
                    self._current_calculator = calculator
                    logger.info(f"兴趣值计算组件注册成功: {calculator.component_name} v{calculator.component_version}")
                    return True
                else:
                    logger.error(f"兴趣值计算组件初始化失败: {calculator.component_name}")
                    return False

            except Exception as e:
                logger.error(f"注册兴趣值计算组件失败: {e}")
                return False

    async def calculate_interest(self, message: "DatabaseMessages", timeout: float | None = None, use_cache: bool = True) -> InterestCalculationResult:
        """计算消息兴趣值（优化版，支持缓存）

        Args:
            message: 数据库消息对象
            timeout: 最大等待时间（秒），超时则使用默认值返回；为None时不设置超时
            use_cache: 是否使用缓存，默认True

        Returns:
            InterestCalculationResult: 计算结果或默认结果
        """
        if not self._current_calculator:
            # 返回默认结果
            return InterestCalculationResult(
                success=False,
                message_id=getattr(message, "message_id", ""),
                interest_value=0.3,
                error_message="没有可用的兴趣值计算组件",
            )

        message_id = getattr(message, "message_id", "")

        # 缓存查询
        if use_cache and message_id:
            cached_result = self._get_from_cache(message_id)
            if cached_result is not None:
                self._cache_hits += 1
                logger.debug(f"命中缓存: {message_id}, 兴趣值: {cached_result.interest_value:.3f}")
                return cached_result
            self._cache_misses += 1

        # 使用 create_task 异步执行计算
        task = asyncio.create_task(self._async_calculate(message))

        if timeout is None:
            result = await task
        else:
            try:
                # 等待计算结果，但有超时限制
                result = await asyncio.wait_for(task, timeout=timeout)
            except asyncio.TimeoutError:
                # 超时返回默认结果，但计算仍在后台继续
                logger.warning(f"兴趣值计算超时 ({timeout}s)，消息 {message_id} 使用默认兴趣值 0.5")
                return InterestCalculationResult(
                    success=True,
                    message_id=message_id,
                    interest_value=0.5,  # 固定默认兴趣值
                    should_reply=False,
                    should_act=False,
                    error_message=f"计算超时({timeout}s)，使用默认值",
                )
            except Exception as e:
                # 发生异常，返回默认结果
                logger.error(f"兴趣值计算异常: {e}")
                return InterestCalculationResult(
                    success=False,
                    message_id=message_id,
                    interest_value=0.3,
                    error_message=f"计算异常: {e!s}",
                )

        # 缓存结果
        if use_cache and result.success and message_id:
            self._put_to_cache(message_id, result)

        return result

    async def _async_calculate(self, message: "DatabaseMessages") -> InterestCalculationResult:
        """异步执行兴趣值计算"""
        start_time = time.time()
        self._total_calculations += 1

        if not self._current_calculator:
            return InterestCalculationResult(
                success=False,
                message_id=getattr(message, "message_id", ""),
                interest_value=0.0,
                error_message="没有可用的兴趣值计算组件",
                calculation_time=time.time() - start_time,
            )

        try:
            # 使用组件的安全执行方法
            result = await self._current_calculator._safe_execute(message)

            if result.success:
                self._last_calculation_time = time.time()
                self._total_calculation_time += result.calculation_time
                logger.debug(f"兴趣值计算完成: {result.interest_value:.3f} (耗时: {result.calculation_time:.3f}s)")
            else:
                self._failed_calculations += 1
                logger.warning(f"兴趣值计算失败: {result.error_message}")

            return result

        except Exception as e:
            self._failed_calculations += 1
            calc_time = time.time() - start_time
            self._total_calculation_time += calc_time
            logger.error(f"兴趣值计算异常: {e}")
            return InterestCalculationResult(
                success=False,
                message_id=getattr(message, "message_id", ""),
                interest_value=0.0,
                error_message=f"计算异常: {e!s}",
                calculation_time=calc_time,
            )

    async def _calculation_worker(self):
        """计算工作线程（预留用于批量处理）"""
        while not self._shutdown_event.is_set():
            try:
                # 等待计算任务或关闭信号
                await asyncio.wait_for(self._calculation_queue.get(), timeout=1.0)

                # 处理计算任务
                # 这里可以实现批量处理逻辑

            except asyncio.TimeoutError:
                # 超时继续循环
                continue
            except asyncio.CancelledError:
                # 任务被取消，退出循环
                break
            except Exception as e:
                logger.error(f"计算工作线程异常: {e}")

    def _get_from_cache(self, message_id: str) -> InterestCalculationResult | None:
        """从缓存中获取结果（LRU策略）"""
        if message_id not in self._result_cache:
            return None

        # 检查TTL
        result = self._result_cache[message_id]
        if time.time() - result.timestamp > self._cache_ttl:
            # 过期，删除
            del self._result_cache[message_id]
            return None

        # 更新访问顺序（LRU）
        self._result_cache.move_to_end(message_id)
        return result

    def _put_to_cache(self, message_id: str, result: InterestCalculationResult):
        """将结果放入缓存（LRU策略）"""
        # 如果已存在，更新
        if message_id in self._result_cache:
            self._result_cache.move_to_end(message_id)

        self._result_cache[message_id] = result

        # 限制缓存大小
        while len(self._result_cache) > self._cache_max_size:
            # 删除最旧的项
            self._result_cache.popitem(last=False)

    async def calculate_interest_batch(self, messages: list["DatabaseMessages"], timeout: float | None = None) -> list[InterestCalculationResult]:
        """批量计算消息兴趣值（并发优化）
        
        Args:
            messages: 消息列表
            timeout: 单个计算的超时时间
            
        Returns:
            list[InterestCalculationResult]: 计算结果列表
        """
        if not messages:
            return []

        # 并发计算所有消息
        tasks = [self.calculate_interest(msg, timeout=timeout) for msg in messages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"批量计算消息 {i} 失败: {result}")
                final_results.append(InterestCalculationResult(
                    success=False,
                    message_id=getattr(messages[i], "message_id", ""),
                    interest_value=0.3,
                    error_message=f"批量计算异常: {result!s}",
                ))
            else:
                final_results.append(result)

        self._batch_calculations += 1
        return final_results

    async def _batch_processing_worker(self):
        """批处理工作线程"""
        while not self._shutdown_event.is_set():
            batch = []
            deadline = time.time() + self._batch_timeout

            try:
                # 收集批次
                while len(batch) < self._batch_size and time.time() < deadline:
                    remaining_time = deadline - time.time()
                    if remaining_time <= 0:
                        break

                    try:
                        item = await asyncio.wait_for(self._batch_queue.get(), timeout=remaining_time)
                        batch.append(item)
                    except asyncio.TimeoutError:
                        break

                # 处理批次
                if batch:
                    await self._process_batch(batch)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"批处理工作线程异常: {e}")

    async def _process_batch(self, batch: list):
        """处理批次消息"""
        # 这里可以实现具体的批处理逻辑
        # 当前版本只是占位，实际的批处理逻辑可以根据具体需求实现
        pass

    async def warmup(self, sample_messages: list["DatabaseMessages"] | None = None):
        """预热兴趣计算器
        
        Args:
            sample_messages: 样本消息列表，用于预热。如果为None，则只初始化计算器
        """
        if not self._current_calculator:
            logger.warning("无法预热：没有可用的兴趣值计算组件")
            return

        logger.info("开始预热兴趣值计算器...")
        start_time = time.time()

        # 如果提供了样本消息，进行预热计算
        if sample_messages:
            try:
                # 批量计算样本消息
                await self.calculate_interest_batch(sample_messages, timeout=5.0)
                logger.info(f"预热完成：处理了 {len(sample_messages)} 条样本消息，耗时 {time.time() - start_time:.2f}s")
            except Exception as e:
                logger.error(f"预热过程中出现异常: {e}")
        else:
            logger.info(f"预热完成：计算器已就绪，耗时 {time.time() - start_time:.2f}s")

        self._is_warmed_up = True

    def clear_cache(self):
        """清空缓存"""
        cleared_count = len(self._result_cache)
        self._result_cache.clear()
        logger.info(f"已清空 {cleared_count} 条缓存记录")

    def set_cache_config(self, max_size: int | None = None, ttl: int | None = None):
        """设置缓存配置
        
        Args:
            max_size: 最大缓存数量
            ttl: 缓存生存时间（秒）
        """
        if max_size is not None:
            self._cache_max_size = max_size
            logger.info(f"缓存最大容量设置为: {max_size}")

        if ttl is not None:
            self._cache_ttl = ttl
            logger.info(f"缓存TTL设置为: {ttl}秒")

        # 如果当前缓存超过新的最大值，清理旧数据
        if max_size is not None:
            while len(self._result_cache) > self._cache_max_size:
                self._result_cache.popitem(last=False)

    def get_current_calculator(self) -> BaseInterestCalculator | None:
        """获取当前活跃的兴趣值计算组件"""
        return self._current_calculator

    def get_statistics(self) -> dict:
        """获取管理器统计信息"""
        success_rate = 1.0 - (self._failed_calculations / max(1, self._total_calculations))
        cache_hit_rate = self._cache_hits / max(1, self._cache_hits + self._cache_misses)
        avg_calc_time = self._total_calculation_time / max(1, self._total_calculations)

        stats = {
            "manager_statistics": {
                "total_calculations": self._total_calculations,
                "failed_calculations": self._failed_calculations,
                "success_rate": success_rate,
                "last_calculation_time": self._last_calculation_time,
                "current_calculator": self._current_calculator.component_name if self._current_calculator else None,
                "cache_hit_rate": cache_hit_rate,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_size": len(self._result_cache),
                "batch_calculations": self._batch_calculations,
                "average_calculation_time": avg_calc_time,
                "is_warmed_up": self._is_warmed_up,
            }
        }

        # 添加当前组件的统计信息
        if self._current_calculator:
            stats["calculator_statistics"] = self._current_calculator.get_statistics()

        return stats

    async def health_check(self) -> bool:
        """健康检查"""
        if not self._current_calculator:
            return False

        try:
            # 检查组件是否还活跃
            return self._current_calculator.is_enabled
        except Exception:
            return False

    def has_calculator(self) -> bool:
        """检查是否有可用的计算组件"""
        return self._current_calculator is not None and self._current_calculator.is_enabled

    async def adaptive_optimize(self):
        """自适应优化：根据性能统计自动调整参数"""
        if not self._current_calculator:
            return

        stats = self.get_statistics()["manager_statistics"]

        # 根据缓存命中率调整缓存大小
        cache_hit_rate = stats["cache_hit_rate"]
        if cache_hit_rate < 0.5 and self._cache_max_size < 5000:
            # 命中率低，增加缓存容量
            new_size = min(self._cache_max_size * 2, 5000)
            logger.info(f"自适应优化：缓存命中率较低 ({cache_hit_rate:.2%})，扩大缓存容量 {self._cache_max_size} -> {new_size}")
            self._cache_max_size = new_size
        elif cache_hit_rate > 0.9 and self._cache_max_size > 100:
            # 命中率高，可以适当减小缓存
            new_size = max(self._cache_max_size // 2, 100)
            logger.info(f"自适应优化：缓存命中率很高 ({cache_hit_rate:.2%})，缩小缓存容量 {self._cache_max_size} -> {new_size}")
            self._cache_max_size = new_size
            # 清理多余缓存
            while len(self._result_cache) > self._cache_max_size:
                self._result_cache.popitem(last=False)

        # 根据平均计算时间调整批处理参数
        avg_calc_time = stats["average_calculation_time"]
        if avg_calc_time > 0.5 and self._batch_size < 50:
            # 计算较慢，增加批次大小以提高吞吐量
            new_batch_size = min(self._batch_size * 2, 50)
            logger.info(f"自适应优化：平均计算时间较长 ({avg_calc_time:.3f}s)，增加批次大小 {self._batch_size} -> {new_batch_size}")
            self._batch_size = new_batch_size
        elif avg_calc_time < 0.1 and self._batch_size > 5:
            # 计算较快，可以减小批次
            new_batch_size = max(self._batch_size // 2, 5)
            logger.info(f"自适应优化：平均计算时间较短 ({avg_calc_time:.3f}s)，减小批次大小 {self._batch_size} -> {new_batch_size}")
            self._batch_size = new_batch_size

    def get_performance_report(self) -> str:
        """生成性能报告"""
        stats = self.get_statistics()["manager_statistics"]

        report = [
            "=" * 60,
            "兴趣值管理器性能报告",
            "=" * 60,
            f"总计算次数: {stats['total_calculations']}",
            f"失败次数: {stats['failed_calculations']}",
            f"成功率: {stats['success_rate']:.2%}",
            f"缓存命中率: {stats['cache_hit_rate']:.2%}",
            f"缓存命中: {stats['cache_hits']}",
            f"缓存未命中: {stats['cache_misses']}",
            f"当前缓存大小: {stats['cache_size']} / {self._cache_max_size}",
            f"批量计算次数: {stats['batch_calculations']}",
            f"平均计算时间: {stats['average_calculation_time']:.4f}s",
            f"是否已预热: {'是' if stats['is_warmed_up'] else '否'}",
            f"当前计算器: {stats['current_calculator'] or '无'}",
            "=" * 60,
        ]

        # 添加计算器统计
        if self._current_calculator:
            calc_stats = self.get_statistics()["calculator_statistics"]
            report.extend([
                "",
                "计算器统计:",
                f"  组件名称: {calc_stats['component_name']}",
                f"  版本: {calc_stats['component_version']}",
                f"  已启用: {calc_stats['enabled']}",
                f"  总计算: {calc_stats['total_calculations']}",
                f"  失败: {calc_stats['failed_calculations']}",
                f"  成功率: {calc_stats['success_rate']:.2%}",
                f"  平均耗时: {calc_stats['average_calculation_time']:.4f}s",
                "=" * 60,
            ])

        return "\n".join(report)


# 全局实例
_interest_manager = None


def get_interest_manager() -> InterestManager:
    """获取兴趣值管理器实例"""
    global _interest_manager
    if _interest_manager is None:
        _interest_manager = InterestManager()
    return _interest_manager
