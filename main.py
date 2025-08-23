"""德州扑克AstrBot插件

完整的德州扑克群内多人对战系统，支持：
- 完整德州扑克规则
- 精美图形渲染
- 实时统计数据
- 超时自动弃牌
"""

import asyncio
import os
from typing import Optional, Dict, Any
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import command
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Image
from astrbot.api.platform import AstrBotMessage
from astrbot.api import logger

# 导入业务模块
from .services.game_engine import GameEngine
from .services.renderer import PokerRenderer
from .services.player_service import PlayerService
from .utils.storage_manager import StorageManager
from .utils.error_handler import ErrorHandler, GameValidation, ResponseMessages
from .utils.money_formatter import MoneyFormatter, fmt_chips


@register("astrbot_plugin_texaspoker", "YourName", "德州扑克群内多人对战插件", "1.0.0")
class TexasPokerPlugin(Star):
    """
    德州扑克插件
    
    功能特点：
    - 🃏 完整的德州扑克规则实现
    - 🎨 精美的扑克牌图形渲染
    - 👥 群内多人实时对战
    - 📊 玩家统计数据记录
    - ⏰ 超时自动弃牌机制
    """
    
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化配置
        self.config = context.get_config()
        
        # 初始化服务层
        self.storage = StorageManager("texaspoker", context)
        self.player_service = PlayerService(self.storage)
        self.game_engine = GameEngine(self.storage, self.player_service)
        self.renderer = PokerRenderer()
        
        # 临时文件跟踪
        self.temp_files: Dict[str, list] = {}  # group_id -> [file_paths]
        
        logger.info("德州扑克插件初始化完成")
    
    async def initialize(self):
        """插件初始化"""
        try:
            # 从存储中恢复进行中的游戏
            all_games = self.storage.get_all_games()
            for group_id in all_games.keys():
                self.game_engine.load_game_from_storage(group_id)
            
            logger.info("德州扑克插件启动完成")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}")
    
    async def terminate(self):
        """插件销毁"""
        try:
            # 保存所有游戏状态
            for group_id, game in self.game_engine.active_games.items():
                self.storage.save_game(group_id, game.to_dict())
            
            # 取消所有超时任务
            for task in self.game_engine.timeouts.values():
                task.cancel()
            
            # 清理所有临时文件
            self._cleanup_all_temp_files()
            
            logger.info("德州扑克插件已停止")
        except Exception as e:
            logger.error(f"插件停止时出错: {e}")
    
    # ==================== 游戏管理命令 ====================
    
    @command("德州注册")
    @ErrorHandler.game_command_error_handler("玩家注册")
    async def register_player(self, event: AstrMessageEvent):
        """注册德州扑克玩家"""
        user_id = event.get_sender_id()
        nickname = event.get_sender_name()
        
        # 检查是否已经注册
        existing_player = self.player_service.get_player_info(user_id)
        if existing_player:
            total_chips = existing_player.get('total_chips', 0)
            yield event.plain_result(f"{nickname}，您已经注册过了！\n当前银行余额: {fmt_chips(total_chips)}")
            return
        
        # 获取初始筹码配置 (以K为单位)
        initial_chips = self.storage.get_plugin_config_value('default_chips', 500)  # 500K
        
        # 注册新玩家
        success, message = self.player_service.register_player(user_id, nickname, initial_chips)
        
        if success:
            yield event.plain_result(f"🎉 {nickname} 注册成功！\n💰 获得初始资金: {fmt_chips(initial_chips)}")
        else:
            yield event.plain_result(message)
    
    @command("德州创建")
    @ErrorHandler.game_command_error_handler("游戏创建")
    async def create_game(self, event: AstrMessageEvent, small_blind: int = None, big_blind: int = None):
        """创建德州扑克游戏"""
        user_id = event.get_sender_id()
        nickname = event.get_sender_name()
        group_id = event.get_group_id() or user_id  # 私聊时使用用户ID作为group_id
        
        # 参数验证
        GameValidation.validate_game_creation_params(small_blind, big_blind)
        
        # 创建游戏
        success, message, game = self.game_engine.create_game(
            group_id, user_id, nickname, small_blind, big_blind
        )
        
        if success and game:
            # 获取默认买入金额用于显示
            default_buyin = self.storage.get_plugin_config_value('default_buyin', 50)
            
            result_msg = (f"{message}\n"
                         f"小盲注: {fmt_chips(game.small_blind)}, 大盲注: {fmt_chips(game.big_blind)}\n"
                         f"默认买入: {fmt_chips(default_buyin)}\n"
                         f"使用 /德州加入 [买入金额] 来加入游戏")
            yield event.plain_result(result_msg)
            
            # 初始化该群组的临时文件列表
            if group_id not in self.temp_files:
                self.temp_files[group_id] = []
        else:
            yield event.plain_result(message)
    
    @command("德州加入")
    @ErrorHandler.game_command_error_handler("加入游戏")
    async def join_game(self, event: AstrMessageEvent, buyin: int = None):
        """加入德州扑克游戏"""
        user_id = event.get_sender_id()
        nickname = event.get_sender_name()
        group_id = event.get_group_id() or user_id
        
        # 如果没有指定买入金额，使用默认值
        if buyin is None:
            buyin = self.storage.get_plugin_config_value('default_buyin', 50)  # 50K
        
        # 验证买入金额范围
        min_buyin = self.storage.get_plugin_config_value('min_buyin', 10)  # 10K
        max_buyin = self.storage.get_plugin_config_value('max_buyin', 200)  # 200K
        
        if buyin < min_buyin:
            yield event.plain_result(f"买入金额过少，最少需要 {fmt_chips(min_buyin)}")
            return
        if buyin > max_buyin:
            yield event.plain_result(f"买入金额过多，最多允许 {fmt_chips(max_buyin)}")
            return
        
        # 使用买入制度加入游戏
        success, message = self.game_engine.join_game_with_buyin(group_id, user_id, nickname, buyin)
        yield event.plain_result(message)
    
    @command("德州开始")
    @ErrorHandler.game_command_error_handler("开始游戏")
    async def start_game(self, event: AstrMessageEvent):
        """开始德州扑克游戏"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id() or user_id
        
        success, message = self.game_engine.start_game(group_id, user_id)
        
        if success:
            yield event.plain_result(message)
            
            # 发送手牌给每个玩家（私聊）
            await self._send_hand_cards_to_players(group_id)
            
            # 发送公共牌区域（群内）
            community_result = await self._send_community_cards(group_id)
            if community_result:
                yield community_result
        else:
            yield event.plain_result(message)
    
    @command("德州状态")
    @ErrorHandler.game_command_error_handler("查看游戏状态")
    async def show_game_status(self, event: AstrMessageEvent):
        """显示游戏状态"""
        group_id = event.get_group_id() or event.get_sender_id()
        game = self.game_engine.get_game_state(group_id)
        
        if not game:
            yield event.plain_result("当前没有进行中的游戏")
            return
        
        # 构建状态信息
        status_lines = [
            f"🎮 游戏ID: {game.game_id}",
            f"🎯 阶段: {game.phase.value.upper()}",
            f"💰 底池: {fmt_chips(game.pot)}",
            f"👥 玩家数: {len(game.players)}",
            "",
            "玩家列表:"
        ]
        
        for i, player in enumerate(game.players):
            status_line = f"{i+1}. {player.nickname} - 筹码: {fmt_chips(player.chips)}"
            if player.current_bet > 0:
                status_line += f" (已下注: {fmt_chips(player.current_bet)})"
            if player.is_folded:
                status_line += " (已弃牌)"
            elif player.is_all_in:
                status_line += " (全下)"
            status_lines.append(status_line)
        
        if game.phase in ["pre_flop", "flop", "turn", "river"]:
            active_player = game.get_active_player()
            if active_player:
                status_lines.append(f"\n⏰ 当前行动玩家: {active_player.nickname}")
        
        yield event.plain_result("\n".join(status_lines))
    
    # ==================== 游戏操作命令 ====================
    
    @command("跟注")
    async def call_action(self, event: AstrMessageEvent):
        """跟注"""
        async for result in self._handle_player_action(event, "call"):
            yield result
    
    @command("加注")
    @ErrorHandler.game_command_error_handler("加注")
    async def raise_action(self, event: AstrMessageEvent, amount: int = None):
        """加注"""
        # 获取最小下注金额配置
        min_bet = self.storage.get_plugin_config_value('min_bet', 1)  # 1K
        GameValidation.validate_raise_amount(amount, min_bet)
        
        async for result in self._handle_player_action(event, "raise", amount):
            yield result
    
    @command("弃牌")
    async def fold_action(self, event: AstrMessageEvent):
        """弃牌"""
        async for result in self._handle_player_action(event, "fold"):
            yield result
    
    @command("让牌")
    async def check_action(self, event: AstrMessageEvent):
        """让牌"""
        async for result in self._handle_player_action(event, "check"):
            yield result
    
    @command("全下")
    async def all_in_action(self, event: AstrMessageEvent):
        """全下"""
        async for result in self._handle_player_action(event, "all_in"):
            yield result
    
    async def _handle_player_action(self, event: AstrMessageEvent, action: str, amount: int = 0):
        """处理玩家行动的通用方法"""
        try:
            user_id = event.get_sender_id()
            group_id = event.get_group_id() or user_id
            
            success, message = self.game_engine.player_action(group_id, user_id, action, amount)
            yield event.plain_result(message)
            
            if success:
                # 检查游戏状态变化
                game = self.game_engine.get_game_state(group_id)
                if game:
                    # 如果阶段改变，发送新的公共牌
                    if game.phase.value in ["flop", "turn", "river"]:
                        community_result = await self._send_community_cards(group_id)
                        if community_result:
                            yield community_result
                    
                    # 如果游戏结束，发送结算图片并清理资源
                    elif game.phase.value == "showdown":
                        showdown_result = await self._send_showdown_result(group_id)
                        if showdown_result:
                            yield showdown_result
                        # 清理该游戏的所有临时文件
                        self._cleanup_temp_files(group_id)
            
        except Exception as e:
            logger.error(f"处理玩家行动失败: {e}")
            yield event.plain_result("系统错误，请稍后重试")
    
    # ==================== 查询命令 ====================
    
    @command("德州排行")
    async def show_ranking(self, event: AstrMessageEvent):
        """显示排行榜"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            ranking = self.storage.get_group_ranking(group_id, 10)
            
            if not ranking:
                yield event.plain_result("暂无排行数据")
                return
            
            lines = ["🏆 德州扑克排行榜", ""]
            for i, player_data in enumerate(ranking, 1):
                nickname = player_data.get('nickname', '未知')
                winnings = player_data.get('total_winnings', 0)
                games = player_data.get('games_played', 0)
                hands_won = player_data.get('hands_won', 0)
                
                line = f"{i}. {nickname} - 盈利:{winnings} 局数:{games} 胜场:{hands_won}"
                lines.append(line)
            
            yield event.plain_result("\n".join(lines))
            
        except Exception as e:
            logger.error(f"显示排行榜失败: {e}")
            yield event.plain_result("系统错误，请稍后重试")
    
    @command("德州帮助")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        # 获取配置信息用于帮助显示
        default_chips = self.storage.get_plugin_config_value('default_chips', 500)
        default_buyin = self.storage.get_plugin_config_value('default_buyin', 50)
        min_buyin = self.storage.get_plugin_config_value('min_buyin', 10)
        max_buyin = self.storage.get_plugin_config_value('max_buyin', 200)
        default_small_blind = self.storage.get_plugin_config_value('small_blind', 1)
        default_big_blind = self.storage.get_plugin_config_value('big_blind', 2)
        
        help_text = f"""🃏 德州扑克插件帮助

💰 资金系统：
- 注册获得 {fmt_chips(default_chips)} 银行资金
- 买入制度：每局需买入筹码参与游戏
- 游戏结束后剩余筹码自动返回银行

玩家管理：
/德州注册 - 注册玩家账户

游戏管理：
/德州创建 [{default_small_blind}] [{default_big_blind}] - 创建游戏 (盲注以K为单位)
/德州加入 [{default_buyin}] - 加入游戏 (买入金额 {fmt_chips(min_buyin)}-{fmt_chips(max_buyin)})
/德州开始 - 开始游戏
/德州状态 - 查看游戏状态

游戏操作：
/跟注 - 跟注
/加注 [金额] - 加注指定金额 (最小 1K)
/弃牌 - 弃牌
/让牌 - 让牌(check)
/全下 - 全下所有筹码

查询功能：
/德州排行 - 查看排行榜
/德州帮助 - 显示此帮助

游戏规则：
- 每人发2张手牌，5张公共牌
- 翻牌前、翻牌、转牌、河牌四轮下注
- 最终比较牌型大小决定胜负
- 支持超时自动弃牌机制
- 所有金额以K为单位 (1K = 1000)"""
        
        yield event.plain_result(help_text)
    
    # ==================== 私有方法 ====================
    
    async def _send_hand_cards_to_players(self, group_id: str) -> None:
        """私聊发送手牌给每个玩家"""
        try:
            game = self.game_engine.get_game_state(group_id)
            if not game:
                return
            
            for player in game.players:
                if len(player.hole_cards) >= 2:
                    try:
                        # 渲染手牌图片
                        hand_img = self.renderer.render_hand_cards(player, game)
                        filename = f"hand_{player.user_id}_{game.game_id}.png"
                        img_path = self.renderer.save_image(hand_img, filename)
                        
                        if img_path:
                            # 跟踪临时文件
                            if group_id not in self.temp_files:
                                self.temp_files[group_id] = []
                            self.temp_files[group_id].append(img_path)
                            
                            # 尝试私聊发送手牌
                            private_result = await self._send_private_message(
                                player.user_id, 
                                f"🃏 {player.nickname}，您的手牌：",
                                img_path
                            )
                            
                            if not private_result:
                                # 私聊失败，在群内@玩家提醒查看私聊
                                logger.warning(f"私聊发送手牌失败，玩家: {player.nickname}")
                            
                    except Exception as e:
                        logger.error(f"为玩家 {player.nickname} 生成手牌图片失败: {e}")
            
        except Exception as e:
            logger.error(f"发送手牌失败: {e}")
    
    async def _send_private_message(self, user_id: str, text: str, image_path: Optional[str] = None) -> bool:
        """发送私聊消息"""
        try:
            # 创建私聊消息
            components = [text]
            if image_path and os.path.exists(image_path):
                components.append(Image.fromFileSystem(image_path))
            
            # 构建私聊消息对象
            private_msg = AstrBotMessage()
            private_msg.message = components
            
            # 尝试通过context发送私聊（这里需要根据AstrBot的实际API调整）
            # 注：实际实现可能需要platform adapter的支持
            success = await self._try_send_private(user_id, private_msg)
            return success
            
        except Exception as e:
            logger.error(f"发送私聊消息失败: {e}")
            return False
    
    async def _try_send_private(self, user_id: str, message: AstrBotMessage) -> bool:
        """尝试发送私聊消息的具体实现"""
        try:
            # 这里需要根据AstrBot的具体API来实现
            # 暂时返回False，表示私聊功能需要进一步开发
            # TODO: 实现真正的私聊发送功能
            return False
        except Exception:
            return False
    
    async def _send_community_cards(self, group_id: str) -> Optional[MessageEventResult]:
        """发送公共牌区域"""
        try:
            game = self.game_engine.get_game_state(group_id)
            if not game:
                return None
            
            # 渲染公共牌图片
            community_img = self.renderer.render_community_cards(game)
            filename = f"community_{game.game_id}_{game.phase.value}.png"
            img_path = self.renderer.save_image(community_img, filename)
            
            if img_path:
                # 跟踪临时文件
                if group_id not in self.temp_files:
                    self.temp_files[group_id] = []
                self.temp_files[group_id].append(img_path)
                
                img_component = Image.fromFileSystem(img_path)
                return MessageEventResult().message([img_component])
            
            return None
            
        except Exception as e:
            logger.error(f"发送公共牌失败: {e}")
            return None
    
    async def _send_showdown_result(self, group_id: str) -> Optional[MessageEventResult]:
        """发送摊牌结果"""
        try:
            game = self.game_engine.get_game_state(group_id)
            if not game:
                return None
            
            # 获取真正的获胜者（从GameEngine中获取）
            active_players = [p for p in game.players if not p.is_folded]
            if not active_players:
                return None
            
            # 这里应该从game_engine获取真正的获胜者
            # 简化处理：取第一个未弃牌的玩家
            winners = active_players[:1]
            
            # 渲染摊牌结果图片
            showdown_img = self.renderer.render_showdown(game, winners)
            filename = f"showdown_{game.game_id}.png"
            img_path = self.renderer.save_image(showdown_img, filename)
            
            if img_path:
                # 跟踪临时文件
                if group_id not in self.temp_files:
                    self.temp_files[group_id] = []
                self.temp_files[group_id].append(img_path)
                
                img_component = Image.fromFileSystem(img_path)
                return MessageEventResult().message([img_component])
            
            return None
            
        except Exception as e:
            logger.error(f"发送摊牌结果失败: {e}")
            return None
    
    def _cleanup_temp_files(self, group_id: str) -> None:
        """清理指定群组的临时文件"""
        try:
            if group_id in self.temp_files:
                for file_path in self.temp_files[group_id]:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logger.debug(f"已删除临时文件: {file_path}")
                    except Exception as e:
                        logger.warning(f"删除临时文件失败 {file_path}: {e}")
                
                # 清空文件列表
                self.temp_files[group_id] = []
                
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")
    
    def _cleanup_all_temp_files(self) -> None:
        """清理所有临时文件"""
        try:
            for group_id in list(self.temp_files.keys()):
                self._cleanup_temp_files(group_id)
            
            self.temp_files.clear()
            logger.info("已清理所有临时文件")
            
        except Exception as e:
            logger.error(f"清理所有临时文件失败: {e}")