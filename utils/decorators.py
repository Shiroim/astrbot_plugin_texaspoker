"""统一装饰器

提供错误处理、参数验证等通用装饰器
"""
import asyncio
from functools import wraps
from typing import Any, Callable, AsyncGenerator
from .error_handler import GameError, ValidationError
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import logger


def error_handler(operation_name: str):
    """
    统一错误处理装饰器
    
    Args:
        operation_name: 操作名称，用于日志记录
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ValidationError as e:
                logger.warning(f"{operation_name}参数错误: {e}")
                return False, str(e)
            except GameError as e:
                logger.error(f"{operation_name}游戏错误: {e}")
                return False, str(e)
            except Exception as e:
                logger.error(f"{operation_name}失败: {e}")
                return False, f"{operation_name}失败，请稍后重试"
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ValidationError as e:
                logger.warning(f"{operation_name}参数错误: {e}")
                return False, str(e)
            except GameError as e:
                logger.error(f"{operation_name}游戏错误: {e}")
                return False, str(e)
            except Exception as e:
                logger.error(f"{operation_name}失败: {e}")
                return False, f"{operation_name}失败，请稍后重试"
        
        # 根据函数类型返回对应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def command_error_handler(operation_name: str):
    """
    命令处理错误装饰器（用于AstrBot命令处理）
    
    Args:
        operation_name: 操作名称，用于日志记录
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, event: AstrMessageEvent, *args, **kwargs) -> AsyncGenerator[MessageEventResult, None]:
            try:
                async for result in func(self, event, *args, **kwargs):
                    yield result
            except ValidationError as e:
                logger.warning(f"{operation_name}参数错误: {e}")
                error_msg = [
                    f"❌ {operation_name}失败",
                    "",
                    f"🔍 错误原因: 参数错误",
                    f"📝 详细信息: {str(e)}",
                    "",
                    "💡 请检查输入参数并重试"
                ]
                yield event.plain_result("\n".join(error_msg))
            except GameError as e:
                logger.error(f"{operation_name}游戏错误: {e}")
                error_msg = [
                    f"❌ {operation_name}失败",
                    "",
                    f"🔍 错误原因: 游戏逻辑错误",
                    f"📝 详细信息: {str(e)}",
                    "",
                    "💡 请检查游戏状态并重试"
                ]
                yield event.plain_result("\n".join(error_msg))
            except Exception as e:
                logger.error(f"{operation_name}失败: {e}")
                error_msg = [
                    f"❌ {operation_name}失败",
                    "",
                    "🔍 错误原因: 系统异常",
                    "",
                    "💡 请稍后重试，如问题持续请联系管理员"
                ]
                yield event.plain_result("\n".join(error_msg))
        return wrapper
    return decorator


def validate_params(func: Callable) -> Callable:
    """
    参数验证装饰器
    
    检查函数参数的基本有效性
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        # 基本参数验证
        for key, value in kwargs.items():
            if key.endswith('_id') and (not value or not isinstance(value, str)):
                raise ValidationError(f"参数 {key} 必须是有效的字符串")
            if key.endswith('_amount') and (not isinstance(value, int) or value <= 0):
                raise ValidationError(f"参数 {key} 必须是正整数")
        
        return await func(*args, **kwargs)
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        # 基本参数验证
        for key, value in kwargs.items():
            if key.endswith('_id') and (not value or not isinstance(value, str)):
                raise ValidationError(f"参数 {key} 必须是有效的字符串")
            if key.endswith('_amount') and (not isinstance(value, int) or value <= 0):
                raise ValidationError(f"参数 {key} 必须是正整数")
        
        return func(*args, **kwargs)
    
    # 根据函数类型返回对应的包装器
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """
    重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 重试延迟（秒）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"第{attempt + 1}次尝试失败，{delay}秒后重试: {e}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"所有重试都失败了: {e}")
                        break
            
            raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            import time
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"第{attempt + 1}次尝试失败，{delay}秒后重试: {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"所有重试都失败了: {e}")
                        break
            
            raise last_exception
        
        # 根据函数类型返回对应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def timeout_handler(timeout_seconds: float = 30.0):
    """
    超时处理装饰器
    
    Args:
        timeout_seconds: 超时时间（秒）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logger.error(f"操作超时: {func.__name__}")
                raise GameError("操作超时", f"{func.__name__} 在 {timeout_seconds} 秒内未完成")
        
        return wrapper
    return decorator
