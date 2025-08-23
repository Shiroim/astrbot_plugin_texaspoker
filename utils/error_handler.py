"""错误处理工具类

提供统一的错误处理和日志记录功能
"""
from functools import wraps
from typing import Any, AsyncGenerator, Callable
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import logger


class ErrorHandler:
    """统一错误处理器"""
    
    @staticmethod
    def game_command_error_handler(operation_name: str):
        """
        游戏命令错误处理装饰器
        
        Args:
            operation_name: 操作名称，用于日志记录
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(self, event: AstrMessageEvent, *args, **kwargs) -> AsyncGenerator[MessageEventResult, None]:
                try:
                    async for result in func(self, event, *args, **kwargs):
                        yield result
                except ValueError as e:
                    logger.warning(f"{operation_name}参数错误: {e}")
                    yield event.plain_result(f"参数错误: {str(e)}")
                except Exception as e:
                    logger.error(f"{operation_name}失败: {e}")
                    yield event.plain_result("系统错误，请稍后重试")
            return wrapper
        return decorator
    
    @staticmethod
    def validate_positive_int(value: int, name: str) -> None:
        """
        验证正整数
        
        Args:
            value: 要验证的值
            name: 参数名称
            
        Raises:
            ValueError: 如果值不是正整数
        """
        if value is not None and value <= 0:
            raise ValueError(f"{name}必须大于0")
    
    @staticmethod
    def validate_blind_relation(small_blind: int, big_blind: int) -> None:
        """
        验证盲注关系
        
        Args:
            small_blind: 小盲注
            big_blind: 大盲注
            
        Raises:
            ValueError: 如果大盲注不大于小盲注
        """
        if small_blind is not None and big_blind is not None and big_blind <= small_blind:
            raise ValueError("大盲注必须大于小盲注")


class GameValidation:
    """游戏逻辑验证器"""
    
    @staticmethod
    def validate_game_creation_params(small_blind: int, big_blind: int) -> None:
        """
        验证游戏创建参数
        
        Args:
            small_blind: 小盲注
            big_blind: 大盲注
            
        Raises:
            ValueError: 参数无效时抛出
        """
        ErrorHandler.validate_positive_int(small_blind, "小盲注")
        ErrorHandler.validate_positive_int(big_blind, "大盲注")
        ErrorHandler.validate_blind_relation(small_blind, big_blind)
    
    @staticmethod
    def validate_raise_amount(amount: int, min_bet: int = 1) -> None:
        """
        验证加注金额
        
        Args:
            amount: 加注金额 (K为单位)
            min_bet: 最小下注金额 (K为单位)
            
        Raises:
            ValueError: 金额无效时抛出
        """
        if amount is None or amount <= 0:
            raise ValueError("请输入有效的加注金额")
        
        if amount < min_bet:
            raise ValueError(f"加注金额过少，最少需要 {min_bet}K")


class ResponseMessages:
    """标准响应消息"""
    
    # 成功消息
    REGISTRATION_SUCCESS = "🎉 {nickname} 注册成功！\n💰 获得初始资金: {chips} 筹码"
    GAME_CREATION_SUCCESS = "{message}\n小盲注: {small_blind}\n大盲注: {big_blind}\n使用 /德州加入 来加入游戏"
    
    # 错误消息
    ALREADY_REGISTERED = "{nickname}，您已经注册过了！\n当前总筹码: {chips}"
    SYSTEM_ERROR = "系统错误，请稍后重试"
    INVALID_RAISE_AMOUNT = "请输入有效的加注金额，例如：/加注 100"
    
    # 参数错误消息
    SMALL_BLIND_POSITIVE = "小盲注必须大于0"
    BIG_BLIND_POSITIVE = "大盲注必须大于0"
    BIG_BLIND_GREATER = "大盲注必须大于小盲注"
