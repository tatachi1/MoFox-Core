"""数据库操作装饰器

提供常用的装饰器：
- @retry: 自动重试失败的数据库操作
- @timeout: 为数据库操作添加超时控制
- @cached: 自动缓存函数结果
"""

import asyncio
import functools
import hashlib
import time
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLTimeoutError

from src.common.logger import get_logger

logger = get_logger("database.decorators")


def generate_cache_key(
    key_prefix: str,
    *args: Any,
    **kwargs: Any,
) -> str:
    """生成与@cached装饰器相同的缓存键

    用于手动缓存失效等操作

    Args:
        key_prefix: 缓存键前缀
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        缓存键字符串

    Example:
        cache_key = generate_cache_key("person_info", platform, person_id)
        await cache.delete(cache_key)
    """
    cache_key_parts = [key_prefix]

    if args:
        args_str = ",".join(str(arg) for arg in args)
        args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:8]
        cache_key_parts.append(f"args:{args_hash}")

    if kwargs:
        kwargs_str = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        kwargs_hash = hashlib.sha256(kwargs_str.encode()).hexdigest()[:8]
        cache_key_parts.append(f"kwargs:{kwargs_hash}")

    return ":".join(cache_key_parts)


P = ParamSpec("P")
R = TypeVar("R")


def retry(
    max_attempts: int = 3,
    delay: float = 0.5,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (OperationalError, DBAPIError, SQLTimeoutError),
):
    """重试装饰器

    自动重试失败的数据库操作，适用于临时性错误

    Args:
        max_attempts: 最大尝试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟倍数（指数退避）
        exceptions: 需要重试的异常类型

    Example:
        async def query_data():
            return await session.execute(stmt)
    """

    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"{func.__name__} 失败 (尝试 {attempt}/{max_attempts}): {e}. "
                            f"等待 {current_delay:.2f}s 后重试..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"{func.__name__} 在 {max_attempts} 次尝试后仍然失败: {e}",
                            exc_info=True,
                        )

            # 所有尝试都失败
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Retry failed after {max_attempts} attempts")

        return wrapper

    return decorator


def timeout(seconds: float):
    """超时装饰器

    为数据库操作添加超时控制

    Args:
        seconds: 超时时间（秒）

    Example:
        @timeout(30.0)
        async def long_query():
            return await session.execute(complex_stmt)
    """

    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.error(f"{func.__name__} 执行超时 (>{seconds}s)")
                raise TimeoutError(f"{func.__name__} 执行超时 (>{seconds}s)")

        return wrapper

    return decorator


def cached(
    ttl: int | None = 600,
    key_prefix: str | None = None,
    use_args: bool = True,
    use_kwargs: bool = True,
):
    """缓存装饰器

    自动缓存函数返回值

    Args:
        ttl: 缓存过期时间（秒），None表示永不过期
        key_prefix: 缓存键前缀，默认使用函数名
        use_args: 是否将位置参数包含在缓存键中
        use_kwargs: 是否将关键字参数包含在缓存键中

    Example:
        @cached(ttl=60, key_prefix="user_data")
        async def get_user_info(user_id: str) -> dict:
            return await query_user(user_id)
    """

    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # 延迟导入避免循环依赖
            from src.common.database.optimization import get_cache

            # 生成缓存键
            cache_key_parts = [key_prefix or func.__name__]

            if use_args and args:
                # 将位置参数转换为字符串
                args_str = ",".join(str(arg) for arg in args)
                args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:8]
                cache_key_parts.append(f"args:{args_hash}")

            if use_kwargs and kwargs:
                # 将关键字参数转换为字符串（排序以保证一致性）
                kwargs_str = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                kwargs_hash = hashlib.sha256(kwargs_str.encode()).hexdigest()[:8]
                cache_key_parts.append(f"kwargs:{kwargs_hash}")

            cache_key = ":".join(cache_key_parts)

            # 尝试从缓存获取
            cache = await get_cache()
            cached_result = await cache.get(cache_key)

            if cached_result is not None:
                return cached_result

            # 执行函数
            result = await func(*args, **kwargs)

            # 写入缓存，传递自定义TTL参数
            await cache.set(cache_key, result, ttl=ttl)
            if ttl is not None:
                logger.debug(f"缓存写入: {cache_key} (TTL={ttl}s)")
            else:
                logger.debug(f"缓存写入: {cache_key} (使用默认TTL)")

            return result

        return wrapper

    return decorator


