"""游戏状态和玩家数据模型

提供德州扑克游戏的核心数据结构：
- Player: 玩家模型，包含筹码、手牌、统计数据等
- TexasHoldemGame: 游戏模型，管理整个游戏的状态
- GamePhase: 游戏阶段枚举
- PlayerAction: 玩家行动枚举
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from enum import Enum
import time
import uuid
from .card import Card


class GamePhase(Enum):
    """
    游戏阶段枚举
    
    定义德州扑克游戏的各个阶段
    """
    WAITING = "waiting"        # 等待玩家加入
    PRE_FLOP = "pre_flop"     # 翻牌前（发手牌后的第一轮下注）
    FLOP = "flop"             # 翻牌（发3张公共牌后的下注轮）
    TURN = "turn"             # 转牌（发第4张公共牌后的下注轮）
    RIVER = "river"           # 河牌（发第5张公共牌后的下注轮）
    SHOWDOWN = "showdown"     # 摊牌（比较手牌决定胜负）
    FINISHED = "finished"     # 游戏结束


class PlayerAction(Enum):
    """
    玩家行动枚举
    
    定义玩家可以执行的所有行动
    """
    FOLD = "fold"             # 弃牌（放弃当前手牌）
    CHECK = "check"           # 让牌（不下注但继续游戏）
    CALL = "call"             # 跟注（跟上当前的下注额）
    RAISE = "raise"           # 加注（增加下注额）
    ALL_IN = "all_in"         # 全下（押上所有筹码）


@dataclass
class Player:
    """
    德州扑克玩家模型
    
    表示游戏中的一个玩家，包含其状态、筹码、手牌等信息
    
    Attributes:
        user_id: 用户唯一标识
        nickname: 玩家显示名称
        chips: 当前筹码数量
        hole_cards: 手牌（2张）
        current_bet: 当前轮次已下注金额
        is_folded: 是否已弃牌
        is_all_in: 是否已全下
        position: 在牌桌上的位置
        last_action: 最后执行的行动
        total_winnings: 总盈利（统计用）
        games_played: 参与游戏局数（统计用）
        hands_won: 获胜手数（统计用）
    """
    user_id: str                      # 用户ID
    nickname: str                     # 昵称
    chips: int                        # 筹码数量
    hole_cards: List[Card] = field(default_factory=list)  # 手牌
    current_bet: int = 0              # 当前下注
    is_folded: bool = False           # 是否已弃牌
    is_all_in: bool = False           # 是否全下
    position: int = 0                 # 座位位置
    last_action: Optional[PlayerAction] = None  # 最后行动
    
    # 统计数据
    total_winnings: int = 0           # 总盈利
    games_played: int = 0             # 游戏局数
    hands_won: int = 0                # 获胜手数
    initial_chips: int = 0            # 本局游戏初始筹码（用于计算盈亏）
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.hole_cards:
            self.hole_cards = []
    
    def can_bet(self, amount: int) -> bool:
        """
        检查是否能下注指定金额
        
        Args:
            amount: 下注金额
            
        Returns:
            是否能够下注
        """
        return (self.chips >= amount and 
                not self.is_folded and 
                not self.is_all_in and 
                amount > 0)
    
    def bet(self, amount: int) -> int:
        """
        执行下注操作
        
        Args:
            amount: 想要下注的金额
            
        Returns:
            实际下注的金额
        """
        if self.is_folded or self.is_all_in:
            return 0
        
        actual_bet = min(amount, self.chips)
        self.chips -= actual_bet
        self.current_bet += actual_bet
        
        if self.chips == 0:
            self.is_all_in = True
            
        return actual_bet
    
    def fold(self) -> None:
        """执行弃牌操作"""
        self.is_folded = True
        self.last_action = PlayerAction.FOLD
    
    def add_chips(self, amount: int) -> None:
        """
        增加筹码
        
        Args:
            amount: 增加的筹码数量
        """
        if amount > 0:
            self.chips += amount
    
    def reset_for_new_hand(self) -> None:
        """重置玩家状态以开始新一手牌"""
        self.hole_cards = []
        self.current_bet = 0
        self.is_folded = False
        self.is_all_in = False
        self.last_action = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'nickname': self.nickname,
            'chips': self.chips,
            'hole_cards': [str(card) for card in self.hole_cards],
            'current_bet': self.current_bet,
            'is_folded': self.is_folded,
            'is_all_in': self.is_all_in,
            'position': self.position,
            'last_action': self.last_action.value if self.last_action else None,
            'total_winnings': self.total_winnings,
            'games_played': self.games_played,
            'hands_won': self.hands_won,
            'initial_chips': self.initial_chips
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Player':
        """从字典创建玩家对象"""
        player = cls(
            user_id=data['user_id'],
            nickname=data['nickname'],
            chips=data['chips'],
            current_bet=data.get('current_bet', 0),
            is_folded=data.get('is_folded', False),
            is_all_in=data.get('is_all_in', False),
            position=data.get('position', 0),
            total_winnings=data.get('total_winnings', 0),
            games_played=data.get('games_played', 0),
            hands_won=data.get('hands_won', 0),
            initial_chips=data.get('initial_chips', 0)
        )
        
        if data.get('last_action'):
            player.last_action = PlayerAction(data['last_action'])
            
        return player


@dataclass
class TexasHoldemGame:
    """德州扑克游戏模型"""
    game_id: str                           # 游戏ID
    group_id: str                          # 群组ID
    players: List[Player] = field(default_factory=list)  # 玩家列表
    community_cards: List[Card] = field(default_factory=list)  # 公共牌
    pot: int = 0                           # 主池
    side_pots: List[int] = field(default_factory=list)  # 边池
    current_bet: int = 0                   # 当前轮下注额
    phase: GamePhase = GamePhase.WAITING   # 游戏阶段
    active_player_index: int = 0           # 当前行动玩家索引
    dealer_index: int = 0                  # 庄家位置索引
    small_blind: int = 10                  # 小盲注
    big_blind: int = 20                    # 大盲注
    created_at: int = field(default_factory=lambda: int(time.time()))  # 创建时间
    last_action_time: int = field(default_factory=lambda: int(time.time()))  # 最后行动时间
    timeout_seconds: int = 30              # 超时时间
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.game_id:
            self.game_id = str(uuid.uuid4())[:8]
        if not self.players:
            self.players = []
        if not self.community_cards:
            self.community_cards = []
        if not self.side_pots:
            self.side_pots = []
    
    def add_player(self, player: Player) -> bool:
        """添加玩家"""
        if len(self.players) >= 9:  # 最多9人
            return False
        if any(p.user_id == player.user_id for p in self.players):
            return False  # 玩家已在游戏中
        
        player.position = len(self.players)
        self.players.append(player)
        return True
    
    def remove_player(self, user_id: str) -> bool:
        """移除玩家"""
        for i, player in enumerate(self.players):
            if player.user_id == user_id:
                del self.players[i]
                # 重新分配位置
                for j, p in enumerate(self.players):
                    p.position = j
                return True
        return False
    
    def get_player(self, user_id: str) -> Optional[Player]:
        """获取玩家"""
        for player in self.players:
            if player.user_id == user_id:
                return player
        return None
    
    def get_active_player(self) -> Optional[Player]:
        """获取当前行动玩家"""
        if 0 <= self.active_player_index < len(self.players):
            return self.players[self.active_player_index]
        return None
    
    def get_active_players(self) -> List[Player]:
        """获取仍在游戏中的玩家"""
        return [p for p in self.players if not p.is_folded]
    
    def can_start(self) -> bool:
        """检查是否可以开始游戏"""
        return len(self.players) >= 2 and self.phase == GamePhase.WAITING
    
    def update_last_action_time(self):
        """更新最后行动时间"""
        self.last_action_time = int(time.time())
    
    def is_timeout(self) -> bool:
        """检查是否超时"""
        return int(time.time()) - self.last_action_time > self.timeout_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'game_id': self.game_id,
            'group_id': self.group_id,
            'players': [player.to_dict() for player in self.players],
            'community_cards': [str(card) for card in self.community_cards],
            'pot': self.pot,
            'side_pots': self.side_pots,
            'current_bet': self.current_bet,
            'phase': self.phase.value,
            'active_player_index': self.active_player_index,
            'dealer_index': self.dealer_index,
            'small_blind': self.small_blind,
            'big_blind': self.big_blind,
            'created_at': self.created_at,
            'last_action_time': self.last_action_time,
            'timeout_seconds': self.timeout_seconds
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TexasHoldemGame':
        """从字典创建游戏对象"""
        game = cls(
            game_id=data['game_id'],
            group_id=data['group_id'],
            pot=data.get('pot', 0),
            side_pots=data.get('side_pots', []),
            current_bet=data.get('current_bet', 0),
            active_player_index=data.get('active_player_index', 0),
            dealer_index=data.get('dealer_index', 0),
            small_blind=data.get('small_blind', 10),
            big_blind=data.get('big_blind', 20),
            created_at=data.get('created_at', int(time.time())),
            last_action_time=data.get('last_action_time', int(time.time())),
            timeout_seconds=data.get('timeout_seconds', 30)
        )
        
        if data.get('phase'):
            game.phase = GamePhase(data['phase'])
        
        if data.get('players'):
            game.players = [Player.from_dict(p) for p in data['players']]
        
        return game
