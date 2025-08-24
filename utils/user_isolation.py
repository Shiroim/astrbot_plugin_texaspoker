"""用户隔离机制

提供用户ID隔离功能，确保不同群聊中的用户账户完全隔离。
参考papertrading插件的隔离机制实现。
"""

from typing import Optional, Tuple, Dict, Any, List
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger


class UserIsolation:
    """
    用户隔离工具类
    
    确保同一用户在不同群聊中拥有独立的账户，
    避免跨群聊的数据混乱。
    """
    
    @staticmethod
    def get_isolated_user_id(event: AstrMessageEvent) -> str:
        """
        获取隔离的用户ID，确保不同群聊中的数据隔离
        
        格式: platform:sender_id:session_id
        这样同一用户在不同群聊中会有不同的隔离ID
        
        Args:
            event: 消息事件对象
            
        Returns:
            隔离后的用户ID字符串
        """
        try:
            platform_name = event.get_platform_name() or "unknown"
            sender_id = event.get_sender_id() or "unknown"
            session_id = event.get_session_id() or "unknown"
            
            isolated_id = f"{platform_name}:{sender_id}:{session_id}"
            
            # 记录调试信息
            logger.debug(f"生成隔离用户ID: {isolated_id} (平台:{platform_name}, 用户:{sender_id}, 会话:{session_id})")
            
            return isolated_id
            
        except Exception as e:
            logger.error(f"获取隔离用户ID失败: {e}")
            # 回退方案：使用发送者ID
            fallback_id = event.get_sender_id() or f"fallback_{hash(str(event))}"
            logger.warning(f"使用回退用户ID: {fallback_id}")
            return fallback_id
    
    @staticmethod
    def extract_original_user_id(isolated_user_id: str) -> Optional[str]:
        """
        从隔离的用户ID中提取原始用户ID
        
        Args:
            isolated_user_id: 隔离的用户ID
            
        Returns:
            原始用户ID，如果提取失败则返回None
        """
        try:
            parts = isolated_user_id.split(':')
            if len(parts) >= 2:
                return parts[1]  # sender_id部分
            return None
        except Exception as e:
            logger.error(f"提取原始用户ID失败: {e}")
            return None
    
    @staticmethod
    def get_session_info(isolated_user_id: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        从隔离的用户ID中提取会话信息
        
        Args:
            isolated_user_id: 隔离的用户ID
            
        Returns:
            (平台名, 原始用户ID, 会话ID) 的元组
        """
        try:
            parts = isolated_user_id.split(':')
            if len(parts) >= 3:
                return parts[0], parts[1], parts[2]
            return None, None, None
        except Exception as e:
            logger.error(f"提取会话信息失败: {e}")
            return None, None, None
    
    @staticmethod
    def is_legacy_user_id(user_id: str) -> bool:
        """
        判断是否为旧格式的用户ID（未隔离）
        
        Args:
            user_id: 用户ID
            
        Returns:
            True表示是旧格式，False表示是新的隔离格式
        """
        return ':' not in user_id
    
    @staticmethod
    def create_default_isolated_id(user_id: str, platform: str = "default", session: str = "default") -> str:
        """
        为旧数据创建默认的隔离ID
        
        Args:
            user_id: 原始用户ID
            platform: 默认平台名
            session: 默认会话ID
            
        Returns:
            创建的隔离用户ID
        """
        return f"{platform}:{user_id}:{session}"
