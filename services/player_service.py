"""玩家管理服务

提供玩家注册、查询、更新等功能
"""
import time
from typing import Dict, Any, Optional, Tuple
from ..utils.data_storage import DataStorage
from ..models.game import Player
from astrbot.api import logger


class PlayerService:
    """玩家管理服务"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    def register_player(self, user_id: str, nickname: str, initial_chips: int) -> Tuple[bool, str]:
        """
        注册新玩家
        
        Args:
            user_id: 用户ID
            nickname: 用户昵称  
            initial_chips: 初始筹码
            
        Returns:
            Tuple[成功标志, 消息]
        """
        try:
            # 检查玩家是否已存在
            existing_player = self.storage.get_player(user_id)
            if existing_player:
                return False, f"{nickname} 已经注册过了"
            
            # 创建新玩家记录（所有筹码金额以K为单位存储）
            player_data = {
                'user_id': user_id,
                'nickname': nickname,
                'total_chips': initial_chips,       # 银行总筹码 (K为单位)
                'total_winnings': 0,                # 累计盈利 (K为单位)
                'games_played': 0,                  # 参与游戏局数
                'hands_won': 0,                     # 获胜手数
                'total_buyin': 0,                   # 累计买入金额 (K为单位)
                'created_at': int(time.time()),     # 注册时间
                'last_played': int(time.time()),    # 最后游戏时间
                'currency_unit': 'K'                # 货币单位标识
            }
            
            # 保存玩家数据
            self.storage.save_player(user_id, player_data)
            
            logger.info(f"新玩家注册: {nickname} (ID: {user_id}), 初始筹码: {initial_chips}")
            return True, f"玩家 {nickname} 注册成功"
            
        except Exception as e:
            logger.error(f"注册玩家时发生错误: {e}")
            return False, "注册失败，请稍后重试"
    
    def get_or_create_player(self, user_id: str, nickname: str, default_chips: int) -> Player:
        """
        获取玩家或创建新玩家
        
        Args:
            user_id: 用户ID
            nickname: 用户昵称
            default_chips: 默认筹码数
            
        Returns:
            Player对象
        """
        # 尝试获取已存在的玩家
        player_data = self.storage.get_player(user_id)
        
        if player_data:
            # 玩家已存在，使用存储的数据创建Player对象
            return Player(
                user_id=user_id,
                nickname=nickname,
                chips=player_data.get('total_chips', default_chips),
                total_winnings=player_data.get('total_winnings', 0),
                games_played=player_data.get('games_played', 0),
                hands_won=player_data.get('hands_won', 0)
            )
        else:
            # 新玩家，自动注册
            success, message = self.register_player(user_id, nickname, default_chips)
            if success:
                logger.info(f"自动注册新玩家: {nickname}")
            
            return Player(
                user_id=user_id,
                nickname=nickname,
                chips=default_chips
            )
    
    def update_player_after_game(self, player: Player, chips_change: int, 
                                games_increment: int = 1, hands_won_increment: int = 0) -> None:
        """
        游戏结束后更新玩家统计数据
        
        Args:
            player: 玩家对象
            chips_change: 筹码变化（可以是负数）
            games_increment: 游戏局数增加
            hands_won_increment: 获胜手数增加
        """
        try:
            # 更新玩家对象数据
            player.total_winnings += chips_change
            player.games_played += games_increment
            player.hands_won += hands_won_increment
            
            # 更新存储中的数据
            self.storage.update_player_stats(
                player.user_id,
                player.nickname,
                chips_change=chips_change,
                games_played=games_increment,
                hands_won=hands_won_increment
            )
            
            logger.debug(f"玩家 {player.nickname} 数据已更新")
            
        except Exception as e:
            logger.error(f"更新玩家数据失败 {player.nickname}: {e}")
    
    def get_player_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取玩家信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            玩家信息字典，不存在返回None
        """
        return self.storage.get_player(user_id)
    
    def is_player_registered(self, user_id: str) -> bool:
        """
        检查玩家是否已注册
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否已注册
        """
        return self.storage.get_player(user_id) is not None
    
    def get_player_chips(self, user_id: str) -> int:
        """
        获取玩家当前筹码数
        
        Args:
            user_id: 用户ID
            
        Returns:
            筹码数，未注册玩家返回0
        """
        player_data = self.storage.get_player(user_id)
        if player_data:
            return player_data.get('total_chips', 0)
        return 0
    
    def update_player_chips(self, user_id: str, new_chips: int) -> bool:
        """
        更新玩家筹码数
        
        Args:
            user_id: 用户ID
            new_chips: 新的筹码数 (K为单位)
            
        Returns:
            是否更新成功
        """
        try:
            player_data = self.storage.get_player(user_id)
            if player_data:
                player_data['total_chips'] = new_chips
                player_data['last_played'] = int(time.time())
                self.storage.save_player(user_id, player_data)
                return True
            return False
        except Exception as e:
            logger.error(f"更新玩家筹码失败: {e}")
            return False
    
    def process_buyin(self, user_id: str, nickname: str, buyin_amount: int) -> Tuple[bool, str, int]:
        """
        处理玩家买入操作
        
        Args:
            user_id: 用户ID
            nickname: 用户昵称
            buyin_amount: 买入金额 (K为单位)
            
        Returns:
            Tuple[是否成功, 消息, 剩余银行资金]
        """
        try:
            player_data = self.storage.get_player(user_id)
            if not player_data:
                return False, f"{nickname} 未注册，请先使用 /德州注册", 0
            
            current_chips = player_data.get('total_chips', 0)
            
            # 检查资金是否足够
            if current_chips < buyin_amount:
                return False, f"资金不足！银行余额: {current_chips}K，需要买入: {buyin_amount}K", current_chips
            
            # 扣除买入金额
            new_chips = current_chips - buyin_amount
            player_data['total_chips'] = new_chips
            player_data['total_buyin'] = player_data.get('total_buyin', 0) + buyin_amount
            player_data['last_played'] = int(time.time())
            
            # 保存数据
            self.storage.save_player(user_id, player_data)
            
            logger.info(f"玩家 {nickname} 买入成功: {buyin_amount}K，剩余: {new_chips}K")
            return True, "买入成功", new_chips
            
        except Exception as e:
            logger.error(f"处理买入失败: {e}")
            return False, "买入处理失败，请稍后重试", 0
    
    def process_cashout(self, user_id: str, nickname: str, cashout_amount: int) -> Tuple[bool, str]:
        """
        处理玩家兑现操作（游戏结束后将筹码返回银行）
        
        Args:
            user_id: 用户ID
            nickname: 用户昵称
            cashout_amount: 兑现金额 (K为单位)
            
        Returns:
            Tuple[是否成功, 消息]
        """
        try:
            player_data = self.storage.get_player(user_id)
            if not player_data:
                return False, f"{nickname} 玩家数据不存在"
            
            # 将筹码添加回银行
            current_chips = player_data.get('total_chips', 0)
            new_chips = current_chips + cashout_amount
            player_data['total_chips'] = new_chips
            player_data['last_played'] = int(time.time())
            
            # 保存数据
            self.storage.save_player(user_id, player_data)
            
            logger.info(f"玩家 {nickname} 兑现成功: {cashout_amount}K，银行余额: {new_chips}K")
            return True, f"兑现成功，银行余额: {new_chips}K"
            
        except Exception as e:
            logger.error(f"处理兑现失败: {e}")
            return False, "兑现处理失败"
    
    def can_buyin(self, user_id: str, buyin_amount: int) -> Tuple[bool, str]:
        """
        检查玩家是否可以买入指定金额
        
        Args:
            user_id: 用户ID
            buyin_amount: 买入金额 (K为单位)
            
        Returns:
            Tuple[是否可以买入, 消息]
        """
        player_data = self.storage.get_player(user_id)
        if not player_data:
            return False, "玩家未注册，请先使用 /德州注册"
        
        current_chips = player_data.get('total_chips', 0)
        if current_chips < buyin_amount:
            return False, f"资金不足！银行余额: {current_chips}K，需要: {buyin_amount}K"
        
        return True, "可以买入"
