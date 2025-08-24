"""消息服务抽象层

提供跨平台的消息发送抽象，解决平台耦合问题
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple
from astrbot.api.star import Context
from astrbot.api import logger


class MessageServiceInterface(ABC):
    """消息服务接口"""
    
    @abstractmethod
    async def send_private_text(self, user_id: str, text: str) -> bool:
        """发送私聊文本消息"""
        pass
    
    @abstractmethod
    async def send_private_image(self, user_id: str, text: str, image_path: str) -> bool:
        """发送私聊图片消息"""
        pass
    
    @abstractmethod 
    async def send_group_text(self, group_id: str, text: str) -> bool:
        """发送群聊文本消息"""
        pass
    
    @abstractmethod
    async def send_group_image(self, group_id: str, image_path: str) -> bool:
        """发送群聊图片消息"""
        pass


class UniversalMessageService(MessageServiceInterface):
    """通用消息服务实现
    
    自动检测平台并选择合适的发送方式
    """
    
    def __init__(self, context: Context):
        self.context = context
        self.platform_adapters: Dict[str, Any] = {}
        self._init_platform_adapters()
    
    def _init_platform_adapters(self):
        """初始化平台适配器"""
        try:
            if hasattr(self.context, 'platform_manager'):
                for adapter in self.context.platform_manager.get_insts():
                    platform_name = adapter.meta().name.lower()
                    self.platform_adapters[platform_name] = adapter
                    logger.debug(f"注册平台适配器: {platform_name}")
        except Exception as e:
            logger.warning(f"初始化平台适配器失败: {e}")
    
    async def send_private_text(self, user_id: str, text: str) -> bool:
        """发送私聊文本消息"""
        try:
            # 尝试检测平台类型
            platform = self._detect_platform_from_user_id(user_id)
            if platform:
                return await self._send_private_text_to_platform(platform, user_id, text)
            
            # 如果无法检测平台，尝试所有可用的平台
            for platform_name, adapter in self.platform_adapters.items():
                try:
                    if await self._send_private_text_to_platform(platform_name, user_id, text):
                        return True
                except Exception as e:
                    logger.debug(f"平台 {platform_name} 发送私聊失败: {e}")
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"发送私聊文本失败: {e}")
            return False
    
    async def send_private_image(self, user_id: str, text: str, image_path: str) -> bool:
        """发送私聊图片消息"""
        try:
            platform = self._detect_platform_from_user_id(user_id)
            if platform:
                return await self._send_private_image_to_platform(platform, user_id, text, image_path)
            
            # 尝试所有平台
            for platform_name, adapter in self.platform_adapters.items():
                try:
                    if await self._send_private_image_to_platform(platform_name, user_id, text, image_path):
                        return True
                except Exception as e:
                    logger.debug(f"平台 {platform_name} 发送私聊图片失败: {e}")
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"发送私聊图片失败: {e}")
            return False
    
    async def send_group_text(self, group_id: str, text: str) -> bool:
        """发送群聊文本消息"""
        try:
            platform = self._detect_platform_from_group_id(group_id)
            if platform:
                return await self._send_group_text_to_platform(platform, group_id, text)
            
            # 尝试所有平台
            for platform_name, adapter in self.platform_adapters.items():
                try:
                    if await self._send_group_text_to_platform(platform_name, group_id, text):
                        return True
                except Exception as e:
                    logger.debug(f"平台 {platform_name} 发送群聊失败: {e}")
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"发送群聊文本失败: {e}")
            return False
    
    async def send_group_image(self, group_id: str, image_path: str) -> bool:
        """发送群聊图片消息"""
        try:
            platform = self._detect_platform_from_group_id(group_id)
            if platform:
                return await self._send_group_image_to_platform(platform, group_id, image_path)
            
            # 尝试所有平台
            for platform_name, adapter in self.platform_adapters.items():
                try:
                    if await self._send_group_image_to_platform(platform_name, group_id, image_path):
                        return True
                except Exception as e:
                    logger.debug(f"平台 {platform_name} 发送群聊图片失败: {e}")
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"发送群聊图片失败: {e}")
            return False
    
    def _detect_platform_from_user_id(self, user_id: str) -> Optional[str]:
        """从用户ID检测平台类型"""
        try:
            # 基于用户隔离ID格式: platform:sender_id:session_id
            if ':' in user_id:
                parts = user_id.split(':')
                if len(parts) >= 3:
                    return parts[0].lower()
            return None
        except Exception:
            return None
    
    def _detect_platform_from_group_id(self, group_id: str) -> Optional[str]:
        """从群组ID检测平台类型"""
        # 群组ID的检测逻辑可能需要根据实际情况调整
        return self._detect_platform_from_user_id(group_id)
    
    async def _send_private_text_to_platform(self, platform: str, user_id: str, text: str) -> bool:
        """向指定平台发送私聊文本"""
        adapter = self.platform_adapters.get(platform)
        if not adapter:
            return False
        
        try:
            # 提取真实的用户ID
            real_user_id = self._extract_real_user_id(user_id)
            
            if platform == "aiocqhttp":
                # QQ平台
                user_id_int = int(real_user_id)
                await adapter.bot.send_private_msg(user_id=user_id_int, message=text)
                return True
            elif platform in ["weixin", "wechat"]:
                # 微信平台
                await adapter.client.post_text(real_user_id, text)
                return True
            elif platform == "discord":
                # Discord平台
                user = await adapter.bot.fetch_user(int(real_user_id))
                await user.send(text)
                return True
            else:
                # 通用方法
                if hasattr(adapter, 'send_private_message'):
                    await adapter.send_private_message(real_user_id, text)
                    return True
            
        except Exception as e:
            logger.error(f"平台 {platform} 发送私聊文本失败: {e}")
            
        return False
    
    async def _send_private_image_to_platform(self, platform: str, user_id: str, text: str, image_path: str) -> bool:
        """向指定平台发送私聊图片"""
        adapter = self.platform_adapters.get(platform)
        if not adapter:
            return False
        
        try:
            real_user_id = self._extract_real_user_id(user_id)
            
            if platform == "aiocqhttp":
                # QQ平台
                user_id_int = int(real_user_id)
                message = [
                    {"type": "text", "data": {"text": text}},
                    {"type": "image", "data": {"file": f"file:///{image_path}"}}
                ]
                await adapter.bot.send_private_msg(user_id=user_id_int, message=message)
                return True
            elif platform in ["weixin", "wechat"]:
                # 微信平台
                await adapter.client.post_text(real_user_id, text)
                with open(image_path, 'rb') as f:
                    await adapter.client.post_image(real_user_id, f.read())
                return True
            elif platform == "discord":
                # Discord平台
                user = await adapter.bot.fetch_user(int(real_user_id))
                with open(image_path, 'rb') as f:
                    from discord import File
                    file = File(f, filename="poker_hand.png")
                    await user.send(content=text, file=file)
                return True
            else:
                # 通用方法
                if hasattr(adapter, 'send_private_image'):
                    await adapter.send_private_image(real_user_id, text, image_path)
                    return True
                    
        except Exception as e:
            logger.error(f"平台 {platform} 发送私聊图片失败: {e}")
            
        return False
    
    async def _send_group_text_to_platform(self, platform: str, group_id: str, text: str) -> bool:
        """向指定平台发送群聊文本"""
        adapter = self.platform_adapters.get(platform)
        if not adapter:
            return False
        
        try:
            real_group_id = self._extract_real_group_id(group_id)
            
            if platform == "aiocqhttp":
                # QQ平台
                group_id_int = int(real_group_id)
                await adapter.bot.send_group_msg(group_id=group_id_int, message=text)
                return True
            elif platform in ["weixin", "wechat"]:
                # 微信平台
                await adapter.client.post_text(real_group_id, text)
                return True
            elif platform == "discord":
                # Discord平台
                channel = adapter.bot.get_channel(int(real_group_id))
                if channel:
                    await channel.send(text)
                    return True
            else:
                # 通用方法
                if hasattr(adapter, 'send_group_message'):
                    await adapter.send_group_message(real_group_id, text)
                    return True
                    
        except Exception as e:
            logger.error(f"平台 {platform} 发送群聊文本失败: {e}")
            
        return False
    
    async def _send_group_image_to_platform(self, platform: str, group_id: str, image_path: str) -> bool:
        """向指定平台发送群聊图片"""
        adapter = self.platform_adapters.get(platform)
        if not adapter:
            return False
        
        try:
            real_group_id = self._extract_real_group_id(group_id)
            
            if platform == "aiocqhttp":
                # QQ平台
                group_id_int = int(real_group_id)
                message = {"type": "image", "data": {"file": f"file:///{image_path}"}}
                await adapter.bot.send_group_msg(group_id=group_id_int, message=message)
                return True
            elif platform in ["weixin", "wechat"]:
                # 微信平台
                with open(image_path, 'rb') as f:
                    await adapter.client.post_image(real_group_id, f.read())
                return True
            elif platform == "discord":
                # Discord平台
                channel = adapter.bot.get_channel(int(real_group_id))
                if channel:
                    with open(image_path, 'rb') as f:
                        from discord import File
                        file = File(f, filename="poker_game.png")
                        await channel.send(file=file)
                    return True
            else:
                # 通用方法
                if hasattr(adapter, 'send_group_image'):
                    await adapter.send_group_image(real_group_id, image_path)
                    return True
                    
        except Exception as e:
            logger.error(f"平台 {platform} 发送群聊图片失败: {e}")
            
        return False
    
    def _extract_real_user_id(self, isolated_user_id: str) -> str:
        """从隔离用户ID中提取真实用户ID"""
        try:
            if ':' in isolated_user_id:
                parts = isolated_user_id.split(':')
                if len(parts) >= 3:
                    return parts[1]  # sender_id部分
            return isolated_user_id
        except Exception:
            return isolated_user_id
    
    def _extract_real_group_id(self, group_id: str) -> str:
        """从群组ID中提取真实群组ID"""
        # 可能需要根据实际的群组ID格式调整
        return self._extract_real_user_id(group_id)
    
    async def send_hand_cards_to_players(self, players: List[Dict[str, Any]], hand_images: Dict[str, str]) -> Dict[str, bool]:
        """批量发送手牌图片给玩家
        
        Args:
            players: 玩家列表，包含user_id和nickname
            hand_images: 手牌图片路径字典，key为user_id
            
        Returns:
            发送结果字典，key为user_id，value为是否成功
        """
        results = {}
        
        # 并行发送所有手牌
        tasks = []
        for player in players:
            user_id = player['user_id']
            nickname = player['nickname']
            
            if user_id in hand_images:
                text = f"🃏 {nickname}，您的手牌："
                image_path = hand_images[user_id]
                
                task = asyncio.create_task(
                    self._send_hand_card_with_result(user_id, nickname, text, image_path)
                )
                tasks.append((user_id, task))
        
        # 等待所有任务完成
        for user_id, task in tasks:
            try:
                results[user_id] = await task
            except Exception as e:
                logger.error(f"发送手牌给 {user_id} 失败: {e}")
                results[user_id] = False
        
        return results
    
    async def _send_hand_card_with_result(self, user_id: str, nickname: str, text: str, image_path: str) -> bool:
        """发送手牌并返回结果"""
        try:
            success = await self.send_private_image(user_id, text, image_path)
            if success:
                logger.info(f"手牌已发送给 {nickname}")
            else:
                logger.warning(f"手牌发送失败: {nickname}")
            return success
        except Exception as e:
            logger.error(f"发送手牌异常 {nickname}: {e}")
            return False


class MockMessageService(MessageServiceInterface):
    """模拟消息服务（用于测试）"""
    
    def __init__(self):
        self.sent_messages = []
    
    async def send_private_text(self, user_id: str, text: str) -> bool:
        self.sent_messages.append({
            'type': 'private_text',
            'user_id': user_id,
            'text': text
        })
        logger.debug(f"模拟发送私聊文本给 {user_id}: {text[:50]}...")
        return True
    
    async def send_private_image(self, user_id: str, text: str, image_path: str) -> bool:
        self.sent_messages.append({
            'type': 'private_image', 
            'user_id': user_id,
            'text': text,
            'image_path': image_path
        })
        logger.debug(f"模拟发送私聊图片给 {user_id}: {image_path}")
        return True
    
    async def send_group_text(self, group_id: str, text: str) -> bool:
        self.sent_messages.append({
            'type': 'group_text',
            'group_id': group_id,
            'text': text
        })
        logger.debug(f"模拟发送群聊文本到 {group_id}: {text[:50]}...")
        return True
    
    async def send_group_image(self, group_id: str, image_path: str) -> bool:
        self.sent_messages.append({
            'type': 'group_image',
            'group_id': group_id,
            'image_path': image_path
        })
        logger.debug(f"模拟发送群聊图片到 {group_id}: {image_path}")
        return True
