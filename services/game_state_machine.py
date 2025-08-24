"""德州扑克游戏状态机

清晰简洁的状态管理，负责：
- 游戏阶段转换
- 状态验证
- 阶段特定的逻辑处理
"""
from typing import List, Optional, Callable, Any, Dict
from enum import Enum
from ..models.game import TexasHoldemGame, Player, GamePhase
from ..models.card import Deck
from astrbot.api import logger


class StateTransition:
    """状态转换规则定义"""
    
    @staticmethod
    def can_transition(from_phase: GamePhase, to_phase: GamePhase) -> bool:
        """检查状态转换是否合法"""
        valid_transitions = {
            GamePhase.WAITING: [GamePhase.PRE_FLOP],
            GamePhase.PRE_FLOP: [GamePhase.FLOP, GamePhase.SHOWDOWN],
            GamePhase.FLOP: [GamePhase.TURN, GamePhase.SHOWDOWN],
            GamePhase.TURN: [GamePhase.RIVER, GamePhase.SHOWDOWN],
            GamePhase.RIVER: [GamePhase.SHOWDOWN],
            GamePhase.SHOWDOWN: [GamePhase.FINISHED],
            GamePhase.FINISHED: []
        }
        return to_phase in valid_transitions.get(from_phase, [])


class GameStateMachine:
    """德州扑克游戏状态机
    
    职责：
    - 管理游戏阶段转换
    - 验证状态合法性
    - 处理阶段特定逻辑
    """
    
    def __init__(self):
        self.phase_handlers = {
            GamePhase.WAITING: self._handle_waiting_phase,
            GamePhase.PRE_FLOP: self._handle_preflop_phase,
            GamePhase.FLOP: self._handle_flop_phase,
            GamePhase.TURN: self._handle_turn_phase,
            GamePhase.RIVER: self._handle_river_phase,
            GamePhase.SHOWDOWN: self._handle_showdown_phase
        }
        
        # 阶段变更回调
        self.on_phase_changed: Optional[Callable] = None
    
    def set_phase_change_callback(self, callback: Callable):
        """设置阶段变更回调"""
        self.on_phase_changed = callback
    
    def start_game(self, game: TexasHoldemGame) -> bool:
        """开始游戏，从等待阶段转入翻牌前"""
        if not self._validate_game_can_start(game):
            return False
        
        # 初始化牌组
        game._deck = Deck()
        game._deck.shuffle()
        
        # 转换到翻牌前阶段
        return self.transition_to_phase(game, GamePhase.PRE_FLOP)
    
    def transition_to_phase(self, game: TexasHoldemGame, target_phase: GamePhase) -> bool:
        """转换游戏阶段"""
        if not StateTransition.can_transition(game.phase, target_phase):
            logger.error(f"非法状态转换: {game.phase.value} -> {target_phase.value}")
            return False
        
        old_phase = game.phase
        game.phase = target_phase
        
        # 执行阶段特定处理
        handler = self.phase_handlers.get(target_phase)
        if handler:
            try:
                handler(game)
                logger.info(f"游戏 {game.game_id} 阶段转换: {old_phase.value} -> {target_phase.value}")
                
                # 触发回调
                if self.on_phase_changed:
                    self.on_phase_changed(game, old_phase, target_phase)
                    
                return True
            except Exception as e:
                logger.error(f"阶段处理失败: {e}")
                game.phase = old_phase  # 回滚
                return False
        
        return True
    
    def _validate_game_can_start(self, game: TexasHoldemGame) -> bool:
        """验证游戏是否可以开始"""
        if game.phase != GamePhase.WAITING:
            return False
        if len(game.players) < 2:
            return False
        # 验证所有玩家都有足够筹码参与盲注
        for player in game.players:
            if player.chips < game.big_blind:
                return False
        return True
    
    def _handle_waiting_phase(self, game: TexasHoldemGame):
        """处理等待阶段"""
        # 重置游戏状态
        game.pot = 0
        game.current_bet = 0
        game.community_cards = []
        
        # 重置所有玩家状态
        for player in game.players:
            player.hole_cards = []
            player.current_bet = 0
            player.is_folded = False
            player.is_all_in = False
            player.last_action = None
            player.has_acted_this_round = False
    
    def _handle_preflop_phase(self, game: TexasHoldemGame):
        """处理翻牌前阶段"""
        # 发手牌
        for player in game.players:
            player.hole_cards = game._deck.deal_multiple(2)
        
        # 下盲注
        self._post_blinds(game)
        
        # 设置第一个行动玩家（大盲注左边的玩家）
        self._set_preflop_action_order(game)
    
    def _handle_flop_phase(self, game: TexasHoldemGame):
        """处理翻牌阶段"""
        # 发3张公共牌
        game.community_cards.extend(game._deck.deal_multiple(3))
        
        # 重置下注轮
        self._reset_betting_round(game)
        
        # 设置行动玩家（从小盲注开始）
        self._set_postflop_action_order(game)
    
    def _handle_turn_phase(self, game: TexasHoldemGame):
        """处理转牌阶段"""
        # 发1张公共牌
        game.community_cards.extend(game._deck.deal_multiple(1))
        
        # 重置下注轮
        self._reset_betting_round(game)
        
        # 设置行动玩家
        self._set_postflop_action_order(game)
    
    def _handle_river_phase(self, game: TexasHoldemGame):
        """处理河牌阶段"""
        # 发1张公共牌
        game.community_cards.extend(game._deck.deal_multiple(1))
        
        # 重置下注轮
        self._reset_betting_round(game)
        
        # 设置行动玩家
        self._set_postflop_action_order(game)
    
    def _handle_showdown_phase(self, game: TexasHoldemGame):
        """处理摊牌阶段"""
        from .hand_evaluator import HandEvaluator
        
        # 评估所有未弃牌玩家的手牌
        active_players = [p for p in game.players if not p.is_folded]
        if not active_players:
            return
        
        # 计算所有玩家的手牌等级
        player_hands = []
        for player in active_players:
            hand_rank, values = HandEvaluator.evaluate_hand(player.hole_cards, game.community_cards)
            player_hands.append((player, hand_rank, values))
        
        # 排序找出获胜者
        player_hands.sort(key=lambda x: (x[1].value, x[2]), reverse=True)
        
        # 使用边池系统分配奖池
        side_pots = self._create_side_pots(game)
        winners_info = self._distribute_side_pots(side_pots, player_hands)
        
        # 获取所有获胜者
        all_winners = list(set(winner for _, winner in winners_info))
        
        # 保存摊牌结果
        game.showdown_results = {
            'player_hands': player_hands,
            'winners': all_winners,
            'pot_distribution': [{'winner': w.nickname, 'amount': amt} for amt, w in winners_info]
        }
        
        logger.info(f"游戏 {game.game_id} 摊牌完成，获胜者: {[w.nickname for w in all_winners]}")
    
    def _create_side_pots(self, game: TexasHoldemGame) -> List[Dict[str, Any]]:
        """创建边池系统"""
        active_players = [p for p in game.players if not p.is_folded]
        
        if len(active_players) <= 1:
            return [{'amount': game.pot, 'eligible_players': active_players}]
        
        # 按下注金额分组
        bet_levels = sorted(set(p.current_bet for p in active_players))
        side_pots = []
        
        for i, level in enumerate(bet_levels):
            if level <= 0:
                continue
            
            # 找出投入至少达到这个水平的玩家
            eligible_players = [p for p in active_players if p.current_bet >= level]
            
            # 计算这个边池的大小
            if i == 0:
                contribution_per_player = level
            else:
                contribution_per_player = level - bet_levels[i-1]
            
            pot_amount = contribution_per_player * len(eligible_players)
            
            if pot_amount > 0:
                side_pots.append({
                    'amount': pot_amount,
                    'eligible_players': eligible_players.copy()
                })
        
        return side_pots
    
    def _distribute_side_pots(self, side_pots: List[Dict[str, Any]], player_hands: List) -> List[Tuple[int, Player]]:
        """分配边池，返回(金额, 获胜者)列表"""
        from .hand_evaluator import HandEvaluator
        
        winners_info = []
        
        for side_pot in side_pots:
            eligible_players = side_pot['eligible_players']
            pot_amount = side_pot['amount']
            
            # 找出在这个边池中的最强手牌
            eligible_hands = [(p, r, v) for p, r, v in player_hands if p in eligible_players]
            
            if not eligible_hands:
                continue
            
            # 找出边池获胜者
            best_rank, best_values = eligible_hands[0][1], eligible_hands[0][2]
            pot_winners = [eligible_hands[0][0]]
            
            for player, rank, values in eligible_hands[1:]:
                comparison = HandEvaluator.compare_hands((rank, values), (best_rank, best_values))
                if comparison == 0:  # 平手
                    pot_winners.append(player)
                elif comparison > 0:  # 更强的手牌
                    pot_winners = [player]
                    best_rank, best_values = rank, values
            
            # 分配这个边池
            pot_per_winner = pot_amount // len(pot_winners)
            remainder = pot_amount % len(pot_winners)
            
            for i, winner in enumerate(pot_winners):
                winnings = pot_per_winner + (1 if i < remainder else 0)
                winner.add_chips(winnings)
                winner.hands_won += 1
                winners_info.append((winnings, winner))
        
        return winners_info
    
    def _post_blinds(self, game: TexasHoldemGame):
        """下盲注"""
        player_count = len(game.players)
        
        if player_count == 2:
            # 两人游戏：庄家是小盲注
            small_blind_idx = game.dealer_index
            big_blind_idx = (game.dealer_index + 1) % 2
        else:
            # 多人游戏：庄家左边是小盲注
            small_blind_idx = (game.dealer_index + 1) % player_count
            big_blind_idx = (game.dealer_index + 2) % player_count
        
        # 小盲注
        sb_player = game.players[small_blind_idx]
        sb_amount = min(game.small_blind, sb_player.chips)
        sb_player.chips -= sb_amount
        sb_player.current_bet = sb_amount
        game.pot += sb_amount
        
        if sb_player.chips == 0:
            sb_player.is_all_in = True
        
        # 大盲注  
        bb_player = game.players[big_blind_idx]
        bb_amount = min(game.big_blind, bb_player.chips)
        bb_player.chips -= bb_amount
        bb_player.current_bet = bb_amount
        game.pot += bb_amount
        game.current_bet = bb_amount
        
        if bb_player.chips == 0:
            bb_player.is_all_in = True
    
    def _set_preflop_action_order(self, game: TexasHoldemGame):
        """设置翻牌前行动顺序"""
        player_count = len(game.players)
        
        if player_count == 2:
            # 两人游戏：庄家（小盲注）先行动
            start_idx = game.dealer_index
        else:
            # 多人游戏：大盲注左边的玩家先行动
            start_idx = (game.dealer_index + 3) % player_count
        
        # 找到第一个可以行动的玩家
        game.active_player_index = self._find_next_active_player(game, start_idx)
    
    def _set_postflop_action_order(self, game: TexasHoldemGame):
        """设置翻牌后行动顺序"""
        player_count = len(game.players)
        
        if player_count == 2:
            # 两人游戏：庄家先行动
            start_idx = game.dealer_index
        else:
            # 多人游戏：小盲注先行动
            start_idx = (game.dealer_index + 1) % player_count
        
        # 找到第一个可以行动的玩家
        game.active_player_index = self._find_next_active_player(game, start_idx)
    
    def _find_next_active_player(self, game: TexasHoldemGame, start_idx: int) -> int:
        """从指定位置开始找下一个可行动的玩家"""
        player_count = len(game.players)
        
        for i in range(player_count):
            idx = (start_idx + i) % player_count
            player = game.players[idx]
            if not player.is_folded and not player.is_all_in:
                return idx
        
        # 如果没有找到，返回起始位置
        return start_idx
    
    def _reset_betting_round(self, game: TexasHoldemGame):
        """重置下注轮"""
        game.current_bet = 0
        for player in game.players:
            player.current_bet = 0
            player.has_acted_this_round = False
            player.last_action = None
