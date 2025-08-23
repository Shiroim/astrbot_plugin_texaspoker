"""德州扑克牌型评估服务"""
from typing import List, Tuple, Optional
from collections import Counter
from enum import Enum
from ..models.card import Card, Rank, Suit


class HandRank(Enum):
    """牌型等级枚举（数值越大等级越高）"""
    HIGH_CARD = 1         # 高牌
    ONE_PAIR = 2          # 一对
    TWO_PAIR = 3          # 两对
    THREE_OF_A_KIND = 4   # 三条
    STRAIGHT = 5          # 顺子
    FLUSH = 6             # 同花
    FULL_HOUSE = 7        # 葫芦（满堂红）
    FOUR_OF_A_KIND = 8    # 四条
    STRAIGHT_FLUSH = 9    # 同花顺
    ROYAL_FLUSH = 10      # 皇家同花顺


class HandEvaluator:
    """牌型评估器"""
    
    @staticmethod
    def evaluate_hand(hole_cards: List[Card], community_cards: List[Card]) -> Tuple[HandRank, List[int]]:
        """
        评估最佳五张牌组合
        
        Args:
            hole_cards: 玩家手牌(2张)
            community_cards: 公共牌(最多5张)
            
        Returns:
            Tuple[HandRank, List[int]]: (牌型等级, 比较值列表)
        """
        all_cards = hole_cards + community_cards
        if len(all_cards) < 5:
            # 不足5张牌，返回高牌
            sorted_values = sorted([card.value for card in all_cards], reverse=True)
            return HandRank.HIGH_CARD, sorted_values
        
        # 找出最佳五张牌组合
        best_hand = None
        best_rank = HandRank.HIGH_CARD
        best_values = []
        
        # 生成所有5张牌的组合
        from itertools import combinations
        for five_cards in combinations(all_cards, 5):
            rank, values = HandEvaluator._evaluate_five_cards(list(five_cards))
            
            # 比较牌型
            if rank.value > best_rank.value or (rank == best_rank and HandEvaluator._compare_values(values, best_values) > 0):
                best_hand = five_cards
                best_rank = rank
                best_values = values
        
        return best_rank, best_values
    
    @staticmethod
    def _evaluate_five_cards(cards: List[Card]) -> Tuple[HandRank, List[int]]:
        """评估五张牌的牌型"""
        # 按牌值排序
        sorted_cards = sorted(cards, key=lambda c: c.value, reverse=True)
        values = [c.value for c in sorted_cards]
        suits = [c.suit for c in sorted_cards]
        
        # 统计牌值出现次数
        value_counts = Counter(values)
        counts = sorted(value_counts.values(), reverse=True)
        
        # 检查是否为同花
        is_flush = len(set(suits)) == 1
        
        # 检查是否为顺子
        is_straight = HandEvaluator._is_straight(values)
        
        # 特殊处理A-2-3-4-5顺子
        if values == [14, 5, 4, 3, 2]:  # A-5顺子
            is_straight = True
            values = [5, 4, 3, 2, 1]  # A当作1处理
        
        # 判断牌型
        if is_straight and is_flush:
            if values == [14, 13, 12, 11, 10]:  # A-K-Q-J-10同花顺
                return HandRank.ROYAL_FLUSH, values
            else:
                return HandRank.STRAIGHT_FLUSH, [values[0]]  # 同花顺只比较最高牌
        elif counts == [4, 1]:  # 四条
            four_kind = [v for v, c in value_counts.items() if c == 4][0]
            kicker = [v for v, c in value_counts.items() if c == 1][0]
            return HandRank.FOUR_OF_A_KIND, [four_kind, kicker]
        elif counts == [3, 2]:  # 葫芦
            three_kind = [v for v, c in value_counts.items() if c == 3][0]
            pair = [v for v, c in value_counts.items() if c == 2][0]
            return HandRank.FULL_HOUSE, [three_kind, pair]
        elif is_flush:  # 同花
            return HandRank.FLUSH, values
        elif is_straight:  # 顺子
            return HandRank.STRAIGHT, [values[0]]
        elif counts == [3, 1, 1]:  # 三条
            three_kind = [v for v, c in value_counts.items() if c == 3][0]
            kickers = sorted([v for v, c in value_counts.items() if c == 1], reverse=True)
            return HandRank.THREE_OF_A_KIND, [three_kind] + kickers
        elif counts == [2, 2, 1]:  # 两对
            pairs = sorted([v for v, c in value_counts.items() if c == 2], reverse=True)
            kicker = [v for v, c in value_counts.items() if c == 1][0]
            return HandRank.TWO_PAIR, pairs + [kicker]
        elif counts == [2, 1, 1, 1]:  # 一对
            pair = [v for v, c in value_counts.items() if c == 2][0]
            kickers = sorted([v for v, c in value_counts.items() if c == 1], reverse=True)
            return HandRank.ONE_PAIR, [pair] + kickers
        else:  # 高牌
            return HandRank.HIGH_CARD, values
    
    @staticmethod
    def _is_straight(values: List[int]) -> bool:
        """检查是否为顺子"""
        if len(values) != 5:
            return False
        
        unique_values = sorted(set(values), reverse=True)
        if len(unique_values) != 5:
            return False
        
        # 检查连续性
        for i in range(4):
            if unique_values[i] - unique_values[i + 1] != 1:
                return False
        
        return True
    
    @staticmethod
    def _compare_values(values1: List[int], values2: List[int]) -> int:
        """
        比较两个牌型的值
        
        Returns:
            1: values1 > values2
            0: values1 == values2  
            -1: values1 < values2
        """
        for v1, v2 in zip(values1, values2):
            if v1 > v2:
                return 1
            elif v1 < v2:
                return -1
        return 0
    
    @staticmethod
    def compare_hands(hand1: Tuple[HandRank, List[int]], hand2: Tuple[HandRank, List[int]]) -> int:
        """
        比较两手牌的大小
        
        Returns:
            1: hand1 > hand2
            0: hand1 == hand2
            -1: hand1 < hand2
        """
        rank1, values1 = hand1
        rank2, values2 = hand2
        
        # 先比较牌型等级
        if rank1.value > rank2.value:
            return 1
        elif rank1.value < rank2.value:
            return -1
        
        # 牌型相同，比较具体值
        return HandEvaluator._compare_values(values1, values2)
    
    @staticmethod
    def get_hand_description(hand_rank: HandRank, values: List[int]) -> str:
        """获取牌型描述"""
        rank_names = {
            Rank.TWO: "2", Rank.THREE: "3", Rank.FOUR: "4", Rank.FIVE: "5",
            Rank.SIX: "6", Rank.SEVEN: "7", Rank.EIGHT: "8", Rank.NINE: "9",
            Rank.TEN: "10", Rank.JACK: "J", Rank.QUEEN: "Q", 
            Rank.KING: "K", Rank.ACE: "A"
        }
        
        def value_to_name(value: int) -> str:
            for rank in Rank:
                if rank.value == value:
                    return rank_names[rank]
            return str(value)
        
        if hand_rank == HandRank.ROYAL_FLUSH:
            return "皇家同花顺"
        elif hand_rank == HandRank.STRAIGHT_FLUSH:
            return f"{value_to_name(values[0])}高同花顺"
        elif hand_rank == HandRank.FOUR_OF_A_KIND:
            return f"四条{value_to_name(values[0])}"
        elif hand_rank == HandRank.FULL_HOUSE:
            return f"{value_to_name(values[0])}满{value_to_name(values[1])}"
        elif hand_rank == HandRank.FLUSH:
            return f"{value_to_name(values[0])}高同花"
        elif hand_rank == HandRank.STRAIGHT:
            return f"{value_to_name(values[0])}高顺子"
        elif hand_rank == HandRank.THREE_OF_A_KIND:
            return f"三条{value_to_name(values[0])}"
        elif hand_rank == HandRank.TWO_PAIR:
            return f"{value_to_name(values[0])}、{value_to_name(values[1])}两对"
        elif hand_rank == HandRank.ONE_PAIR:
            return f"一对{value_to_name(values[0])}"
        else:
            return f"{value_to_name(values[0])}高牌"
