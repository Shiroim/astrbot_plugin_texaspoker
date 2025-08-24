"""德州扑克游戏管理器

统一的游戏管理，负责：
- 游戏生命周期管理
- 玩家行动协调
- 状态持久化
- 超时处理
"""
import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any, Callable
from ..models.game import TexasHoldemGame, Player, GamePhase
from ..services.game_state_machine import GameStateMachine
from ..services.betting_round_manager import BettingRoundManager
from ..services.player_service import PlayerService
from ..services.renderer import PokerRenderer
from ..utils.storage_manager import StorageManager
from astrbot.api import logger


class GameManager:
    """德州扑克游戏管理器
    
    职责：
    - 统一管理所有游戏实例
    - 协调状态机和下注管理器
    - 处理超时和清理
    - 与外部服务交互
    """
    
    def __init__(self, storage: StorageManager, player_service: PlayerService):
        self.storage = storage
        self.player_service = player_service
        self.renderer = PokerRenderer()
        
        # 核心组件
        self.state_machine = GameStateMachine()
        self.betting_manager = BettingRoundManager()
        
        # 游戏实例管理
        self.active_games: Dict[str, TexasHoldemGame] = {}
        self.timeout_tasks: Dict[str, asyncio.Task] = {}
        self.temp_files: Dict[str, List[str]] = {}
        
        # 并发控制
        self.game_locks: Dict[str, asyncio.Lock] = {}
        
        # 回调函数
        self.action_prompt_callback: Optional[Callable] = None
        
        # 设置状态机回调
        self.state_machine.set_phase_change_callback(self._on_phase_changed)
        
        logger.info("游戏管理器初始化完成")
    
    async def initialize(self):
        """初始化管理器"""
        try:
            await self._restore_games_from_storage()
            logger.info("游戏管理器启动完成")
        except Exception as e:
            logger.error(f"游戏管理器初始化失败: {e}")
            raise
    
    async def terminate(self):
        """终止管理器"""
        try:
            await self._save_all_games()
            await self._cleanup_all_resources()
            logger.info("游戏管理器已安全关闭")
        except Exception as e:
            logger.error(f"游戏管理器关闭失败: {e}")
    
    def set_action_prompt_callback(self, callback: Callable):
        """设置行动提示回调"""
        self.action_prompt_callback = callback
    
    # ==================== 游戏管理方法 ====================
    
    def create_game(self, group_id: str, creator_id: str, creator_nickname: str,
                   small_blind: Optional[int] = None, big_blind: Optional[int] = None) -> Tuple[bool, str, Optional[TexasHoldemGame]]:
        """创建新游戏"""
        try:
            # 检查是否已有游戏
            if group_id in self.active_games:
                return False, "该群已有正在进行的游戏", None
            
            # 获取配置参数
            small_blind = small_blind or self.storage.get_plugin_config_value('small_blind', 1)
            big_blind = big_blind or self.storage.get_plugin_config_value('big_blind', 2)
            default_buyin = self.storage.get_plugin_config_value('default_buyin', 50)
            timeout_seconds = self.storage.get_plugin_config_value('action_timeout', 30)
            
            # 验证参数
            if small_blind <= 0 or big_blind <= 0 or big_blind <= small_blind:
                return False, "盲注设置无效", None
            
            # 处理创建者买入
            buyin_success, buyin_message = self.player_service.can_buyin(creator_id, default_buyin)
            if not buyin_success:
                return False, f"创建失败: {buyin_message}", None
            
            success, message, remaining = self.player_service.process_buyin(creator_id, creator_nickname, default_buyin)
            if not success:
                return False, f"买入失败: {message}", None
            
            # 创建游戏和创建者玩家
            game = TexasHoldemGame(
                game_id=f"{group_id}_{int(time.time())}",
                group_id=group_id,
                small_blind=small_blind,
                big_blind=big_blind,
                timeout_seconds=timeout_seconds
            )
            
            creator = Player(
                user_id=creator_id,
                nickname=creator_nickname,
                chips=default_buyin,
                initial_chips=default_buyin
            )
            
            game.add_player(creator)
            self.active_games[group_id] = game
            self.temp_files[group_id] = []
            
            # 保存到存储
            self.storage.save_game(group_id, game.to_dict())
            
            logger.info(f"游戏创建成功: {game.game_id}")
            return True, f"游戏创建成功！游戏ID: {game.game_id}", game
            
        except Exception as e:
            logger.error(f"创建游戏失败: {e}")
            return False, "创建游戏失败", None
    
    def join_game(self, group_id: str, user_id: str, nickname: str, buyin: Optional[int] = None) -> Tuple[bool, str]:
        """玩家加入游戏"""
        try:
            game = self.active_games.get(group_id)
            if not game:
                return False, "该群没有正在进行的游戏"
            
            if game.phase != GamePhase.WAITING:
                return False, "游戏已开始，无法加入"
            
            if game.get_player(user_id):
                return False, "您已在游戏中"
            
            # 检查人数限制
            max_players = self.storage.get_plugin_config_value('max_players', 9)
            if len(game.players) >= max_players:
                return False, f"游戏人数已满({max_players}人)"
            
            # 处理买入
            buyin = buyin or self.storage.get_plugin_config_value('default_buyin', 50)
            
            buyin_success, buyin_message = self.player_service.can_buyin(user_id, buyin)
            if not buyin_success:
                return False, f"加入失败: {buyin_message}"
            
            success, message, remaining = self.player_service.process_buyin(user_id, nickname, buyin)
            if not success:
                return False, f"买入失败: {message}"
            
            # 创建玩家并加入游戏
            player = Player(
                user_id=user_id,
                nickname=nickname,
                chips=buyin,
                initial_chips=buyin
            )
            
            game.add_player(player)
            self.storage.save_game(group_id, game.to_dict())
            
            logger.info(f"玩家 {nickname} 加入游戏 {game.game_id}")
            return True, f"{nickname} 成功加入游戏！当前玩家数: {len(game.players)}"
            
        except Exception as e:
            logger.error(f"加入游戏失败: {e}")
            return False, "加入游戏失败"
    
    async def start_game(self, group_id: str, user_id: str) -> Tuple[bool, str]:
        """开始游戏"""
        try:
            game = self.active_games.get(group_id)
            if not game:
                return False, "该群没有正在进行的游戏"
            
            if not game.get_player(user_id):
                return False, "您不在游戏中，无法开始游戏"
            
            min_players = self.storage.get_plugin_config_value('min_players', 2)
            if len(game.players) < min_players:
                return False, f"至少需要{min_players}名玩家才能开始游戏"
            
            # 使用状态机开始游戏
            if not self.state_machine.start_game(game):
                return False, "游戏启动失败"
            
            self.storage.save_game(group_id, game.to_dict())
            
            # 启动超时检查
            await self._start_timeout_timer(group_id)
            
            logger.info(f"游戏开始: {game.game_id}")
            return True, f"游戏开始！参与玩家: {len(game.players)}人"
            
        except Exception as e:
            logger.error(f"开始游戏失败: {e}")
            return False, "开始游戏失败"
    
    async def player_action(self, group_id: str, user_id: str, action: str, amount: int = 0) -> Tuple[bool, str]:
        """处理玩家行动"""
        # 获取或创建游戏锁
        if group_id not in self.game_locks:
            self.game_locks[group_id] = asyncio.Lock()
        
        async with self.game_locks[group_id]:
            try:
                game = self.active_games.get(group_id)
                if not game:
                    return False, "该群没有正在进行的游戏"
                
                player = game.get_player(user_id)
                if not player:
                    return False, "您不在游戏中"
                
                # 使用下注管理器处理行动
                success, message = self.betting_manager.process_action(game, player, action, amount)
                if not success:
                    return False, message
                
                # 保存状态
                self.storage.save_game(group_id, game.to_dict())
                
                # 检查下注轮是否结束
                await self._check_and_advance_game(game)
                
                return True, message
                
            except Exception as e:
                logger.error(f"处理玩家行动失败: {e}")
                return False, "行动处理失败"
    
    def get_game_state(self, group_id: str) -> Optional[TexasHoldemGame]:
        """获取游戏状态"""
        return self.active_games.get(group_id)
    
    # ==================== 内部管理方法 ====================
    
    async def _check_and_advance_game(self, game: TexasHoldemGame):
        """检查游戏状态并推进"""
        # 检查是否只剩一个玩家
        active_players = [p for p in game.players if not p.is_folded]
        if len(active_players) <= 1:
            await self._end_game_early(game)
            return
        
        # 检查下注轮是否结束
        if self.betting_manager.is_betting_round_complete(game):
            await self._advance_to_next_phase(game)
        else:
            # 移动到下一个玩家
            next_player_idx = self.betting_manager.find_next_player(game)
            if next_player_idx is not None:
                game.active_player_index = next_player_idx
                await self._send_action_prompt(game)
                await self._start_timeout_timer(game.group_id)
    
    async def _advance_to_next_phase(self, game: TexasHoldemGame):
        """推进到下一阶段"""
        current_phase = game.phase
        
        # 确定下一阶段
        if current_phase == GamePhase.PRE_FLOP:
            next_phase = GamePhase.FLOP
        elif current_phase == GamePhase.FLOP:
            next_phase = GamePhase.TURN
        elif current_phase == GamePhase.TURN:
            next_phase = GamePhase.RIVER
        elif current_phase == GamePhase.RIVER:
            next_phase = GamePhase.SHOWDOWN
        else:
            return
        
        # 检查是否可以直接跳到摊牌（所有人全下）
        active_players = [p for p in game.players if not p.is_folded]
        acting_players = [p for p in active_players if not p.is_all_in]
        
        if len(acting_players) <= 1 and next_phase != GamePhase.SHOWDOWN:
            # 直接跳到摊牌，发完剩余公共牌
            self._deal_remaining_cards(game)
            next_phase = GamePhase.SHOWDOWN
        
        # 执行状态转换
        if self.state_machine.transition_to_phase(game, next_phase):
            self.storage.save_game(game.group_id, game.to_dict())
            
            if next_phase == GamePhase.SHOWDOWN:
                await self._handle_showdown(game)
            else:
                # 开始新的下注轮
                await self._send_action_prompt(game)
                await self._start_timeout_timer(game.group_id)
    
    def _deal_remaining_cards(self, game: TexasHoldemGame):
        """发完剩余公共牌（全下情况）"""
        target_count = 5
        current_count = len(game.community_cards)
        
        if current_count < target_count:
            remaining_cards = game._deck.deal_multiple(target_count - current_count)
            game.community_cards.extend(remaining_cards)
            logger.info(f"快速发完剩余 {len(remaining_cards)} 张公共牌")
    
    async def _handle_showdown(self, game: TexasHoldemGame):
        """处理摊牌"""
        try:
            # 发送摊牌结果
            if self.action_prompt_callback:
                await self.action_prompt_callback(game.group_id, game)
            
            # 结束游戏
            await self._end_game(game)
            
        except Exception as e:
            logger.error(f"处理摊牌失败: {e}")
    
    async def _end_game_early(self, game: TexasHoldemGame):
        """提前结束游戏（只剩一个玩家）"""
        active_players = [p for p in game.players if not p.is_folded]
        if active_players:
            winner = active_players[0]
            winner.add_chips(game.pot)
            winner.hands_won += 1
            
            # 简化的获胜结果
            game.showdown_results = {
                'winners': [winner],
                'player_hands': [(winner, None, [])],
                'pot_distribution': [{'winner': winner.nickname, 'amount': game.pot}]
            }
            
            logger.info(f"游戏 {game.game_id} 提前结束，获胜者: {winner.nickname}")
        
        await self._end_game(game)
    
    async def _end_game(self, game: TexasHoldemGame):
        """结束游戏"""
        try:
            game.phase = GamePhase.FINISHED
            
            # 处理玩家兑现
            for player in game.players:
                if player.chips > 0:
                    success, message = self.player_service.process_cashout(
                        player.user_id, player.nickname, player.chips
                    )
                    if success:
                        logger.debug(f"玩家 {player.nickname} 兑现 {player.chips}K")
                
                # 更新统计数据
                self.storage.update_player_stats(
                    player.user_id,
                    player.nickname,
                    games_played=1
                )
            
            # 保存历史记录
            self._save_game_history(game)
            
            # 清理资源
            await self._cleanup_game_resources(game.group_id)
            
            logger.info(f"游戏结束: {game.game_id}")
            
        except Exception as e:
            logger.error(f"结束游戏失败: {e}")
    
    # ==================== 超时处理 ====================
    
    async def _start_timeout_timer(self, group_id: str):
        """启动简单的超时定时器"""
        # 取消现有定时器
        if group_id in self.timeout_tasks:
            self.timeout_tasks[group_id].cancel()
        
        # 启动新定时器
        game = self.active_games.get(group_id)
        if game and game.phase in [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]:
            self.timeout_tasks[group_id] = asyncio.create_task(
                self._timeout_handler(group_id, game.timeout_seconds)
            )
    
    async def _timeout_handler(self, group_id: str, timeout_seconds: int):
        """超时处理器"""
        try:
            await asyncio.sleep(timeout_seconds)
            
            # 获取或创建游戏锁
            if group_id not in self.game_locks:
                self.game_locks[group_id] = asyncio.Lock()
            
            async with self.game_locks[group_id]:
                game = self.active_games.get(group_id)
                if not game:
                    return
                
                # 检查是否真的超时（可能期间有行动）
                if time.time() - game.last_action_time < timeout_seconds:
                    return
                
                active_player = game.get_active_player()
                if active_player and not active_player.is_folded:
                    logger.info(f"玩家 {active_player.nickname} 超时自动弃牌")
                    
                    # 执行自动弃牌
                    active_player.is_folded = True
                    active_player.has_acted_this_round = True
                    game.last_action_time = int(time.time())
                    
                    # 保存状态并继续游戏
                    self.storage.save_game(group_id, game.to_dict())
                    await self._check_and_advance_game(game)
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"超时处理失败: {e}")
    
    # ==================== 回调和通知 ====================
    
    def _on_phase_changed(self, game: TexasHoldemGame, old_phase: GamePhase, new_phase: GamePhase):
        """阶段变更回调"""
        logger.info(f"游戏 {game.game_id} 阶段变更: {old_phase.value} -> {new_phase.value}")
    
    async def _send_action_prompt(self, game: TexasHoldemGame):
        """发送行动提示"""
        if self.action_prompt_callback:
            try:
                await self.action_prompt_callback(game.group_id, game)
            except Exception as e:
                logger.error(f"发送行动提示失败: {e}")
    
    # ==================== 图像生成方法 ====================
    
    def generate_hand_images(self, group_id: str) -> Dict[str, str]:
        """生成手牌图片"""
        game = self.active_games.get(group_id)
        if not game:
            return {}
        
        hand_images = {}
        for player in game.players:
            if len(player.hole_cards) >= 2:
                try:
                    hand_img = self.renderer.render_hand_cards(player, game)
                    filename = f"hand_{player.user_id}_{game.game_id}.png"
                    img_path = self.renderer.save_image(hand_img, filename)
                    if img_path:
                        hand_images[player.user_id] = img_path
                        self.temp_files[group_id].append(img_path)
                except Exception as e:
                    logger.error(f"生成玩家 {player.nickname} 手牌图片失败: {e}")
        
        return hand_images
    
    def generate_community_image(self, group_id: str) -> Optional[str]:
        """生成公共牌图片"""
        game = self.active_games.get(group_id)
        if not game:
            return None
        
        try:
            community_img = self.renderer.render_community_cards(game)
            filename = f"community_{game.game_id}_{game.phase.value}.png"
            img_path = self.renderer.save_image(community_img, filename)
            if img_path:
                self.temp_files[group_id].append(img_path)
                return img_path
        except Exception as e:
            logger.error(f"生成公共牌图片失败: {e}")
        
        return None
    
    def generate_showdown_image(self, group_id: str) -> Optional[str]:
        """生成摊牌结果图片"""
        game = self.active_games.get(group_id)
        if not game or not hasattr(game, 'showdown_results'):
            return None
        
        try:
            winners = game.showdown_results.get('winners', [])
            if winners:
                showdown_img = self.renderer.render_showdown(game, winners)
                filename = f"showdown_{game.game_id}.png"
                img_path = self.renderer.save_image(showdown_img, filename)
                if img_path:
                    self.temp_files[group_id].append(img_path)
                    return img_path
        except Exception as e:
            logger.error(f"生成摊牌图片失败: {e}")
        
        return None
    
    # ==================== 资源管理 ====================
    
    async def _restore_games_from_storage(self):
        """从存储恢复游戏"""
        all_games = self.storage.get_all_games()
        for group_id, game_data in all_games.items():
            try:
                game = TexasHoldemGame.from_dict(game_data)
                
                # 跳过已结束的游戏
                if game.phase == GamePhase.FINISHED:
                    self.storage.delete_game(group_id)
                    continue
                
                self.active_games[group_id] = game
                self.temp_files[group_id] = []
                
                # 如果是进行中的游戏，恢复超时检查
                if game.phase in [GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]:
                    await self._start_timeout_timer(group_id)
                
                logger.info(f"恢复游戏: {game.game_id}")
                
            except Exception as e:
                logger.warning(f"恢复游戏失败 {group_id}: {e}")
                self.storage.delete_game(group_id)
    
    async def _save_all_games(self):
        """保存所有游戏状态"""
        for group_id, game in self.active_games.items():
            try:
                self.storage.save_game(group_id, game.to_dict())
            except Exception as e:
                logger.warning(f"保存游戏失败 {group_id}: {e}")
    
    async def _cleanup_all_resources(self):
        """清理所有资源"""
        # 取消所有超时任务
        for task in self.timeout_tasks.values():
            task.cancel()
        
        # 等待任务完成
        if self.timeout_tasks:
            await asyncio.gather(*self.timeout_tasks.values(), return_exceptions=True)
        
        # 清理临时文件
        for group_id in list(self.temp_files.keys()):
            await self._cleanup_temp_files(group_id)
        
        self.timeout_tasks.clear()
        self.temp_files.clear()
        self.active_games.clear()
    
    async def _cleanup_game_resources(self, group_id: str):
        """清理单个游戏的资源"""
        # 取消超时任务
        if group_id in self.timeout_tasks:
            self.timeout_tasks[group_id].cancel()
            del self.timeout_tasks[group_id]
        
        # 清理临时文件
        await self._cleanup_temp_files(group_id)
        
        # 删除游戏实例
        if group_id in self.active_games:
            del self.active_games[group_id]
        
        # 删除存储数据
        self.storage.delete_game(group_id)
    
    async def _cleanup_temp_files(self, group_id: str):
        """清理临时文件"""
        if group_id not in self.temp_files:
            return
        
        import os
        for file_path in self.temp_files[group_id]:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败 {file_path}: {e}")
        
        self.temp_files[group_id] = []
    
    def _save_game_history(self, game: TexasHoldemGame):
        """保存游戏历史"""
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
                'big_blind': game.big_blind
            }
            
            self.storage.save_game_history(game.game_id, history_data)
            logger.debug(f"游戏历史已保存: {game.game_id}")
            
        except Exception as e:
            logger.error(f"保存游戏历史失败: {e}")
