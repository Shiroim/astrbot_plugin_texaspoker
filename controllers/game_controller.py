"""德州扑克游戏控制器

专门负责游戏逻辑控制和流程管理
"""
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from ..models.game import TexasHoldemGame, Player, GamePhase
from ..services.game_engine import GameEngine
from ..services.renderer import PokerRenderer
from ..services.player_service import PlayerService
from ..utils.storage_manager import StorageManager
from ..utils.error_handler import GameError, ValidationError
from ..utils.decorators import error_handler, validate_params
from astrbot.api import logger


class GameController:
    """
    德州扑克游戏控制器
    
    职责：
    - 游戏创建和管理
    - 玩家行动处理
    - 游戏状态控制
    - 图像渲染协调
    """
    
    def __init__(self, storage: StorageManager, player_service: PlayerService):
        self.storage = storage
        self.player_service = player_service
        self.game_engine = GameEngine(storage, player_service)
        self.renderer = PokerRenderer()
        
        # 临时文件管理
        self.temp_files: Dict[str, List[str]] = {}
        
        # 行动提示回调
        self.action_prompt_callback = None
        
        logger.info("游戏控制器初始化完成")
    
    async def initialize(self) -> None:
        """初始化控制器，恢复游戏状态"""
        try:
            await self._restore_active_games()
            # 设置游戏引擎的行动提示回调
            self.game_engine.set_action_prompt_callback(self._send_action_prompt)
            logger.info("游戏控制器启动完成")
        except Exception as e:
            logger.error(f"游戏控制器初始化失败: {e}")
            raise GameError("控制器初始化失败", str(e))
    
    async def terminate(self) -> None:
        """安全关闭控制器"""
        try:
            await self._save_all_games()
            await self._cleanup_resources()
            logger.info("游戏控制器已安全关闭")
        except Exception as e:
            logger.error(f"游戏控制器关闭时出错: {e}")
    
    @error_handler("创建游戏")
    @validate_params
    async def create_game(self, group_id: str, creator_id: str, creator_nickname: str,
                         small_blind: Optional[int] = None, big_blind: Optional[int] = None) -> Tuple[bool, str, Optional[TexasHoldemGame]]:
        """创建新游戏"""
        try:
            # 参数验证
            self._validate_blind_params(small_blind, big_blind)
            
            # 使用游戏引擎创建游戏
            success, message, game = self.game_engine.create_game(
                group_id, creator_id, creator_nickname, small_blind, big_blind
            )
            
            if success and game:
                # 初始化临时文件跟踪
                self.temp_files[group_id] = []
                logger.info(f"游戏创建成功: {game.game_id}")
            
            return success, message, game
            
        except ValidationError as e:
            return False, str(e), None
        except Exception as e:
            logger.error(f"创建游戏时发生错误: {e}")
            return False, "系统错误，请稍后重试", None
    
    @error_handler("加入游戏")
    async def join_game_with_buyin(self, group_id: str, user_id: str, nickname: str, 
                                  buyin_amount: int) -> Tuple[bool, str]:
        """玩家买入加入游戏"""
        try:
            # 验证买入金额
            self._validate_buyin_amount(buyin_amount)
            
            return self.game_engine.join_game_with_buyin(group_id, user_id, nickname, buyin_amount)
            
        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            logger.error(f"加入游戏失败: {e}")
            return False, "加入游戏失败，请稍后重试"
    
    @error_handler("开始游戏")
    async def start_game(self, group_id: str, user_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """开始游戏并生成所需图片"""
        try:
            # 启动游戏
            success, message = self.game_engine.start_game(group_id, user_id)
            if not success:
                return False, message, None
            
            # 生成游戏图片
            game_images = await self._generate_game_start_images(group_id)
            
            return True, message, game_images
            
        except Exception as e:
            logger.error(f"开始游戏失败: {e}")
            return False, "开始游戏失败，请稍后重试", None
    
    @error_handler("玩家行动")
    async def handle_player_action(self, group_id: str, user_id: str, action: str, 
                                  amount: int = 0) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """处理玩家行动并生成相应图片"""
        try:
            # 记录当前阶段
            game = self.game_engine.get_game_state(group_id)
            previous_phase = game.phase if game else None
            
            # 执行行动 - 修复: 添加await
            success, message = await self.game_engine.player_action(group_id, user_id, action, amount)
            if not success:
                return False, message, None
            
            # 生成相应的图片和数据
            result_data = await self._generate_action_result_images(group_id, previous_phase)
            
            return True, message, result_data
            
        except Exception as e:
            logger.error(f"处理玩家行动失败: {e}")
            return False, "处理行动失败，请稍后重试", None
    
    def get_game_state(self, group_id: str) -> Optional[TexasHoldemGame]:
        """获取游戏状态"""
        return self.game_engine.get_game_state(group_id)
    
    def set_action_prompt_callback(self, callback):
        """设置行动提示回调函数"""
        self.action_prompt_callback = callback
    
    async def cleanup_finished_game(self, group_id: str) -> bool:
        """清理已结束的游戏"""
        try:
            # 清理游戏引擎中的游戏
            if self.game_engine.cleanup_finished_game(group_id):
                # 清理临时文件
                await self._cleanup_temp_files(group_id)
                return True
            return False
        except Exception as e:
            logger.error(f"清理游戏失败: {e}")
            return False
    
    async def _restore_active_games(self) -> None:
        """恢复进行中的游戏"""
        all_games = self.storage.get_all_games()
        for group_id in all_games.keys():
            try:
                if self.game_engine.load_game_from_storage(group_id):
                    self.temp_files[group_id] = []
                    logger.debug(f"恢复游戏: {group_id}")
            except Exception as e:
                logger.warning(f"恢复游戏失败 {group_id}: {e}")
    
    async def _save_all_games(self) -> None:
        """保存所有游戏状态"""
        for group_id, game in self.game_engine.active_games.items():
            try:
                self.storage.save_game(group_id, game.to_dict())
            except Exception as e:
                logger.warning(f"保存游戏状态失败 {group_id}: {e}")
    
    async def _cleanup_resources(self) -> None:
        """清理所有资源"""
        # 取消所有超时任务
        for task in self.game_engine.timeouts.values():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 清理所有临时文件
        for group_id in list(self.temp_files.keys()):
            await self._cleanup_temp_files(group_id)
        
        self.temp_files.clear()
    
    async def _generate_game_start_images(self, group_id: str) -> Dict[str, Any]:
        """生成游戏开始时的图片"""
        game = self.game_engine.get_game_state(group_id)
        if not game:
            return {}
        
        result = {}
        
        try:
            # 生成手牌图片给每个玩家
            hand_images = {}
            for player in game.players:
                if len(player.hole_cards) >= 2:
                    hand_img = self.renderer.render_hand_cards(player, game)
                    filename = f"hand_{player.user_id}_{game.game_id}.png"
                    img_path = self.renderer.save_image(hand_img, filename)
                    if img_path:
                        hand_images[player.user_id] = img_path
                        self.temp_files[group_id].append(img_path)
            
            # 生成公共牌区域
            community_img = self.renderer.render_community_cards(game)
            community_filename = f"community_{game.game_id}_{game.phase.value}.png"
            community_path = self.renderer.save_image(community_img, community_filename)
            if community_path:
                self.temp_files[group_id].append(community_path)
            
            result = {
                'hand_images': hand_images,
                'community_image': community_path,
                'game_info': self._build_game_info(game)
            }
            
        except Exception as e:
            logger.error(f"生成游戏开始图片失败: {e}")
        
        return result
    
    async def _generate_action_result_images(self, group_id: str, previous_phase: Optional[GamePhase]) -> Dict[str, Any]:
        """生成行动结果图片"""
        game = self.game_engine.get_game_state(group_id)
        if not game:
            return {}
        
        result = {}
        
        try:
            # 检查是否进入新阶段，需要更新公共牌
            if game.phase != previous_phase and game.phase.value in ["flop", "turn", "river"]:
                community_img = self.renderer.render_community_cards(game)
                community_filename = f"community_{game.game_id}_{game.phase.value}.png"
                community_path = self.renderer.save_image(community_img, community_filename)
                if community_path:
                    self.temp_files[group_id].append(community_path)
                    result['community_image'] = community_path
            
            # 检查是否游戏结束，生成结算图片
            if game.phase == GamePhase.SHOWDOWN:
                # 获取正确的获胜者信息
                winners = []
                if hasattr(game, 'showdown_results') and game.showdown_results:
                    winners = game.showdown_results['winners']
                else:
                    # 备用方案：简化处理
                    active_players = [p for p in game.players if not p.is_folded]
                    winners = active_players[:1] if active_players else []
                
                if winners:
                    showdown_img = self.renderer.render_showdown(game, winners)
                    showdown_filename = f"showdown_{game.game_id}.png"
                    showdown_path = self.renderer.save_image(showdown_img, showdown_filename)
                    if showdown_path:
                        self.temp_files[group_id].append(showdown_path)
                        result['showdown_image'] = showdown_path
            
            result['game_info'] = self._build_game_info(game)
            
        except Exception as e:
            logger.error(f"生成行动结果图片失败: {e}")
        
        return result
    
    def _build_game_info(self, game: TexasHoldemGame) -> Dict[str, Any]:
        """构建游戏信息字典"""
        return {
            'game_id': game.game_id,
            'phase': game.phase.value,
            'pot': game.pot,
            'current_bet': game.current_bet,
            'player_count': len(game.players),
            'active_player': game.get_active_player().nickname if game.get_active_player() else None
        }
    
    async def _cleanup_temp_files(self, group_id: str) -> None:
        """清理指定群组的临时文件"""
        if group_id not in self.temp_files:
            return
        
        for file_path in self.temp_files[group_id]:
            try:
                import os
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"已删除临时文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败 {file_path}: {e}")
        
        self.temp_files[group_id] = []
    
    def _validate_blind_params(self, small_blind: Optional[int], big_blind: Optional[int]) -> None:
        """验证盲注参数"""
        if small_blind is not None and small_blind <= 0:
            raise ValidationError("小盲注必须大于0")
        if big_blind is not None and big_blind <= 0:
            raise ValidationError("大盲注必须大于0")
        if (small_blind is not None and big_blind is not None and 
            big_blind <= small_blind):
            raise ValidationError("大盲注必须大于小盲注")
    
    def _validate_buyin_amount(self, buyin_amount: int) -> None:
        """验证买入金额"""
        min_buyin = self.storage.get_plugin_config_value('min_buyin', 10)
        max_buyin = self.storage.get_plugin_config_value('max_buyin', 200)
        
        if buyin_amount < min_buyin:
            raise ValidationError(f"买入金额过少，最少需要 {min_buyin}K")
        if buyin_amount > max_buyin:
            raise ValidationError(f"买入金额过多，最多允许 {max_buyin}K")
    
    async def _send_action_prompt(self, group_id: str, game) -> None:
        """发送行动提示消息"""
        try:
            if not self.action_prompt_callback:
                return
            
            # 获取当前行动的玩家
            active_player = game.get_active_player()
            if not active_player:
                return
            
            # 构建行动提示消息
            prompt_message = self._build_action_prompt_message(game, active_player)
            
            # 通过回调发送消息
            await self.action_prompt_callback(group_id, prompt_message)
            
        except Exception as e:
            logger.error(f"发送行动提示失败: {e}")
    
    def _build_action_prompt_message(self, game, active_player) -> str:
        """构建行动提示消息"""
        from ..utils.money_formatter import fmt_chips
        
        phase_names = {
            "pre_flop": "翻牌前",
            "flop": "翻牌圈", 
            "turn": "转牌圈",
            "river": "河牌圈"
        }
        
        phase_name = phase_names.get(game.phase.value, game.phase.value.upper())
        
        lines = [
            f"🎯 轮到 {active_player.nickname} 行动",
            "",
            f"📊 游戏状态:",
            f"• 阶段: {phase_name}",
            f"• 底池: {fmt_chips(game.pot)}",
            f"• 当前下注: {fmt_chips(game.current_bet) if game.current_bet > 0 else '无'}",
            f"• 玩家筹码: {fmt_chips(active_player.chips)}",
            f"• 已下注: {fmt_chips(active_player.current_bet)}",
            "",
            "💡 可用操作:"
        ]
        
        # 计算可用操作
        available_actions = self._get_available_actions(game, active_player)
        for action in available_actions:
            lines.append(f"• {action}")
        
        return "\n".join(lines)
    
    def _get_available_actions(self, game, active_player) -> List[str]:
        """获取玩家可用的操作列表"""
        actions = []
        
        call_amount = game.current_bet - active_player.current_bet
        
        if call_amount == 0:
            # 没有下注，可以让牌
            actions.append("/让牌 - 不下注继续游戏")
        else:
            # 有下注，可以跟注
            from ..utils.money_formatter import fmt_chips
            actions.append(f"/跟注 - 跟上 {fmt_chips(call_amount)}")
        
        # 弃牌总是可用
        actions.append("/弃牌 - 放弃当前手牌")
        
        # 加注 (如果有足够筹码)
        if active_player.chips > call_amount:
            min_raise = max(game.big_blind, call_amount)
            if active_player.chips > min_raise:
                from ..utils.money_formatter import fmt_chips
                actions.append(f"/加注 [金额] - 最少加注 {fmt_chips(min_raise)}")
        
        # 全下 (如果有筹码)
        if active_player.chips > 0:
            from ..utils.money_formatter import fmt_chips
            actions.append(f"/全下 - 押上所有 {fmt_chips(active_player.chips)}")
        
        return actions
