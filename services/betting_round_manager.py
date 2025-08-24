"""德州扑克下注轮管理器

专门负责下注相关逻辑：
- 玩家行动验证
- 下注轮状态判断
- 行动处理
"""
from typing import List, Tuple, Optional, Dict, Any
from ..models.game import TexasHoldemGame, Player, PlayerAction, GamePhase
from astrbot.api import logger


class BettingRoundManager:
    """下注轮管理器
    
    职责：
    - 处理玩家行动
    - 验证行动合法性
    - 判断下注轮是否结束
    - 计算下一个行动玩家
    """
    
    def __init__(self):
        self.action_handlers = {
            'fold': self._handle_fold,
            'check': self._handle_check,
            'call': self._handle_call,
            'raise': self._handle_raise,
            'all_in': self._handle_all_in
        }
    
    def process_action(self, game: TexasHoldemGame, player: Player, action: str, amount: int = 0) -> Tuple[bool, str]:
        """处理玩家行动"""
        # 验证基本条件
        if not self._can_player_act(game, player):
            return False, self._get_action_error_message(game, player)
        
        # 处理具体行动
        action_key = self._normalize_action(action)
        handler = self.action_handlers.get(action_key)
        
        if not handler:
            return False, "无效的行动类型"
        
        try:
            success, message = handler(game, player, amount)
            if success:
                player.has_acted_this_round = True
                game.last_action_time = int(__import__('time').time())
                logger.debug(f"玩家 {player.nickname} 执行行动: {action}")
            return success, message
        except Exception as e:
            logger.error(f"处理行动失败: {e}")
            return False, "行动处理失败"
    
    def find_next_player(self, game: TexasHoldemGame) -> Optional[int]:
        """找到下一个需要行动的玩家索引"""
        player_count = len(game.players)
        start_idx = (game.active_player_index + 1) % player_count
        
        for i in range(player_count):
            idx = (start_idx + i) % player_count
            player = game.players[idx]
            
            if self._player_needs_action(player, game):
                return idx
        
        return None  # 没有玩家需要行动
    
    def is_betting_round_complete(self, game: TexasHoldemGame) -> bool:
        """判断下注轮是否结束"""
        active_players = [p for p in game.players if not p.is_folded]
        
        # 只剩一个玩家，游戏结束
        if len(active_players) <= 1:
            return True
        
        # 检查是否所有玩家都已行动且下注一致
        acting_players = [p for p in active_players if not p.is_all_in]
        
        if len(acting_players) <= 1:
            # 只有一个或零个非全下玩家，下注轮结束
            return True
        
        # 所有非全下玩家必须都已行动且下注额一致
        for player in acting_players:
            if not player.has_acted_this_round or player.current_bet < game.current_bet:
                return False
        
        return True
    
    def get_available_actions(self, game: TexasHoldemGame, player: Player) -> List[str]:
        """获取玩家可用的行动列表"""
        if not self._can_player_act(game, player):
            return []
        
        actions = []
        call_amount = game.current_bet - player.current_bet
        
        # 弃牌总是可用
        actions.append("fold")
        
        if call_amount == 0:
            # 可以让牌
            actions.append("check")
        else:
            # 可以跟注（如果有足够筹码）
            if player.chips >= call_amount:
                actions.append("call")
        
        # 加注（如果有足够筹码）
        min_raise_total = call_amount + game.big_blind
        if player.chips > min_raise_total:
            actions.append("raise")
        
        # 全下（如果有筹码）
        if player.chips > 0:
            actions.append("all_in")
        
        return actions
    
    def _can_player_act(self, game: TexasHoldemGame, player: Player) -> bool:
        """检查玩家是否可以行动"""
        # 基本状态检查
        if player.is_folded or player.is_all_in:
            return False
        
        # 检查是否是该玩家的回合
        active_player = game.get_active_player()
        if not active_player or active_player.user_id != player.user_id:
            return False
        
        # 检查游戏阶段
        valid_phases = [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]
        return game.phase in valid_phases
    
    def _player_needs_action(self, player: Player, game: TexasHoldemGame) -> bool:
        """判断玩家是否需要行动"""
        if player.is_folded or player.is_all_in:
            return False
        
        # 如果还没行动过，需要行动
        if not player.has_acted_this_round:
            return True
        
        # 如果下注不足，需要行动
        if player.current_bet < game.current_bet:
            return True
        
        return False
    
    def _get_action_error_message(self, game: TexasHoldemGame, player: Player) -> str:
        """获取行动错误消息"""
        if player.is_folded:
            return "您已弃牌，无法行动"
        if player.is_all_in:
            return "您已全下，无法继续行动"
        
        active_player = game.get_active_player()
        if not active_player or active_player.user_id != player.user_id:
            current_name = active_player.nickname if active_player else "无"
            return f"现在是 {current_name} 的回合，请等待"
        
        return "当前无法行动"
    
    def _normalize_action(self, action: str) -> str:
        """标准化行动名称"""
        action_map = {
            '弃牌': 'fold',
            '让牌': 'check', 
            '跟注': 'call',
            '加注': 'raise',
            '全下': 'all_in',
            'allin': 'all_in'
        }
        return action_map.get(action.lower().strip(), action.lower().strip())
    
    def _handle_fold(self, game: TexasHoldemGame, player: Player, amount: int) -> Tuple[bool, str]:
        """处理弃牌"""
        player.is_folded = True
        player.last_action = PlayerAction.FOLD
        return True, f"{player.nickname} 弃牌"
    
    def _handle_check(self, game: TexasHoldemGame, player: Player, amount: int) -> Tuple[bool, str]:
        """处理让牌"""
        call_amount = game.current_bet - player.current_bet
        if call_amount > 0:
            return False, f"当前需跟注 {call_amount}，无法让牌"
        
        player.last_action = PlayerAction.CHECK
        return True, f"{player.nickname} 让牌"
    
    def _handle_call(self, game: TexasHoldemGame, player: Player, amount: int) -> Tuple[bool, str]:
        """处理跟注"""
        call_amount = game.current_bet - player.current_bet
        
        if call_amount <= 0:
            return False, "没有需要跟注的金额"
        
        if call_amount > player.chips:
            return False, f"筹码不足，需要 {call_amount}，您只有 {player.chips}"
        
        player.chips -= call_amount
        player.current_bet += call_amount
        game.pot += call_amount
        player.last_action = PlayerAction.CALL
        
        if player.chips == 0:
            player.is_all_in = True
        
        return True, f"{player.nickname} 跟注 {call_amount}"
    
    def _handle_raise(self, game: TexasHoldemGame, player: Player, raise_amount: int) -> Tuple[bool, str]:
        """处理加注"""
        if raise_amount <= 0:
            return False, "请指定有效的加注金额"
        
        # 计算总需要下注额
        call_amount = game.current_bet - player.current_bet
        total_bet = call_amount + raise_amount
        
        if total_bet > player.chips:
            return False, f"筹码不足，需要 {total_bet}，您只有 {player.chips}"
        
        # 检查最小加注额
        if raise_amount < game.big_blind:
            return False, f"最小加注额为 {game.big_blind}"
        
        player.chips -= total_bet
        player.current_bet += total_bet
        game.pot += total_bet
        game.current_bet = player.current_bet
        player.last_action = PlayerAction.RAISE
        
        if player.chips == 0:
            player.is_all_in = True
        
        # 重置其他玩家的行动状态（只重置需要响应加注的玩家）
        for other_player in game.players:
            if (other_player.user_id != player.user_id and 
                not other_player.is_folded and 
                not other_player.is_all_in):
                other_player.has_acted_this_round = False
        
        return True, f"{player.nickname} 加注 {raise_amount}（总下注 {player.current_bet}）"
    
    def _handle_all_in(self, game: TexasHoldemGame, player: Player, amount: int) -> Tuple[bool, str]:
        """处理全下"""
        if player.chips <= 0:
            return False, "您没有筹码可以全下"
        
        all_in_amount = player.chips
        player.chips = 0
        player.current_bet += all_in_amount
        game.pot += all_in_amount
        player.is_all_in = True
        player.last_action = PlayerAction.ALL_IN
        
        # 如果全下金额超过当前下注，更新当前下注额
        if player.current_bet > game.current_bet:
            game.current_bet = player.current_bet
            # 重置其他玩家的行动状态（只重置能够响应的玩家）
            for other_player in game.players:
                if (other_player.user_id != player.user_id and 
                    not other_player.is_folded and 
                    not other_player.is_all_in):
                    other_player.has_acted_this_round = False
        
        return True, f"{player.nickname} 全下 {all_in_amount} 筹码！"