def measure_time(log_slow: float | None = None, operation_name: str | None = None):
    """性能测量装饰器

    测量函数执行时间，可选择性记录慢查询并集成到监控系统

    Args:
        log_slow: 慢查询阈值（秒），None 表示使用配置中的阈值，0 表示禁用
        operation_name: 操作名称，用于监控统计，None 表示使用函数名

    Example:
        @measure_time(log_slow=1.0)
        async def complex_query():
            return await session.execute(stmt)
        
        @measure_time()  # 使用配置的阈值
        async def database_query():
            return await session.execute(stmt)
    """

    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            from src.common.database.utils.monitoring import get_monitor

            # 确定操作名称
            op_name = operation_name or func.__name__

            start_time = time.perf_counter()
            success = False

            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            finally:
                elapsed = time.perf_counter() - start_time

                # 获取监控器
                monitor = get_monitor()

                # 记录到监控系统
                if success:
                    monitor.record_operation(op_name, elapsed, success=True)

                    # 只在监控启用时检查慢查询
                    if monitor.is_enabled():
                        # 判断是否为慢查询
                        threshold = log_slow
                        if threshold is None:
                            # 使用配置中的阈值
                            threshold = monitor.get_metrics().slow_query_threshold

                        if threshold > 0 and elapsed > threshold:
                            logger.warning(
                                f"🐢 {func.__name__} 执行缓慢: {elapsed:.3f}s (阈值: {threshold:.3f}s)"
                            )
                        else:
                            logger.debug(f"{func.__name__} 执行时间: {elapsed:.3f}s")
                    else:
                        logger.debug(f"{func.__name__} 执行时间: {elapsed:.3f}s")
                else:
                    monitor.record_operation(op_name, elapsed, success=False)

        return wrapper

    return decorator


def transactional(auto_commit: bool = True, auto_rollback: bool = True):
    """事务装饰器

    自动管理事务的提交和回滚

    Args:
        auto_commit: 是否自动提交
        auto_rollback: 发生异常时是否自动回滚

    Example:
        @transactional()
        async def update_multiple_records(session):
            await session.execute(stmt1)
            await session.execute(stmt2)

    Note:
        函数需要接受session参数
    """

    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # 查找session参数
            from sqlalchemy.ext.asyncio import AsyncSession

            session: AsyncSession | None = None
            if args:
                for arg in args:
                    if isinstance(arg, AsyncSession):
                        session = arg
                        break

            if not session and "session" in kwargs:
                possible_session = kwargs["session"]
                if isinstance(possible_session, AsyncSession):
                    session = possible_session

            if not session:
                logger.warning(f"{func.__name__} 未找到session参数，跳过事务管理")
                return await func(*args, **kwargs)

            try:
                result = await func(*args, **kwargs)

                if auto_commit:
                    await session.commit()
                    logger.debug(f"{func.__name__} 事务已提交")

                return result

            except Exception as e:
                if auto_rollback:
                    await session.rollback()
                    logger.error(f"{func.__name__} 事务已回滚: {e}")
                raise

        return wrapper

    return decorator


# 组合装饰器示例
def db_operation(
    retry_attempts: int = 3,
    timeout_seconds: float | None = None,
    cache_ttl: int | None = None,
    measure: bool = True,
):
    """组合装饰器

    组合多个装饰器，提供完整的数据库操作保护

    Args:
        retry_attempts: 重试次数
        timeout_seconds: 超时时间
        cache_ttl: 缓存时间
        measure: 是否测量性能

    Example:
        @db_operation(retry_attempts=3, timeout_seconds=30, cache_ttl=60)
        async def important_query():
            return await complex_operation()
    """

    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        # 从内到外应用装饰器
        wrapped = func

        if measure:
            wrapped = measure_time(log_slow=1.0)(wrapped)

        if cache_ttl:
            wrapped = cached(ttl=cache_ttl)(wrapped)

        if timeout_seconds:
            wrapped = timeout(timeout_seconds)(wrapped)

        if retry_attempts > 1:
            wrapped = retry(max_attempts=retry_attempts)(wrapped)

        return wrapped

    return decorator
