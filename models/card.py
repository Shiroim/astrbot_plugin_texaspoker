"""扑克牌相关数据模型

提供德州扑克游戏的扑克牌数据结构：
- Suit: 花色枚举（红桃、方块、梅花、黑桃）
- Rank: 牌面大小枚举（2-A）
- Card: 扑克牌模型
- Deck: 牌组管理器
"""
from dataclasses import dataclass
from typing import List, Optional, Iterator
from enum import Enum
import random


class Suit(Enum):
    """
    扑克牌花色枚举
    
    德州扑克中的四种花色，红色（红桃、方块）和黑色（梅花、黑桃）
    """
    HEARTS = "♥"     # 红桃（红色）
    DIAMONDS = "♦"   # 方块（红色）
    CLUBS = "♣"      # 梅花（黑色）
    SPADES = "♠"     # 黑桃（黑色）


class Rank(Enum):
    """
    扑克牌面大小枚举
    
    德州扑克中的牌面大小，数值越大牌越大
    注意：A既可以当1（A-2-3-4-5顺子）也可以当14（10-J-Q-K-A顺子）
    """
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14


@dataclass
class Card:
    """
    扑克牌模型
    
    表示一张扑克牌，包含花色和牌面大小
    
    Attributes:
        suit: 花色（红桃、方块、梅花、黑桃）
        rank: 牌面大小（2-A）
        
    Example:
        >>> card = Card(Suit.HEARTS, Rank.ACE)
        >>> str(card)  # 'A♥'
        >>> card.is_red  # True
        >>> card.value  # 14
    """
    suit: Suit
    rank: Rank
    
    def __str__(self) -> str:
        """
        扑克牌的字符串表示
        
        Returns:
            格式化的牌面字符串，如 "A♠"、"10♥"
        """
        rank_str = {
            Rank.TWO: "2", Rank.THREE: "3", Rank.FOUR: "4", Rank.FIVE: "5",
            Rank.SIX: "6", Rank.SEVEN: "7", Rank.EIGHT: "8", Rank.NINE: "9",
            Rank.TEN: "10", Rank.JACK: "J", Rank.QUEEN: "Q", 
            Rank.KING: "K", Rank.ACE: "A"
        }[self.rank]
        return f"{rank_str}{self.suit.value}"
    
    def __lt__(self, other):
        """比较运算符，用于排序"""
        return self.rank.value < other.rank.value
    
    def __eq__(self, other):
        """相等比较"""
        if not isinstance(other, Card):
            return False
        return self.suit == other.suit and self.rank == other.rank
    
    def __hash__(self):
        """哈希函数"""
        return hash((self.suit, self.rank))
    
    @property
    def value(self) -> int:
        """获取牌的数值"""
        return self.rank.value
    
    @property
    def is_red(self) -> bool:
        """是否为红色牌"""
        return self.suit in [Suit.HEARTS, Suit.DIAMONDS]
    
    @property
    def is_black(self) -> bool:
        """是否为黑色牌"""
        return self.suit in [Suit.CLUBS, Suit.SPADES]


class Deck:
    """牌组类"""
    
    def __init__(self):
        """初始化标准52张牌"""
        self.cards: List[Card] = []
        self.reset()
    
    def reset(self):
        """重置牌组为完整52张牌"""
        self.cards = []
        for suit in Suit:
            for rank in Rank:
                self.cards.append(Card(suit, rank))
    
    def shuffle(self):
        """洗牌"""
        random.shuffle(self.cards)
    
    def deal(self) -> Optional[Card]:
        """发一张牌"""
        if len(self.cards) > 0:
            return self.cards.pop()
        return None
    
    def deal_multiple(self, count: int) -> List[Card]:
        """发多张牌"""
        cards = []
        for _ in range(count):
            card = self.deal()
            if card:
                cards.append(card)
        return cards
    
    def remaining_count(self) -> int:
        """剩余牌数"""
        return len(self.cards)
    
    def is_empty(self) -> bool:
        """是否已空"""
        return len(self.cards) == 0
