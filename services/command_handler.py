"""德州扑克命令处理器

专门负责处理所有德州扑克相关的命令
"""
from typing import AsyncGenerator, Dict, Any, Optional
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import command
from astrbot.api import logger

from ..services.game_manager import GameManager
from ..services.player_service import PlayerService
from ..utils.storage_manager import StorageManager
from ..utils.user_isolation import UserIsolation
from ..utils.decorators import command_error_handler
from ..utils.money_formatter import fmt_chips, fmt_balance, fmt_error
from ..utils.error_handler import ValidationError, GameError


class CommandHandler:
    """
    德州扑克命令处理器
    
    职责：
    - 处理所有游戏命令
    - 参数验证和解析
    - 响应消息构建
    - 与游戏控制器协调
    """
    
    def __init__(self, storage: StorageManager, player_service: PlayerService, 
                 game_manager: GameManager):
        self.storage = storage
        self.player_service = player_service
        self.game_manager = game_manager
        
        logger.info("命令处理器初始化完成")
    
    @command_error_handler("玩家注册")
    async def register_player(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """注册德州扑克玩家"""
        user_id = UserIsolation.get_isolated_user_id(event)
        nickname = event.get_sender_name()
        
        # 检查是否已经注册
        existing_player = self.player_service.get_player_info(user_id)
        if existing_player:
            total_chips = existing_player.get('total_chips', 0)
            welcome_msg = self._build_welcome_back_message(nickname, existing_player)
            yield event.plain_result("\n".join(welcome_msg))
            return
        
        # 获取初始筹码配置
        initial_chips = self.storage.get_plugin_config_value('default_chips', 500)
        
        # 注册新玩家
        success, message = self.player_service.register_player(user_id, nickname, initial_chips)
        
        if success:
            success_msg = self._build_registration_success_message(nickname, initial_chips)
            yield event.plain_result("\n".join(success_msg))
        else:
            error_msg = fmt_error(
                "玩家注册失败",
                str(message) if message else "系统错误",
                ["请检查网络连接", "稍后重试", "联系管理员"]
            )
            yield event.plain_result("\n".join(error_msg))
    
    @command_error_handler("游戏创建")
    async def create_game(self, event: AstrMessageEvent, small_blind: int = None, 
                         big_blind: int = None) -> AsyncGenerator[MessageEventResult, None]:
        """创建德州扑克游戏"""
        user_id = UserIsolation.get_isolated_user_id(event)
        nickname = event.get_sender_name()
        group_id = event.get_group_id() or user_id
        
        # 创建游戏
        success, message, game = self.game_manager.create_game(
            group_id, user_id, nickname, small_blind, big_blind
        )
        
        if success and game:
            create_msg = self._build_game_creation_message(game)
            yield event.plain_result("\n".join(create_msg))
        else:
            error_msg = fmt_error(
                "游戏创建失败",
                str(message) if message else "系统错误",
                [
                    "检查玩家是否已注册",
                    "确认盲注设置合理",
                    "稍后重试创建游戏"
                ]
            )
            yield event.plain_result("\n".join(error_msg))
    
    @command_error_handler("加入游戏")
    async def join_game(self, event: AstrMessageEvent, buyin: int = None) -> AsyncGenerator[MessageEventResult, None]:
        """加入德州扑克游戏"""
        user_id = UserIsolation.get_isolated_user_id(event)
        nickname = event.get_sender_name()
        group_id = event.get_group_id() or user_id
        
        # 如果没有指定买入金额，使用默认值
        if buyin is None:
            buyin = self.storage.get_plugin_config_value('default_buyin', 50)
        
        # 验证买入金额范围
        self._validate_buyin_range(buyin)
        
        # 使用买入制度加入游戏
        success, message = self.game_manager.join_game(
            group_id, user_id, nickname, buyin
        )
        
        if success:
            join_msg = self._build_join_success_message(group_id, nickname, buyin)
            yield event.plain_result("\n".join(join_msg))
        else:
            error_msg = fmt_error(
                "加入游戏失败",
                str(message) if message else "系统错误",
                [
                    "确认游戏房间已创建",
                    "检查买入金额是否合适",
                    "确认账户余额充足",
                    "使用 /德州状态 查看游戏状态"
                ]
            )
            yield event.plain_result("\n".join(error_msg))
    
    @command_error_handler("开始游戏")
    async def start_game(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """开始德州扑克游戏"""
        user_id = UserIsolation.get_isolated_user_id(event)
        group_id = event.get_group_id() or user_id
        
        success, message = await self.game_manager.start_game(group_id, user_id)
        
        if success:
            # 发送游戏开始信息
            start_info = self._build_game_start_message(group_id)
            if start_info:
                yield event.plain_result(start_info)
            
            # 发送公共牌图片
            community_image = self.game_manager.generate_community_image(group_id)
            if community_image:
                yield event.image_result(community_image)
        else:
            error_msg = [
                "❌ 游戏开始失败",
                "",
                f"🔍 失败原因: {str(message) if message else '未知错误'}",
                "",
                "💡 可能的解决方案:",
                "• 检查是否有足够的玩家加入",
                "• 确认所有玩家都已准备就绪",
                "• 使用 /德州状态 查看详细状态"
            ]
            yield event.plain_result("\n".join(error_msg))
    
    @command_error_handler("查看游戏状态")
    async def show_game_status(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示游戏状态"""
        group_id = event.get_group_id() or UserIsolation.get_isolated_user_id(event)
        game = self.game_controller.get_game_state(group_id)
        
        if not game:
            no_game_msg = self._build_no_game_message()
            yield event.plain_result("\n".join(no_game_msg))
            return
        
        # 检查游戏是否已结束，如果是则清理
        if game.phase.value == "finished":
            await self.game_manager._cleanup_game_resources(group_id)
            finished_msg = self._build_game_finished_message()
            yield event.plain_result("\n".join(finished_msg))
            return
        
        # 构建详细的状态信息
        status_lines = self._build_detailed_game_status(game)
        yield event.plain_result("\n".join(status_lines))
    
    async def handle_player_action(self, event: AstrMessageEvent, action: str, 
                                  amount: int = 0) -> AsyncGenerator[MessageEventResult, None]:
        """处理玩家行动的通用方法"""
        user_id = UserIsolation.get_isolated_user_id(event)
        group_id = event.get_group_id() or user_id
        
        success, message = await self.game_manager.player_action(
            group_id, user_id, action, amount
        )
        
        if success:
            # 构建行动结果消息
            result_msg = self._build_action_result_message(message, None)
            yield event.plain_result(result_msg)
            
            # 根据游戏阶段有选择地生成图片
            game = self.game_manager.get_game_state(group_id)
            if game:
                # 只在阶段变更或摊牌时生成公共牌图片
                if game.phase.value in ["flop", "turn", "river"]:
                    community_image = self.game_manager.generate_community_image(group_id)
                    if community_image:
                        yield event.image_result(community_image)
                
                # 只在摊牌阶段生成摊牌图片
                if game.phase.value == "showdown":
                    showdown_image = self.game_manager.generate_showdown_image(group_id)
                    if showdown_image:
                        yield event.image_result(showdown_image)
        else:
            error_msg = fmt_error(
                "游戏操作失败",
                str(message) if message else "系统错误",
                [
                    "检查是否轮到您行动",
                    "确认操作参数正确",
                    "使用 /德州状态 查看游戏状态"
                ]
            )
            yield event.plain_result("\n".join(error_msg))
    
    @command_error_handler("查询余额")
    async def show_balance(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示玩家银行余额和统计信息"""
        user_id = UserIsolation.get_isolated_user_id(event)
        nickname = event.get_sender_name()
        
        # 获取玩家信息
        player_info = self.player_service.get_player_info(user_id)
        
        if not player_info:
            error_msg = fmt_error(
                "德州扑克银行账户查询",
                "您还未注册德州扑克账户",
                [
                    "使用 /德州注册 创建账户",
                    "获得丰厚的初始资金",
                    "参与激烈的德州扑克对战"
                ]
            )
            yield event.plain_result("\n".join(error_msg))
            return
        
        balance_msg = fmt_balance(player_info, nickname)
        yield event.plain_result("\n".join(balance_msg))
    
    async def show_ranking(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示排行榜"""
        group_id = event.get_group_id() or UserIsolation.get_isolated_user_id(event)
        ranking = self.storage.get_group_ranking(group_id, 10)
        
        if not ranking:
            ranking_msg = self._build_empty_ranking_message()
            yield event.plain_result("\n".join(ranking_msg))
            return
        
        ranking_msg = self._build_ranking_message(ranking)
        yield event.plain_result("\n".join(ranking_msg))
    
    async def show_help(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示帮助信息"""
        help_msg = self._build_help_message()
        yield event.plain_result("\n".join(help_msg))
    
    def _validate_buyin_range(self, buyin: int) -> None:
        """验证买入金额范围"""
        min_buyin = self.storage.get_plugin_config_value('min_buyin', 10)
        max_buyin = self.storage.get_plugin_config_value('max_buyin', 200)
        
        if buyin < min_buyin:
            raise ValidationError(f"买入金额过少，最少需要 {fmt_chips(min_buyin)}")
        if buyin > max_buyin:
            raise ValidationError(f"买入金额过多，最多允许 {fmt_chips(max_buyin)}")
    
    def _build_welcome_back_message(self, nickname: str, player_info: Dict[str, Any]) -> list:
        """构建欢迎回归消息"""
        total_chips = player_info.get('total_chips', 0)
        chips_text = fmt_chips(total_chips)
        
        return [
            f"🎮 欢迎回来，{nickname}！",
            "",
            "📋 您的账户信息:",
            f"💰 银行余额: {chips_text}",
            f"🎯 游戏局数: {player_info.get('games_played', 0)}局",
            f"🏆 获胜场次: {player_info.get('hands_won', 0)}场",
            "",
            "💡 使用 /德州创建 开始新游戏",
            "💡 使用 /德州帮助 查看完整指令"
        ]
    
    def _build_registration_success_message(self, nickname: str, initial_chips: int) -> list:
        """构建注册成功消息"""
        chips_text = fmt_chips(initial_chips)
        
        return [
            f"🎉 {nickname}，注册成功！",
            "",
            "🎁 新手礼包:",
            f"💰 初始资金: {chips_text}",
            "",
            "🎮 开始游戏:",
            "• 使用 /德州创建 创建游戏房间",
            "• 使用 /德州加入 加入其他玩家的游戏",
            "",
            "📚 更多帮助:",
            "• 使用 /德州帮助 查看完整指令手册",
            "• 使用 /德州状态 查看游戏状态",
            "",
            "🎲 祝您游戏愉快！"
        ]
    
    def _build_game_creation_message(self, game) -> list:
        """构建游戏创建成功消息"""
        max_players = self.storage.get_plugin_config_value('max_players', 9)
        min_players = self.storage.get_plugin_config_value('min_players', 2)
        default_buyin = self.storage.get_plugin_config_value('default_buyin', 50)
        min_buyin = self.storage.get_plugin_config_value('min_buyin', 10)
        max_buyin = self.storage.get_plugin_config_value('max_buyin', 200)
        
        return [
            f"🎮 德州扑克房间创建成功！",
            "",
            f"🆔 房间信息:",
            f"• 游戏ID: {game.game_id}",
            f"• 当前玩家: 1/{max_players}人",
            "",
            f"💰 游戏设置:",
            f"• 小盲注: {fmt_chips(game.small_blind)}",
            f"• 大盲注: {fmt_chips(game.big_blind)}",
            f"• 推荐买入: {fmt_chips(default_buyin)}",
            f"• 买入范围: {fmt_chips(min_buyin)} ~ {fmt_chips(max_buyin)}",
            f"• 最少玩家: {min_players}人开始",
            "",
            f"👥 加入游戏:",
            f"• 使用 /德州加入 {default_buyin} 来加入游戏",
            f"• 或使用 /德州加入 [金额] 自定义买入",
            "",
            f"💡 提示: 使用 /德州状态 查看房间详情"
        ]
    
    def _build_join_success_message(self, group_id: str, nickname: str, buyin: int) -> list:
        """构建加入成功消息"""
        game = self.game_manager.get_game_state(group_id)
        if not game:
            return [f"✅ {nickname} 成功加入游戏！"]
        
        max_players = self.storage.get_plugin_config_value('max_players', 9)
        min_players = self.storage.get_plugin_config_value('min_players', 2)
        current_count = len(game.players)
        
        msg = [
            f"✅ {nickname} 成功加入游戏！",
            "",
            f"💰 买入金额: {fmt_chips(buyin)}",
            f"🆔 游戏ID: {game.game_id}",
            f"👥 当前玩家: {current_count}/{max_players}人",
            ""
        ]
        
        # 游戏状态提示
        if current_count >= min_players:
            msg.extend([
                "🎯 可以开始游戏了！",
                "• 使用 /德州开始 开始游戏",
                "• 使用 /德州状态 查看详细状态"
            ])
        else:
            need_count = min_players - current_count
            msg.extend([
                f"⏳ 还需要 {need_count} 名玩家才能开始",
                f"• 邀请朋友使用 /德州加入 加入游戏",
                f"• 使用 /德州状态 查看详细状态"
            ])
        
        return msg
    
    def _build_game_start_message(self, group_id: str) -> Optional[str]:
        """构建游戏开始消息"""
        game = self.game_manager.get_game_state(group_id)
        if not game:
            return None
        
        message_parts = [
            "🎮 德州扑克游戏开始！",
            "",
            f"🆔 游戏ID: {game.game_id}",
            f"💰 盲注设置:",
            f"  小盲注: {fmt_chips(game.small_blind)}",
            f"  大盲注: {fmt_chips(game.big_blind)}",
            "",
            f"👥 玩家座次 ({len(game.players)}人):"
        ]
        
        # 显示玩家座次和筹码
        for i, player in enumerate(game.players):
            chips_text = fmt_chips(player.chips)
            position_text = ""
            if i == game.dealer_index:
                position_text += " [庄家🎯]"
            
            message_parts.append(f"  {i+1}. {player.nickname} - 筹码: {chips_text}{position_text}")
        
        message_parts.extend([
            "",
            "🃏 每位玩家已收到私聊手牌消息",
            "🎲 祝各位游戏愉快！"
        ])
        
        return "\n".join(message_parts)
    
    def _build_no_game_message(self) -> list:
        """构建无游戏消息"""
        return [
            "📊 游戏状态查询",
            "=" * 25,
            "",
            "❌ 当前没有进行中的游戏",
            "",
            "🎮 开始新游戏:",
            "• 使用 /德州创建 创建游戏房间",
            "• 使用 /德州注册 注册账户(如需要)",
            "• 使用 /德州帮助 查看完整指令"
        ]
    
    def _build_game_finished_message(self) -> list:
        """构建游戏结束消息"""
        return [
            "📊 游戏状态查询",
            "=" * 25,
            "",
            "✅ 上一局游戏已结束",
            "",
            "🎮 开始新游戏:",
            "• 使用 /德州创建 创建新的游戏房间",
            "• 使用 /德州排行 查看战绩排名"
        ]
    
    def _build_detailed_game_status(self, game) -> list:
        """构建详细游戏状态"""
        phase_display = {
            "waiting": "等待玩家",
            "pre_flop": "翻牌前",
            "flop": "翻牌圈",
            "turn": "转牌圈", 
            "river": "河牌圈",
            "showdown": "摊牌中"
        }
        
        status_lines = [
            f"🎮 德州扑克游戏状态",
            "=" * 35,
            "",
            f"🆔 游戏ID: {game.game_id}",
            f"🎯 当前阶段: {phase_display.get(game.phase.value, game.phase.value.upper())}",
            f"💰 当前底池: {fmt_chips(game.pot)}",
            f"📈 当前下注额: {fmt_chips(game.current_bet) if game.current_bet > 0 else '无'}",
            f"🔵 小盲注: {fmt_chips(game.small_blind)} | 🔴 大盲注: {fmt_chips(game.big_blind)}",
            "",
            f"👥 玩家信息 ({len(game.players)}人):"
        ]
        
        # 详细玩家信息
        for i, player in enumerate(game.players):
            status_icons = []
            if i == game.dealer_index:
                status_icons.append("🎯庄")
            if player.is_folded:
                status_icons.append("❌弃牌")
            elif player.is_all_in:
                status_icons.append("🎯全下")
            
            status_text = f" [{' '.join(status_icons)}]" if status_icons else ""
            
            player_line = f"  {i+1}. {player.nickname}{status_text}"
            detail_line = f"      💼 筹码: {fmt_chips(player.chips)}"
            
            if player.current_bet > 0:
                detail_line += f" | 💸 已下注: {fmt_chips(player.current_bet)}"
            
            status_lines.extend([player_line, detail_line, ""])
        
        return status_lines
    
    def _build_action_result_message(self, message: str, result_data: Optional[Dict[str, Any]]) -> str:
        """构建行动结果消息"""
        parts = [str(message)]
        
        if result_data and result_data.get('game_info'):
            game_info = result_data['game_info']
            parts.extend([
                "",
                f"💰 当前底池: {fmt_chips(game_info.get('pot', 0))}",
                f"📈 当前下注额: {fmt_chips(game_info.get('current_bet', 0)) if game_info.get('current_bet', 0) > 0 else '无'}"
            ])
            
            if game_info.get('active_player'):
                parts.extend([
                    "",
                    f"⏰ 轮到 {game_info['active_player']} 行动"
                ])
        
        return "\n".join(parts)
    
    def _build_empty_ranking_message(self) -> list:
        """构建空排行榜消息"""
        return [
            "🏆 德州扑克排行榜",
            "=" * 30,
            "",
            "📊 暂无排行数据",
            "",
            "💡 开始游戏来建立您的战绩：",
            "• 使用 /德州注册 注册账户",
            "• 使用 /德州创建 创建游戏",
            "• 赢得游戏来提升排名！"
        ]
    
    def _build_ranking_message(self, ranking: list) -> list:
        """构建排行榜消息"""
        ranking_msg = [
            "🏆 德州扑克排行榜",
            "=" * 30,
            ""
        ]
        
        medal_icons = ["🥇", "🥈", "🥉"]
        
        for i, player_data in enumerate(ranking, 1):
            nickname = player_data.get('nickname', '未知')
            winnings = player_data.get('total_winnings', 0)
            games = player_data.get('games_played', 0)
            hands_won = player_data.get('hands_won', 0)
            
            win_rate = round((hands_won / games * 100) if games > 0 else 0, 1)
            
            if i <= 3:
                rank_icon = medal_icons[i-1]
            elif i <= 5:
                rank_icon = "🌟"
            else:
                rank_icon = f"{i:2d}."
            
            winnings_text = fmt_chips(winnings) if winnings != 0 else "±0"
            if winnings > 0:
                winnings_display = f"💚 +{winnings_text}"
            elif winnings < 0:
                winnings_display = f"💸 {winnings_text}"
            else:
                winnings_display = f"⚪ {winnings_text}"
            
            player_line = f"{rank_icon} {nickname}"
            stats_line = f"    💰 {winnings_display} | 🎮 {games}局 | 🏆 {hands_won}胜 | 📊 {win_rate}%"
            
            ranking_msg.extend([player_line, stats_line, ""])
        
        ranking_msg.extend([
            "📊 排名说明:",
            "• 💰 总盈利：累计盈亏金额",
            "• 🎮 游戏局数：参与的总游戏数",
            "• 🏆 胜利场次：获胜的手牌数",
            "• 📊 胜率：获胜率百分比",
            "",
            "💡 提示: 定期更新，最多显示前10名"
        ])
        
        return ranking_msg
    
    def _build_help_message(self) -> list:
        """构建帮助消息"""
        default_chips = self.storage.get_plugin_config_value('default_chips', 500)
        default_buyin = self.storage.get_plugin_config_value('default_buyin', 50)
        min_buyin = self.storage.get_plugin_config_value('min_buyin', 10)
        max_buyin = self.storage.get_plugin_config_value('max_buyin', 200)
        
        return [
            "🃏 德州扑克插件 - 完整指令手册",
            "=" * 40,
            "",
            "💰 资金系统说明:",
            f"• 注册获得 {fmt_chips(default_chips)} 银行资金",
            "• 采用买入制：每局需买入筹码参与",
            "• 游戏结束后剩余筹码返回银行账户",
            f"• 所有金额以K为单位 (1K = 1,000)",
            "",
            "👤 玩家管理:",
            "┣ /德州注册",
            "┗   📝 注册德州扑克账户",
            "",
            "🎮 游戏管理:",
            f"┣ /德州创建 [小盲注] [大盲注]",
            f"┃   🏗️  创建游戏房间 (盲注以K为单位)",
            f"┣ /德州加入 [{default_buyin}]",
            f"┃   🚪 加入游戏 (买入 {fmt_chips(min_buyin)}~{fmt_chips(max_buyin)})",
            "┣ /德州开始",
            "┃   🎯 开始游戏",
            "┗ /德州状态",
            "    📊 查看游戏详细状态",
            "",
            "🎲 游戏操作:",
            "┣ /跟注 💸 跟上当前下注额",
            "┣ /加注 [金额] 📈 加注指定金额",
            "┣ /弃牌 🗑️  放弃当前手牌",
            "┣ /让牌 ✋ 不下注继续游戏",
            "┗ /全下 🎯 押上所有筹码",
            "",
            "📊 查询功能:",
            "┣ /德州余额 💰 查看银行余额和游戏统计",
            "┣ /德州排行 🏆 查看玩家排行榜",
            "┗ /德州帮助 ❓ 显示此帮助信息"
        ]
