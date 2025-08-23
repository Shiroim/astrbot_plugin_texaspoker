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
from .hand_evaluator import HandEvaluator, HandRank
from astrbot.api import logger


class GameEngine:
    """德州扑克游戏引擎"""
    
    def __init__(self, storage, player_service=None):
        self.storage = storage
        self.player_service = player_service
        self.active_games: Dict[str, TexasHoldemGame] = {}
        self.timeouts: Dict[str, asyncio.Task] = {}
        self.timeout_locks: Dict[str, asyncio.Lock] = {}  # 防止超时操作的竞态条件
    
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
            
            # 获取默认买入金额
            default_buyin = self.storage.get_plugin_config_value('default_buyin', 50)  # 50K
            
            # 创建者需要买入才能创建游戏
            if self.player_service:
                # 检查创建者是否已注册并有足够资金
                can_buyin, buyin_msg = self.player_service.can_buyin(creator_id, default_buyin)
                if not can_buyin:
                    return False, f"创建游戏失败: {buyin_msg}", None
                
                # 执行买入
                buyin_success, buyin_msg, remaining_bank = self.player_service.process_buyin(
                    creator_id, creator_nickname, default_buyin
                )
                if not buyin_success:
                    return False, f"创建游戏失败: {buyin_msg}", None
                
                # 创建游戏内玩家对象
                creator = Player(
                    user_id=creator_id,
                    nickname=creator_nickname,
                    chips=default_buyin,  # 买入金额作为游戏内筹码
                    initial_chips=default_buyin  # 记录初始筹码
                )
            else:
                # 后备方案：直接创建Player对象
                creator = Player(
                    user_id=creator_id,
                    nickname=creator_nickname,
                    chips=default_buyin,
                    initial_chips=default_buyin
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
            
            # 获取默认买入金额
            default_buyin = self.storage.get_plugin_config_value('default_buyin', 50)  # 50K
            
            # 玩家需要买入才能加入游戏
            if self.player_service:
                # 检查玩家是否已注册并有足够资金
                can_buyin, buyin_msg = self.player_service.can_buyin(user_id, default_buyin)
                if not can_buyin:
                    return False, f"加入游戏失败: {buyin_msg}"
                
                # 执行买入
                buyin_success, buyin_msg, remaining_bank = self.player_service.process_buyin(
                    user_id, nickname, default_buyin
                )
                if not buyin_success:
                    return False, f"加入游戏失败: {buyin_msg}"
                
                # 创建游戏内玩家对象
                player = Player(
                    user_id=user_id,
                    nickname=nickname,
                    chips=default_buyin,  # 买入金额作为游戏内筹码
                    initial_chips=default_buyin  # 记录初始筹码用于计算盈亏
                )
            else:
                # 后备方案：直接创建Player对象
                player = Player(
                    user_id=user_id,
                    nickname=nickname,
                    chips=default_buyin,
                    initial_chips=default_buyin
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
    
    def join_game_with_buyin(self, group_id: str, user_id: str, nickname: str, buyin_amount: int) -> Tuple[bool, str]:
        """
        玩家以指定买入金额加入游戏
        
        Args:
            group_id: 群组ID
            user_id: 用户ID
            nickname: 用户昵称
            buyin_amount: 买入金额 (K为单位)
            
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
            
            # 验证买入金额范围
            min_buyin = self.storage.get_plugin_config_value('min_buyin', 10)  # 10K
            max_buyin = self.storage.get_plugin_config_value('max_buyin', 200)  # 200K
            
            if buyin_amount < min_buyin:
                return False, f"买入金额过少，最少需要 {min_buyin}K"
            if buyin_amount > max_buyin:
                return False, f"买入金额过多，最多允许 {max_buyin}K"
            
            # 玩家买入
            if self.player_service:
                # 检查玩家是否已注册并有足够资金
                can_buyin, buyin_msg = self.player_service.can_buyin(user_id, buyin_amount)
                if not can_buyin:
                    return False, f"买入失败: {buyin_msg}"
                
                # 执行买入
                buyin_success, buyin_msg, remaining_bank = self.player_service.process_buyin(
                    user_id, nickname, buyin_amount
                )
                if not buyin_success:
                    return False, f"买入失败: {buyin_msg}"
                
                # 创建游戏内玩家对象
                player = Player(
                    user_id=user_id,
                    nickname=nickname,
                    chips=buyin_amount,  # 买入金额作为游戏内筹码
                    initial_chips=buyin_amount  # 记录初始筹码
                )
                
                success_message = f"{nickname} 买入 {buyin_amount}K 成功加入游戏！银行剩余: {remaining_bank}K"
            else:
                # 后备方案：直接创建Player对象
                player = Player(
                    user_id=user_id,
                    nickname=nickname,
                    chips=buyin_amount,
                    initial_chips=buyin_amount
                )
                success_message = f"{nickname} 买入 {buyin_amount}K 成功加入游戏！"
            
            # 添加玩家到游戏
            if game.add_player(player):
                # 保存游戏状态
                self.storage.save_game(group_id, game.to_dict())
                logger.info(f"玩家 {nickname} 买入 {buyin_amount}K 加入游戏 {game.game_id}")
                return True, f"{success_message} 当前玩家数: {len(game.players)}"
            else:
                # 如果添加失败，需要退还买入金额
                if self.player_service:
                    self.player_service.process_cashout(user_id, nickname, buyin_amount)
                return False, "添加玩家失败"
                
        except Exception as e:
            logger.error(f"玩家买入加入游戏时发生错误: {e}")
            return False, "买入加入游戏失败，请稍后重试"
    
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
            # 重置所有玩家状态（增强版本）
            for player in game.players:
                # 重置玩家状态
                player.reset_for_new_hand()
                
                # 验证重置后的状态
                if not player.validate_state():
                    logger.warning(f"玩家 {player.nickname} 状态重置后验证失败")
                    # 尝试修复常见问题
                    if player.chips < 0:
                        player.chips = 0
                    if player.current_bet < 0:
                        player.current_bet = 0
                    
                # 记录玩家状态
                logger.debug(f"玩家 {player.nickname} 重置完成: 筹码{player.chips}, 位置{player.position}")
            
            # 重置游戏状态
            game.community_cards = []
            game.pot = 0
            game.side_pots = []
            game.current_bet = 0
            game.phase = GamePhase.PRE_FLOP
            
            # 创建新牌组并洗牌，保存到游戏对象中以保持一致性
            game._current_deck = Deck()
            game._current_deck.shuffle()
            
            # 验证牌组有足够的牌
            cards_needed = len(game.players) * 2 + 5  # 手牌 + 公共牌
            if game._current_deck.remaining_count() < cards_needed:
                raise ValueError("牌组数量不足")
            
            # 每个玩家发2张手牌
            for player in game.players:
                try:
                    player.hole_cards = game._current_deck.deal_multiple(2)
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
        """设置第一个行动玩家（翻牌前专用，重写的精确逻辑）"""
        player_count = len(game.players)
        
        if player_count < 2:
            logger.error("玩家数量不足，无法设置第一个行动玩家")
            return
        
        # 翻牌前的行动顺序规则
        if player_count == 2:
            # heads-up: 庄家（小盲注）先行动
            first_to_act_index = game.dealer_index
        else:
            # 多人游戏: 大盲注左侧的玩家（Under The Gun, UTG）先行动
            first_to_act_index = (game.dealer_index + 3) % player_count
        
        # 确保第一个行动的玩家是有效的（未弃牌且未全下）
        attempts = 0
        while attempts < player_count:
            player = game.players[first_to_act_index]
            if not player.is_folded and not player.is_all_in:
                game.active_player_index = first_to_act_index
                logger.debug(f"翻牌前第一个行动玩家: {player.nickname} (索引: {first_to_act_index})")
                return
            
            # 移动到下一个玩家
            first_to_act_index = (first_to_act_index + 1) % player_count
            attempts += 1
        
        # 如果没有找到有效玩家（理论上不应该发生）
        logger.warning("翻牌前未找到有效的第一个行动玩家，使用默认位置")
        game.active_player_index = (game.dealer_index + 3) % player_count if player_count > 2 else game.dealer_index
    
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
    
    async def player_action(self, group_id: str, user_id: str, action: str, amount: int = 0) -> Tuple[bool, str]:
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
            
            # 记录当前阶段，用于检测阶段变化
            previous_phase = game.phase
            
            # 处理具体行动
            success, message = self._process_player_action(game, player, action, amount)
            
            if success:
                # 更新行动时间
                game.update_last_action_time()
                
                # 检查是否需要进入下一阶段
                await self._check_betting_round_complete(game)
                
                # 检测阶段变化，并在消息中标记
                if game.phase != previous_phase:
                    game._phase_just_changed = True
                else:
                    game._phase_just_changed = False
                
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
        """移动到下一个有效玩家（完全重写的状态机逻辑）"""
        if len(game.players) == 0:
            logger.warning("没有玩家可以移动到下一个")
            return
        
        original_player_index = game.active_player_index
        attempts = 0
        max_attempts = len(game.players)
        
        while attempts < max_attempts:
            # 移动到下一个玩家
            game.active_player_index = (game.active_player_index + 1) % len(game.players)
            next_player = game.players[game.active_player_index]
            attempts += 1
            
            # 检查玩家是否需要行动
            if self._player_needs_action(next_player, game):
                logger.debug(f"下一个行动玩家: {next_player.nickname} (索引: {game.active_player_index})")
                return
                
            # 如果回到原始玩家，说明这轮下注完成
            if game.active_player_index == original_player_index:
                logger.debug("所有玩家已完成本轮下注")
                break
        
        # 如果没有找到需要行动的玩家，下注轮结束
        logger.debug("本轮下注结束，没有玩家需要继续行动")
    
    def _player_needs_action(self, player: Player, game: TexasHoldemGame) -> bool:
        """
        检查玩家是否需要行动
        
        Args:
            player: 玩家对象
            game: 游戏对象
            
        Returns:
            True表示玩家需要行动，False表示不需要
        """
        # 已弃牌的玩家不需要行动
        if player.is_folded:
            return False
            
        # 已全下的玩家不需要行动
        if player.is_all_in:
            return False
            
        # 检查玩家是否需要跟注或加注
        if player.current_bet < game.current_bet:
            return True
            
        # 如果当前下注为0且玩家也是0，则需要检查是否是新阶段的第一个玩家
        if game.current_bet == 0 and player.current_bet == 0:
            # 在新阶段开始时，所有有效玩家都需要机会行动（check或bet）
            return True
            
        # 其他情况不需要行动
        return False
    
    async def _check_betting_round_complete(self, game: TexasHoldemGame):
        """检查下注轮是否结束（重写的严格逻辑）"""
        active_players = [p for p in game.players if not p.is_folded]
        
        # 如果只剩一个玩家，直接结束游戏
        if len(active_players) <= 1:
            logger.info(f"游戏 {game.game_id} 只剩一个玩家，直接结束")
            await self._end_game(game)
            return
        
        # 检查是否还有玩家需要行动
        players_needing_action = []
        for player in active_players:
            if self._player_needs_action(player, game):
                players_needing_action.append(player.nickname)
        
        if players_needing_action:
            # 还有玩家需要行动，下注轮未完成
            logger.debug(f"还有玩家需要行动: {', '.join(players_needing_action)}")
            return
        
        # 所有玩家都完成了行动，检查下注轮是否真的结束
        if self._is_betting_round_truly_complete(game, active_players):
            logger.info(f"游戏 {game.game_id} 下注轮完成，进入下一阶段")
            await self._advance_to_next_phase(game)
        else:
            logger.debug(f"游戏 {game.game_id} 下注轮未真正完成，继续等待")
    
    def _is_betting_round_truly_complete(self, game: TexasHoldemGame, active_players: list) -> bool:
        """
        严格检查下注轮是否真正完成
        
        Args:
            game: 游戏对象
            active_players: 仍在游戏中的玩家列表
            
        Returns:
            True表示下注轮完成，False表示未完成
        """
        # 获取非全下玩家
        non_allin_players = [p for p in active_players if not p.is_all_in]
        
        # 如果只有全下玩家，下注轮完成
        if len(non_allin_players) <= 1:
            return True
        
        # 检查所有非全下玩家的下注是否一致
        if game.current_bet > 0:
            # 有下注时，所有非全下玩家必须跟上或弃牌
            for player in non_allin_players:
                if player.current_bet < game.current_bet:
                    return False
            return True
        else:
            # 无下注时（全部check），确认所有玩家都有机会行动过
            # 这种情况下，如果当前轮没有加注，则算完成
            return True
    
    async def _advance_to_next_phase(self, game: TexasHoldemGame):
        """进入下一游戏阶段"""
        try:
            # 重置所有玩家的下注状态
            for player in game.players:
                player.current_bet = 0
            game.current_bet = 0
            
            # 设置下一阶段的行动玩家（小盲注位置开始）
            self._set_first_to_act(game)
            
            # 使用游戏中保存的牌组，保持一致性
            deck = getattr(game, '_current_deck', None)
            if not deck:
                # 如果没有保存的牌组，创建新的（兼容性处理）
                deck = Deck()
                game._current_deck = deck
            
            previous_phase = game.phase
            
            if game.phase == GamePhase.PRE_FLOP:
                # 翻牌：发3张公共牌
                game.community_cards = deck.deal_multiple(3)
                game.phase = GamePhase.FLOP
                logger.info(f"游戏 {game.game_id} 进入翻牌圈")
                
            elif game.phase == GamePhase.FLOP:
                # 转牌：发1张公共牌
                game.community_cards.extend(deck.deal_multiple(1))
                game.phase = GamePhase.TURN
                logger.info(f"游戏 {game.game_id} 进入转牌圈")
                
            elif game.phase == GamePhase.TURN:
                # 河牌：发1张公共牌
                game.community_cards.extend(deck.deal_multiple(1))
                game.phase = GamePhase.RIVER
                logger.info(f"游戏 {game.game_id} 进入河牌圈")
                
            elif game.phase == GamePhase.RIVER:
                # 摊牌阶段
                logger.info(f"游戏 {game.game_id} 进入摊牌阶段")
                await self._showdown(game)
                return
            
            # 检查是否所有有效玩家都已全下，如果是则直接跳到摊牌
            active_players = [p for p in game.players if not p.is_folded]
            non_all_in_players = [p for p in active_players if not p.is_all_in]
            
            if len(non_all_in_players) <= 1:
                # 只有一个或没有非全下玩家，直接跳到摊牌
                logger.info(f"游戏 {game.game_id} 所有玩家已全下或弃牌，跳转到摊牌")
                if game.phase != GamePhase.RIVER:
                    # 快速发完剩余公共牌
                    self._deal_remaining_community_cards(game, deck)
                await self._showdown(game)
                return
            
            game.update_last_action_time()
            logger.debug(f"阶段转换完成: {previous_phase.value} -> {game.phase.value}")
            
        except Exception as e:
            logger.error(f"阶段切换时发生错误: {e}")
            raise
    
    def _deal_remaining_community_cards(self, game: TexasHoldemGame, deck: Deck):
        """发完剩余的公共牌（当所有玩家全下时使用）"""
        try:
            # 根据当前阶段发完剩余公共牌
            if game.phase == GamePhase.PRE_FLOP:
                # 发翻牌（3张）+ 转牌（1张）+ 河牌（1张）= 5张
                remaining_cards = deck.deal_multiple(5)
                game.community_cards.extend(remaining_cards)
                game.phase = GamePhase.RIVER
            elif game.phase == GamePhase.FLOP:
                # 发转牌（1张）+ 河牌（1张）= 2张
                remaining_cards = deck.deal_multiple(2) 
                game.community_cards.extend(remaining_cards)
                game.phase = GamePhase.RIVER
            elif game.phase == GamePhase.TURN:
                # 发河牌（1张）
                remaining_cards = deck.deal_multiple(1)
                game.community_cards.extend(remaining_cards) 
                game.phase = GamePhase.RIVER
            
            logger.info(f"快速发完剩余公共牌，当前公共牌数量: {len(game.community_cards)}")
            
        except Exception as e:
            logger.error(f"发剩余公共牌时出错: {e}")
    
    def _set_first_to_act(self, game: TexasHoldemGame):
        """设置第一个行动的玩家（重写的精确逻辑）"""
        player_count = len(game.players)
        if player_count == 0:
            logger.warning("没有玩家，无法设置第一个行动者")
            return
        
        # 在翻牌后阶段，从小盲注开始（如果小盲注还在游戏中）
        # 如果是heads-up（2人），庄家是小盲注
        if player_count == 2:
            start_index = game.dealer_index  # 庄家/小盲注先行动
        else:
            start_index = (game.dealer_index + 1) % player_count  # 小盲注位置
        
        # 找到第一个有效的玩家（未弃牌且未全下）
        for i in range(player_count):
            check_index = (start_index + i) % player_count
            player = game.players[check_index]
            
            if not player.is_folded and not player.is_all_in:
                game.active_player_index = check_index
                logger.debug(f"设置第一个行动玩家: {player.nickname} (索引: {check_index})")
                return
        
        # 如果没有找到有效玩家（理论上不应该发生）
        logger.warning("未找到有效的第一个行动玩家")
        game.active_player_index = start_index
    
    async def _showdown(self, game: TexasHoldemGame):
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
        await self._end_game(game)
    
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
    
    async def _end_game(self, game: TexasHoldemGame) -> None:
        """
        结束游戏并清理资源
        
        Args:
            game: 游戏对象
        """
        try:
            game.phase = GamePhase.FINISHED
            
            # 处理所有玩家的游戏结束兑现
            for player in game.players:
                try:
                    # 更新统计数据
                    self.storage.update_player_stats(
                        player.user_id,
                        player.nickname,
                        games_played=1
                    )
                    
                    # 兑现玩家剩余筹码回银行
                    if player.chips > 0 and self.player_service:
                        cashout_success, cashout_msg = self.player_service.process_cashout(
                            player.user_id, player.nickname, player.chips
                        )
                        if cashout_success:
                            logger.info(f"玩家 {player.nickname} 兑现 {player.chips}K 回银行")
                        else:
                            logger.warning(f"玩家 {player.nickname} 兑现失败: {cashout_msg}")
                            
                except Exception as e:
                    logger.warning(f"处理玩家 {player.nickname} 游戏结束数据失败: {e}")
            
            # 保存游戏历史
            self._save_game_history(game)
            
            # 清理游戏数据
            if game.group_id in self.active_games:
                del self.active_games[game.group_id]
            
            # 删除存储中的游戏数据
            self.storage.delete_game(game.group_id)
            
            # 安全清理超时任务
            await self._safe_cleanup_timeout(game.group_id)
            
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
        """启动超时检查（线程安全版本）"""
        # 创建异步任务来处理超时检查，避免阻塞
        asyncio.create_task(self._async_start_timeout_check(group_id))
    
    async def _async_start_timeout_check(self, group_id: str):
        """异步启动超时检查，防止竞态条件"""
        try:
            # 确保该组有锁
            if group_id not in self.timeout_locks:
                self.timeout_locks[group_id] = asyncio.Lock()
            
            # 使用锁防止竞态条件
            async with self.timeout_locks[group_id]:
                # 取消现有的超时任务
                if group_id in self.timeouts:
                    old_task = self.timeouts[group_id]
                    if not old_task.done():
                        old_task.cancel()
                        try:
                            await old_task
                        except asyncio.CancelledError:
                            pass
                    del self.timeouts[group_id]
                
                # 检查游戏是否还存在且需要超时检查
                if group_id in self.active_games:
                    game = self.active_games[group_id]
                    if game.phase in [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]:
                        # 启动新的超时任务
                        self.timeouts[group_id] = asyncio.create_task(
                            self._timeout_check(group_id)
                        )
                        logger.debug(f"为游戏 {group_id} 启动超时检查")
        
        except Exception as e:
            logger.error(f"启动超时检查失败: {e}")
    
    async def _timeout_check(self, group_id: str):
        """超时检查任务（增强的线程安全版本）"""
        timeout_start_time = time.time()
        
        try:
            # 检查游戏是否存在
            if group_id not in self.active_games:
                logger.debug(f"游戏 {group_id} 不存在，取消超时检查")
                return
            
            game = self.active_games[group_id]
            initial_phase = game.phase
            initial_last_action_time = game.last_action_time
            
            # 等待超时时间
            await asyncio.sleep(game.timeout_seconds)
            
            # 使用锁进行超时处理，防止与其他操作冲突
            if group_id not in self.timeout_locks:
                self.timeout_locks[group_id] = asyncio.Lock()
                
            async with self.timeout_locks[group_id]:
                # 重新检查游戏状态（可能在等待期间已改变）
                if group_id not in self.active_games:
                    logger.debug(f"游戏 {group_id} 已结束，取消超时处理")
                    return
                
                game = self.active_games[group_id]
                
                # 检查游戏阶段是否改变（说明已有其他操作）
                if game.phase != initial_phase:
                    logger.debug(f"游戏 {group_id} 阶段已改变 ({initial_phase} -> {game.phase})，取消超时处理")
                    return
                
                # 检查最后行动时间是否改变（说明有新的行动）
                if game.last_action_time != initial_last_action_time:
                    logger.debug(f"游戏 {group_id} 已有新行动，取消超时处理")
                    return
                
                # 严格检查是否真的超时
                current_time = time.time()
                time_since_last_action = current_time - game.last_action_time
                
                if time_since_last_action < game.timeout_seconds:
                    logger.debug(f"游戏 {group_id} 未真正超时 ({time_since_last_action:.1f}s < {game.timeout_seconds}s)")
                    return
                
                # 确认游戏在可超时的阶段
                if game.phase not in [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]:
                    logger.debug(f"游戏 {group_id} 不在可超时阶段: {game.phase}")
                    return
                
                # 获取当前行动玩家并执行超时处理
                active_player = game.get_active_player()
                if not active_player or active_player.is_folded:
                    logger.debug(f"游戏 {group_id} 没有有效的行动玩家")
                    return
                
                logger.info(f"游戏 {group_id} 玩家 {active_player.nickname} 超时自动弃牌")
                
                # 执行超时弃牌
                active_player.fold()
                game.update_last_action_time()
                
                # 移动到下一个玩家
                self._move_to_next_player(game)
                
                # 检查下注轮是否结束
                await self._check_betting_round_complete(game)
                
                # 保存游戏状态
                self.storage.save_game(group_id, game.to_dict())
                
                # 如果游戏还在进行，启动下一轮超时检查
                if (group_id in self.active_games and 
                    game.phase in [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]):
                    
                    next_active_player = game.get_active_player()
                    if next_active_player:
                        logger.debug(f"游戏 {group_id} 继续超时检查，下一个玩家: {next_active_player.nickname}")
                        self._start_timeout_check(group_id)
                    else:
                        logger.debug(f"游戏 {group_id} 没有下一个行动玩家")
            
        except asyncio.CancelledError:
            # 任务被取消，这是正常情况
            logger.debug(f"游戏 {group_id} 超时检查任务被取消")
            pass
        except Exception as e:
            logger.error(f"游戏 {group_id} 超时检查任务出错: {e}")
        finally:
            # 清理超时任务记录
            try:
                if group_id in self.timeouts and not self.timeouts[group_id].done():
                    pass  # 任务仍在运行，不删除
                elif group_id in self.timeouts:
                    del self.timeouts[group_id]
            except Exception as e:
                logger.warning(f"清理超时任务记录失败: {e}")
    
    async def _safe_cleanup_timeout(self, group_id: str):
        """安全清理超时任务（防止竞态条件）"""
        try:
            # 确保有锁
            if group_id not in self.timeout_locks:
                self.timeout_locks[group_id] = asyncio.Lock()
            
            async with self.timeout_locks[group_id]:
                if group_id in self.timeouts:
                    task = self.timeouts[group_id]
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    del self.timeouts[group_id]
                    logger.debug(f"已安全清理游戏 {group_id} 的超时任务")
                
                # 清理锁（如果不再需要）
                if group_id not in self.active_games:
                    if group_id in self.timeout_locks:
                        del self.timeout_locks[group_id]
                        
        except Exception as e:
            logger.warning(f"安全清理超时任务失败 {group_id}: {e}")
    
    def _cleanup_timeout_sync(self, group_id: str):
        """同步版本的超时清理（用于同步方法）"""
        asyncio.create_task(self._safe_cleanup_timeout(group_id))
    
    def get_game_state(self, group_id: str) -> Optional[TexasHoldemGame]:
        """获取游戏状态"""
        return self.active_games.get(group_id)
    
    def cleanup_finished_game(self, group_id: str) -> bool:
        """清理已结束的游戏"""
        try:
            if group_id in self.active_games:
                game = self.active_games[group_id]
                if game.phase == GamePhase.FINISHED:
                    # 删除活动游戏
                    del self.active_games[group_id]
                    
                    # 删除存储中的游戏数据
                    self.storage.delete_game(group_id)
                    
                    # 清理超时任务
                    self._cleanup_timeout_sync(group_id)
                    
                    logger.info(f"已清理结束的游戏: {game.game_id}")
                    return True
            return False
        except Exception as e:
            logger.error(f"清理游戏时发生错误: {e}")
            return False
    
    def load_game_from_storage(self, group_id: str) -> bool:
        """从存储中加载游戏"""
        game_data = self.storage.get_game(group_id)
        if game_data:
            game = TexasHoldemGame.from_dict(game_data)
            
            # 如果游戏已结束，直接清理而不加载
            if game.phase == GamePhase.FINISHED:
                logger.info(f"跳过加载已结束的游戏: {game.game_id}")
                self.storage.delete_game(group_id)
                return False
            
            self.active_games[group_id] = game
            
            # 如果游戏在进行中，启动超时检查
            if game.phase in [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]:
                self._start_timeout_check(group_id)
            
            return True
        return False
