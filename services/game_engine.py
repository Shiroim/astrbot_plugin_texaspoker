"""德州扑克游戏引擎

提供完整的德州扑克游戏逻辑，包括：
- 游戏创建和管理
- 玩家行动处理
- 游戏阶段推进
- 超时处理机制
"""
import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any
from ..models.game import TexasHoldemGame, Player, GamePhase, PlayerAction
from ..models.card import Deck, Card
from ..utils.data_storage import DataStorage
from .hand_evaluator import HandEvaluator, HandRank
from astrbot.api import logger


class GameEngine:
    """德州扑克游戏引擎"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.active_games: Dict[str, TexasHoldemGame] = {}
        self.timeouts: Dict[str, asyncio.Task] = {}
    
    def create_game(self, group_id: str, creator_id: str, creator_nickname: str,
                   small_blind: Optional[int] = None, big_blind: Optional[int] = None) -> Tuple[bool, str, Optional[TexasHoldemGame]]:
        """
        创建新的德州扑克游戏
        
        Args:
            group_id: 群组ID
            creator_id: 创建者用户ID
            creator_nickname: 创建者昵称
            small_blind: 小盲注（可选）
            big_blind: 大盲注（可选）
            
        Returns:
            Tuple[成功标志, 消息, 游戏对象]
        """
        try:
            # 检查是否已有游戏
            if group_id in self.active_games:
                return False, "该群已有正在进行的游戏", None
            
            # 参数验证和默认值设置
            if small_blind is None:
                small_blind = self.storage.get_plugin_config_value('small_blind', 10)
            if big_blind is None:
                big_blind = self.storage.get_plugin_config_value('big_blind', 20)
            
            # 验证参数合理性
            if small_blind <= 0 or big_blind <= 0:
                return False, "盲注必须大于0", None
            if big_blind <= small_blind:
                return False, "大盲注必须大于小盲注", None
            
            default_chips = self.storage.get_plugin_config_value('default_chips', 1000)
            timeout_seconds = self.storage.get_plugin_config_value('action_timeout', 30)
            
            # 验证配置的合理性
            if default_chips < big_blind * 10:
                logger.warning(f"初始筹码({default_chips})可能过少，建议至少为大盲注的10倍")
            
            # 创建游戏
            game = TexasHoldemGame(
                game_id=f"{group_id}_{int(time.time())}",
                group_id=group_id,
                small_blind=small_blind,
                big_blind=big_blind,
                timeout_seconds=timeout_seconds
            )
            
            # 创建创建者玩家
            creator = Player(
                user_id=creator_id,
                nickname=creator_nickname,
                chips=default_chips
            )
            
            if not game.add_player(creator):
                return False, "添加创建者失败", None
            
            self.active_games[group_id] = game
            
            # 保存到存储
            self.storage.save_game(group_id, game.to_dict())
            
            logger.info(f"创建游戏: {game.game_id}, 群组: {group_id}, 创建者: {creator_nickname}")
            return True, f"游戏创建成功！游戏ID: {game.game_id}", game
            
        except Exception as e:
            logger.error(f"创建游戏时发生错误: {e}")
            return False, "创建游戏失败，请稍后重试", None
    
    def join_game(self, group_id: str, user_id: str, nickname: str) -> Tuple[bool, str]:
        """
        玩家加入游戏
        
        Args:
            group_id: 群组ID
            user_id: 用户ID
            nickname: 用户昵称
            
        Returns:
            Tuple[成功标志, 消息]
        """
        try:
            if group_id not in self.active_games:
                return False, "该群没有正在进行的游戏"
            
            game = self.active_games[group_id]
            
            # 检查游戏状态
            if game.phase != GamePhase.WAITING:
                return False, "游戏已开始，无法加入"
            
            # 检查玩家是否已在游戏中
            if game.get_player(user_id):
                return False, "您已在游戏中"
            
            # 检查人数限制
            max_players = self.storage.get_plugin_config_value('max_players', 9)
            if len(game.players) >= max_players:
                return False, f"游戏人数已满({max_players}人)"
            
            # 创建新玩家
            default_chips = self.storage.get_plugin_config_value('default_chips', 1000)
            player = Player(
                user_id=user_id,
                nickname=nickname,
                chips=default_chips
            )
            
            # 添加玩家到游戏
            if game.add_player(player):
                # 保存游戏状态
                self.storage.save_game(group_id, game.to_dict())
                logger.info(f"玩家 {nickname} 加入游戏 {game.game_id}")
                return True, f"{nickname} 加入游戏成功！当前玩家数: {len(game.players)}"
            else:
                return False, "添加玩家失败"
                
        except Exception as e:
            logger.error(f"玩家加入游戏时发生错误: {e}")
            return False, "加入游戏失败，请稍后重试"
    
    def start_game(self, group_id: str, user_id: str) -> Tuple[bool, str]:
        """
        开始德州扑克游戏
        
        Args:
            group_id: 群组ID
            user_id: 启动游戏的用户ID
            
        Returns:
            Tuple[成功标志, 消息]
        """
        try:
            if group_id not in self.active_games:
                return False, "该群没有正在进行的游戏"
            
            game = self.active_games[group_id]
            
            # 验证启动者是否在游戏中
            if not game.get_player(user_id):
                return False, "您不在游戏中，无法开始游戏"
            
            # 检查最少玩家数
            min_players = self.storage.get_plugin_config_value('min_players', 2)
            if len(game.players) < min_players:
                return False, f"至少需要{min_players}名玩家才能开始游戏，当前{len(game.players)}人"
            
            # 检查游戏状态
            if game.phase != GamePhase.WAITING:
                return False, "游戏已经开始，无法重复启动"
            
            # 验证所有玩家都有足够筹码
            for player in game.players:
                if player.chips < game.big_blind:
                    return False, f"玩家 {player.nickname} 筹码不足，无法参与游戏"
            
            # 开始新一手牌
            self._start_new_hand(game)
            
            # 保存游戏状态
            self.storage.save_game(group_id, game.to_dict())
            
            # 启动超时检查
            self._start_timeout_check(group_id)
            
            logger.info(f"游戏开始: {game.game_id}, 玩家数: {len(game.players)}")
            return True, f"游戏开始！参与玩家: {len(game.players)}人"
            
        except Exception as e:
            logger.error(f"开始游戏时发生错误: {e}")
            return False, "开始游戏失败，请稍后重试"
    
    def _start_new_hand(self, game: TexasHoldemGame) -> None:
        """
        开始新一手牌的流程
        
        Args:
            game: 游戏对象
        """
        try:
            # 重置所有玩家状态
            for player in game.players:
                player.reset_for_new_hand()
            
            # 重置游戏状态
            game.community_cards = []
            game.pot = 0
            game.side_pots = []
            game.current_bet = 0
            game.phase = GamePhase.PRE_FLOP
            
            # 创建新牌组并洗牌
            deck = Deck()
            deck.shuffle()
            
            # 验证牌组有足够的牌
            cards_needed = len(game.players) * 2 + 5  # 手牌 + 公共牌
            if deck.remaining_count() < cards_needed:
                raise ValueError("牌组数量不足")
            
            # 每个玩家发2张手牌
            for player in game.players:
                try:
                    player.hole_cards = deck.deal_multiple(2)
                    if len(player.hole_cards) != 2:
                        raise ValueError(f"玩家 {player.nickname} 发牌失败")
                except Exception as e:
                    logger.error(f"为玩家 {player.nickname} 发牌时出错: {e}")
                    raise
            
            # 下盲注
            self._post_blinds(game)
            
            # 设置第一个行动玩家
            self._set_first_action_player(game)
            
            # 更新时间戳
            game.update_last_action_time()
            
            logger.debug(f"新一手牌开始: {game.game_id}, 玩家数: {len(game.players)}")
            
        except Exception as e:
            logger.error(f"开始新一手牌时出错: {e}")
            raise
    
    def _set_first_action_player(self, game: TexasHoldemGame) -> None:
        """设置第一个行动玩家"""
        player_count = len(game.players)
        
        if player_count == 2:
            # heads-up: 庄家（小盲）先行动
            game.active_player_index = game.dealer_index
        else:
            # 多人游戏: 大盲注后一位先行动
            game.active_player_index = (game.dealer_index + 3) % player_count
    
    def _post_blinds(self, game: TexasHoldemGame) -> None:
        """
        处理盲注下注
        
        Args:
            game: 游戏对象
        """
        player_count = len(game.players)
        
        if player_count < 2:
            raise ValueError("盲注至少需要2名玩家")
        
        # 确定盲注位置
        if player_count == 2:
            # heads-up: 庄家是小盲，对家是大盲
            small_blind_index = game.dealer_index
            big_blind_index = (game.dealer_index + 1) % player_count
        else:
            # 多人游戏: 庄家左边是小盲，再左边是大盲
            small_blind_index = (game.dealer_index + 1) % player_count
            big_blind_index = (game.dealer_index + 2) % player_count
        
        # 下小盲注
        small_blind_player = game.players[small_blind_index]
        small_blind_amount = min(game.small_blind, small_blind_player.chips)
        if small_blind_amount > 0:
            actual_sb = small_blind_player.bet(small_blind_amount)
            game.pot += actual_sb
            logger.debug(f"{small_blind_player.nickname} 下小盲注 {actual_sb}")
        
        # 下大盲注
        big_blind_player = game.players[big_blind_index]
        big_blind_amount = min(game.big_blind, big_blind_player.chips)
        if big_blind_amount > 0:
            actual_bb = big_blind_player.bet(big_blind_amount)
            game.pot += actual_bb
            game.current_bet = big_blind_player.current_bet  # 设置当前下注额
            logger.debug(f"{big_blind_player.nickname} 下大盲注 {actual_bb}")
        
        # 检查是否有玩家因为盲注而全下
        if small_blind_player.chips == 0:
            small_blind_player.is_all_in = True
            logger.info(f"{small_blind_player.nickname} 因小盲注全下")
        
        if big_blind_player.chips == 0:
            big_blind_player.is_all_in = True
            logger.info(f"{big_blind_player.nickname} 因大盲注全下")
    
    def player_action(self, group_id: str, user_id: str, action: str, amount: int = 0) -> Tuple[bool, str]:
        """
        处理玩家行动
        
        Args:
            group_id: 群组ID
            user_id: 玩家用户ID
            action: 行动类型
            amount: 行动金额（加注时使用）
            
        Returns:
            Tuple[成功标志, 消息]
        """
        try:
            # 基础验证
            if group_id not in self.active_games:
                return False, "该群没有正在进行的游戏"
            
            game = self.active_games[group_id]
            player = game.get_player(user_id)
            
            if not player:
                return False, "您不在游戏中"
            
            # 检查游戏阶段
            valid_phases = [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]
            if game.phase not in valid_phases:
                return False, "当前不是下注阶段"
            
            # 检查是否是该玩家回合
            active_player = game.get_active_player()
            if not active_player or active_player.user_id != user_id:
                current_player_name = active_player.nickname if active_player else "无"
                return False, f"现在是 {current_player_name} 的回合，请等待"
            
            # 检查玩家状态
            if player.is_folded:
                return False, "您已弃牌，无法进行操作"
            
            # 处理具体行动
            success, message = self._process_player_action(game, player, action, amount)
            
            if success:
                # 更新行动时间
                game.update_last_action_time()
                
                # 检查是否需要进入下一阶段
                self._check_betting_round_complete(game)
                
                # 保存游戏状态
                self.storage.save_game(group_id, game.to_dict())
                
                # 重置超时检查
                if game.phase in valid_phases:
                    self._start_timeout_check(group_id)
            
            return success, message
            
        except Exception as e:
            logger.error(f"处理玩家行动时发生错误: {e}")
            return False, "处理行动失败，请稍后重试"
    
    def _process_player_action(self, game: TexasHoldemGame, player: Player, action: str, amount: int) -> Tuple[bool, str]:
        """
        处理玩家具体行动
        
        Args:
            game: 游戏对象
            player: 玩家对象
            action: 行动类型
            amount: 行动金额
            
        Returns:
            Tuple[成功标志, 消息]
        """
        action_type = action.lower().strip()
        
        try:
            # 弃牌
            if action_type in ["fold", "弃牌"]:
                player.fold()
                message = f"{player.nickname} 弃牌"
                
            # 让牌
            elif action_type in ["check", "让牌"]:
                if player.current_bet < game.current_bet:
                    need_amount = game.current_bet - player.current_bet
                    return False, f"当前需跟注 {need_amount}，无法让牌"
                player.last_action = PlayerAction.CHECK
                message = f"{player.nickname} 让牌"
                
            # 跟注
            elif action_type in ["call", "跟注"]:
                call_amount = game.current_bet - player.current_bet
                if call_amount <= 0:
                    return False, "没有需要跟注的金额，请选择让牌或加注"
                
                if call_amount > player.chips:
                    return False, f"筹码不足跟注，需要 {call_amount}，您只有 {player.chips}"
                
                actual_bet = player.bet(call_amount)
                game.pot += actual_bet
                player.last_action = PlayerAction.CALL
                message = f"{player.nickname} 跟注 {actual_bet}"
                
            # 加注
            elif action_type in ["raise", "加注"]:
                if amount <= 0:
                    return False, "请指定有效的加注金额"
                
                # 计算需要的总下注额
                call_amount = game.current_bet - player.current_bet
                total_bet_needed = call_amount + amount
                
                if total_bet_needed > player.chips:
                    return False, f"筹码不足，需要 {total_bet_needed}，您只有 {player.chips}"
                
                # 检查最小加注额
                min_raise = game.big_blind
                if amount < min_raise:
                    return False, f"最小加注金额为 {min_raise}"
                
                actual_bet = player.bet(total_bet_needed)
                game.pot += actual_bet
                game.current_bet = player.current_bet
                player.last_action = PlayerAction.RAISE
                message = f"{player.nickname} 加注 {amount}（总下注 {player.current_bet}）"
                
            # 全下
            elif action_type in ["allin", "all_in", "全下"]:
                if player.chips <= 0:
                    return False, "您没有筹码可以全下"
                
                all_in_amount = player.chips
                actual_bet = player.bet(all_in_amount)
                game.pot += actual_bet
                
                # 如果全下金额超过当前下注，更新当前下注额
                if player.current_bet > game.current_bet:
                    game.current_bet = player.current_bet
                
                player.last_action = PlayerAction.ALL_IN
                message = f"{player.nickname} 全下 {all_in_amount} 筹码！"
                
            else:
                return False, "无效的行动。可用操作：跟注、加注、弃牌、让牌、全下"
            
            # 移动到下一个玩家
            self._move_to_next_player(game)
            
            return True, message
            
        except Exception as e:
            logger.error(f"处理玩家行动时出错 {player.nickname}: {e}")
            return False, "处理行动时发生错误"
    
    def _move_to_next_player(self, game: TexasHoldemGame):
        """移动到下一个有效玩家"""
        start_index = game.active_player_index
        
        while True:
            game.active_player_index = (game.active_player_index + 1) % len(game.players)
            next_player = game.players[game.active_player_index]
            
            # 如果回到起始位置，说明下注轮结束
            if game.active_player_index == start_index:
                break
            
            # 找到下一个有效玩家（未弃牌且未全下）
            if not next_player.is_folded and not next_player.is_all_in:
                # 检查是否需要行动（未跟上当前下注）
                if next_player.current_bet < game.current_bet:
                    break
    
    def _check_betting_round_complete(self, game: TexasHoldemGame):
        """检查下注轮是否结束"""
        active_players = [p for p in game.players if not p.is_folded]
        
        # 如果只剩一个玩家，直接结束游戏
        if len(active_players) <= 1:
            self._end_game(game)
            return
        
        # 检查所有有效玩家是否都已跟注或全下
        betting_complete = True
        for player in active_players:
            if not player.is_all_in and player.current_bet < game.current_bet:
                betting_complete = False
                break
        
        if betting_complete:
            # 进入下一阶段
            self._advance_to_next_phase(game)
    
    def _advance_to_next_phase(self, game: TexasHoldemGame):
        """进入下一游戏阶段"""
        # 重置所有玩家的下注状态
        for player in game.players:
            player.current_bet = 0
        game.current_bet = 0
        
        # 设置下一阶段的行动玩家（小盲注位置开始）
        self._set_first_to_act(game)
        
        # 发公共牌并更新阶段
        deck = Deck()
        
        if game.phase == GamePhase.PRE_FLOP:
            # 翻牌：发3张公共牌
            game.community_cards = deck.deal_multiple(3)
            game.phase = GamePhase.FLOP
            
        elif game.phase == GamePhase.FLOP:
            # 转牌：发1张公共牌
            game.community_cards.extend(deck.deal_multiple(1))
            game.phase = GamePhase.TURN
            
        elif game.phase == GamePhase.TURN:
            # 河牌：发1张公共牌
            game.community_cards.extend(deck.deal_multiple(1))
            game.phase = GamePhase.RIVER
            
        elif game.phase == GamePhase.RIVER:
            # 摊牌阶段
            self._showdown(game)
            return
        
        game.update_last_action_time()
    
    def _set_first_to_act(self, game: TexasHoldemGame):
        """设置第一个行动的玩家（小盲注位置开始）"""
        small_blind_index = (game.dealer_index + 1) % len(game.players)
        if len(game.players) == 2:
            small_blind_index = game.dealer_index
        
        # 找到小盲注之后第一个有效玩家
        for i in range(len(game.players)):
            check_index = (small_blind_index + i) % len(game.players)
            player = game.players[check_index]
            if not player.is_folded and not player.is_all_in:
                game.active_player_index = check_index
                break
    
    def _showdown(self, game: TexasHoldemGame):
        """摊牌阶段"""
        game.phase = GamePhase.SHOWDOWN
        
        # 评估所有未弃牌玩家的手牌
        active_players = [p for p in game.players if not p.is_folded]
        player_hands = []
        
        for player in active_players:
            hand_rank, values = HandEvaluator.evaluate_hand(player.hole_cards, game.community_cards)
            player_hands.append((player, hand_rank, values))
        
        # 按手牌强度排序
        player_hands.sort(key=lambda x: (x[1].value, x[2]), reverse=True)
        
        # 分配奖池
        self._distribute_pot(game, player_hands)
        
        # 结束游戏
        self._end_game(game)
    
    def _distribute_pot(self, game: TexasHoldemGame, player_hands: List[Tuple[Player, HandRank, List[int]]]):
        """分配奖池"""
        # 简化处理：暂不考虑边池，直接按手牌强度分配
        if not player_hands:
            return
        
        # 找出最强的手牌
        best_hand = player_hands[0]
        winners = [best_hand[0]]
        
        # 找出所有并列的获胜者
        for player, rank, values in player_hands[1:]:
            comparison = HandEvaluator.compare_hands((rank, values), (best_hand[1], best_hand[2]))
            if comparison == 0:  # 平手
                winners.append(player)
            else:
                break
        
        # 平分奖池
        pot_share = game.pot // len(winners)
        remainder = game.pot % len(winners)
        
        for i, winner in enumerate(winners):
            share = pot_share + (1 if i < remainder else 0)
            winner.add_chips(share)
            winner.hands_won += 1
            
            # 更新统计数据
            self.storage.update_player_stats(
                winner.user_id,
                winner.nickname,
                chips_change=share,
                hands_won=1
            )
    
    def _end_game(self, game: TexasHoldemGame) -> None:
        """
        结束游戏并清理资源
        
        Args:
            game: 游戏对象
        """
        try:
            game.phase = GamePhase.FINISHED
            
            # 更新所有玩家的统计数据
            for player in game.players:
                try:
                    self.storage.update_player_stats(
                        player.user_id,
                        player.nickname,
                        games_played=1
                    )
                except Exception as e:
                    logger.warning(f"更新玩家 {player.nickname} 统计数据失败: {e}")
            
            # 保存游戏历史
            self._save_game_history(game)
            
            # 清理游戏数据
            if game.group_id in self.active_games:
                del self.active_games[game.group_id]
            
            # 删除存储中的游戏数据
            self.storage.delete_game(game.group_id)
            
            # 清理超时任务
            if game.group_id in self.timeouts:
                try:
                    self.timeouts[game.group_id].cancel()
                except Exception as e:
                    logger.warning(f"取消超时任务失败: {e}")
                del self.timeouts[game.group_id]
            
            logger.info(f"游戏结束: {game.game_id}, 参与玩家: {len(game.players)}人")
            
        except Exception as e:
            logger.error(f"结束游戏时发生错误: {e}")
    
    def _save_game_history(self, game: TexasHoldemGame) -> None:
        """
        保存游戏历史记录
        
        Args:
            game: 游戏对象
        """
        try:
            history_data = {
                'game_id': game.game_id,
                'group_id': game.group_id,
                'players': [p.to_dict() for p in game.players],
                'community_cards': [str(card) for card in game.community_cards],
                'pot': game.pot,
                'started_at': game.created_at,
                'ended_at': int(time.time()),
                'small_blind': game.small_blind,
                'big_blind': game.big_blind,
                'phase': game.phase.value
            }
            
            self.storage.save_game_history(game.game_id, history_data)
            logger.debug(f"游戏历史已保存: {game.game_id}")
            
        except Exception as e:
            logger.error(f"保存游戏历史失败: {e}")
    
    def _start_timeout_check(self, group_id: str):
        """启动超时检查"""
        if group_id in self.timeouts:
            self.timeouts[group_id].cancel()
        
        self.timeouts[group_id] = asyncio.create_task(
            self._timeout_check(group_id)
        )
    
    async def _timeout_check(self, group_id: str):
        """超时检查任务"""
        try:
            if group_id not in self.active_games:
                return
            
            game = self.active_games[group_id]
            await asyncio.sleep(game.timeout_seconds)
            
            # 检查游戏是否还在进行且确实超时
            if (group_id in self.active_games and 
                game.phase in [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER] and
                game.is_timeout()):
                
                # 当前玩家超时，自动弃牌
                active_player = game.get_active_player()
                if active_player and not active_player.is_folded:
                    logger.info(f"玩家 {active_player.nickname} 超时自动弃牌")
                    active_player.fold()
                    game.update_last_action_time()
                    
                    # 移动到下一个玩家
                    self._move_to_next_player(game)
                    
                    # 检查下注轮是否结束
                    self._check_betting_round_complete(game)
                    
                    # 保存游戏状态
                    self.storage.save_game(group_id, game.to_dict())
                    
                    # 如果游戏还在进行，继续超时检查
                    if game.phase in [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]:
                        self._start_timeout_check(group_id)
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"超时检查任务出错: {e}")
    
    def get_game_state(self, group_id: str) -> Optional[TexasHoldemGame]:
        """获取游戏状态"""
        return self.active_games.get(group_id)
    
    def load_game_from_storage(self, group_id: str) -> bool:
        """从存储中加载游戏"""
        game_data = self.storage.get_game(group_id)
        if game_data:
            game = TexasHoldemGame.from_dict(game_data)
            self.active_games[group_id] = game
            
            # 如果游戏在进行中，启动超时检查
            if game.phase in [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]:
                self._start_timeout_check(group_id)
            
            return True
        return False
