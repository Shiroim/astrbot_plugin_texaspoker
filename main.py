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
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import command
from astrbot.api.star import Context, Star, register
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
            chips_text = fmt_chips(total_chips) if total_chips is not None else "0K"
            
            welcome_msg = [
                f"🎮 欢迎回来，{nickname}！",
                "",
                "📋 您的账户信息:",
                f"💰 银行余额: {chips_text}",
                f"🎯 游戏局数: {existing_player.get('games_played', 0)}局",
                f"🏆 获胜场次: {existing_player.get('hands_won', 0)}场",
                "",
                "💡 使用 /德州创建 开始新游戏",
                "💡 使用 /德州帮助 查看完整指令"
            ]
            yield event.plain_result("\n".join(welcome_msg))
            return
        
        # 获取初始筹码配置 (以K为单位)
        initial_chips = self.storage.get_plugin_config_value('default_chips', 500)  # 500K
        
        # 注册新玩家
        success, message = self.player_service.register_player(user_id, nickname, initial_chips)
        
        if success:
            chips_text = fmt_chips(initial_chips) if initial_chips is not None else "0K"
            
            success_msg = [
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
            yield event.plain_result("\n".join(success_msg))
        else:
            # 确保message是字符串
            message_text = str(message) if message is not None else "❌ 注册失败，请稍后重试"
            yield event.plain_result(message_text)
    
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
            # 获取配置信息
            default_buyin = self.storage.get_plugin_config_value('default_buyin', 50)
            min_buyin = self.storage.get_plugin_config_value('min_buyin', 10)
            max_buyin = self.storage.get_plugin_config_value('max_buyin', 200)
            min_players = self.storage.get_plugin_config_value('min_players', 2)
            max_players = self.storage.get_plugin_config_value('max_players', 9)
            
            # 格式化显示金额
            small_blind_text = fmt_chips(game.small_blind) if game.small_blind is not None else "0K"
            big_blind_text = fmt_chips(game.big_blind) if game.big_blind is not None else "0K"
            buyin_text = fmt_chips(default_buyin) if default_buyin is not None else "0K"
            min_buyin_text = fmt_chips(min_buyin) if min_buyin is not None else "0K"
            max_buyin_text = fmt_chips(max_buyin) if max_buyin is not None else "0K"
            
            create_msg = [
                f"🎮 德州扑克房间创建成功！",
                "",
                f"🆔 房间信息:",
                f"• 游戏ID: {game.game_id}",
                f"• 房主: {nickname}",
                f"• 当前玩家: 1/{max_players}人",
                "",
                f"💰 游戏设置:",
                f"• 小盲注: {small_blind_text}",
                f"• 大盲注: {big_blind_text}",
                f"• 推荐买入: {buyin_text}",
                f"• 买入范围: {min_buyin_text} ~ {max_buyin_text}",
                f"• 最少玩家: {min_players}人开始",
                "",
                f"👥 加入游戏:",
                f"• 使用 /德州加入 {default_buyin} 来加入游戏",
                f"• 或使用 /德州加入 [金额] 自定义买入",
                "",
                f"🎯 开始游戏:",
                f"• 等待 {min_players}人以上加入后",
                f"• 使用 /德州开始 开始游戏",
                "",
                f"💡 提示: 使用 /德州状态 查看房间详情"
            ]
            yield event.plain_result("\n".join(create_msg))
            
            # 初始化该群组的临时文件列表
            if group_id not in self.temp_files:
                self.temp_files[group_id] = []
        else:
            # 确保message是字符串
            message_text = str(message) if message is not None else "❌ 创建失败，请稍后重试"
            yield event.plain_result(message_text)
    
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
            min_text = fmt_chips(min_buyin) if min_buyin is not None else "0K"
            error_msg = [
                "❌ 买入金额不符合要求",
                "",
                f"💰 您的买入: {fmt_chips(buyin)}",
                f"📉 最小买入: {min_text}",
                "",
                "💡 请重新输入正确的买入金额"
            ]
            yield event.plain_result("\n".join(error_msg))
            return
        if buyin > max_buyin:
            max_text = fmt_chips(max_buyin) if max_buyin is not None else "0K"
            error_msg = [
                "❌ 买入金额不符合要求",
                "",
                f"💰 您的买入: {fmt_chips(buyin)}",
                f"📈 最大买入: {max_text}",
                "",
                "💡 请重新输入正确的买入金额"
            ]
            yield event.plain_result("\n".join(error_msg))
            return
        
        # 使用买入制度加入游戏
        success, message = self.game_engine.join_game_with_buyin(group_id, user_id, nickname, buyin)
        
        if success:
            # 获取游戏状态展示更详细的加入信息
            game = self.game_engine.get_game_state(group_id)
            if game:
                max_players = self.storage.get_plugin_config_value('max_players', 9)
                min_players = self.storage.get_plugin_config_value('min_players', 2)
                current_count = len(game.players)
                
                buyin_text = fmt_chips(buyin) if buyin is not None else "0K"
                join_msg = [
                    f"✅ {nickname} 成功加入游戏！",
                    "",
                    f"💰 买入金额: {buyin_text}",
                    f"🆔 游戏ID: {game.game_id}",
                    f"👥 当前玩家: {current_count}/{max_players}人",
                    ""
                ]
                
                # 显示当前玩家列表
                if current_count <= 6:  # 人数不多时显示完整列表
                    join_msg.append("📋 当前玩家:")
                    for i, player in enumerate(game.players, 1):
                        chips_text = fmt_chips(player.chips) if player.chips is not None else "0K"
                        join_msg.append(f"  {i}. {player.nickname} (筹码: {chips_text})")
                    join_msg.append("")
                
                # 游戏状态提示
                if current_count >= min_players:
                    join_msg.extend([
                        "🎯 可以开始游戏了！",
                        "• 使用 /德州开始 开始游戏",
                        "• 使用 /德州状态 查看详细状态"
                    ])
                else:
                    need_count = min_players - current_count
                    join_msg.extend([
                        f"⏳ 还需要 {need_count} 名玩家才能开始",
                        f"• 邀请朋友使用 /德州加入 加入游戏",
                        f"• 使用 /德州状态 查看详细状态"
                    ])
                
                yield event.plain_result("\n".join(join_msg))
            else:
                # 如果无法获取游戏状态，显示简单信息
                message_text = str(message) if message is not None else "加入成功"
                yield event.plain_result(f"✅ {message_text}")
        else:
            # 确保message是字符串
            message_text = str(message) if message is not None else "❌ 加入失败，请稍后重试"
            yield event.plain_result(message_text)
    
    @command("德州开始")
    @ErrorHandler.game_command_error_handler("开始游戏")
    async def start_game(self, event: AstrMessageEvent):
        """开始德州扑克游戏"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id() or user_id
        
        success, message = self.game_engine.start_game(group_id, user_id)
        
        if success:
            # 发送游戏开始的详细信息
            start_info = self._build_game_start_message(group_id)
            if start_info:
                yield event.plain_result(start_info)
            
            # 发送手牌给每个玩家（私聊）
            await self._send_hand_cards_to_players(group_id)
            
            # 发送公共牌区域（群内）
            community_img_path = await self._send_community_cards(group_id)
            if community_img_path:
                yield event.image_result(community_img_path)
        else:
            # 游戏开始失败的详细错误信息
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
    
    @command("德州状态")
    @ErrorHandler.game_command_error_handler("查看游戏状态")
    async def show_game_status(self, event: AstrMessageEvent):
        """显示游戏状态"""
        group_id = event.get_group_id() or event.get_sender_id()
        game = self.game_engine.get_game_state(group_id)
        
        if not game:
            no_game_msg = [
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
            yield event.plain_result("\n".join(no_game_msg))
            return
        
        # 检查游戏是否已结束，如果是则清理
        if game.phase.value == "finished":
            # 清理已结束的游戏
            self.game_engine.cleanup_finished_game(group_id)
            finished_msg = [
                "📊 游戏状态查询",
                "=" * 25,
                "",
                "✅ 上一局游戏已结束",
                "",
                "🎮 开始新游戏:",
                "• 使用 /德州创建 创建新的游戏房间",
                "• 使用 /德州排行 查看战绩排名"
            ]
            yield event.plain_result("\n".join(finished_msg))
            return
        
        # 构建阶段显示文本
        phase_display = {
            "waiting": "等待玩家",
            "pre_flop": "翻牌前",
            "flop": "翻牌圈",
            "turn": "转牌圈", 
            "river": "河牌圈",
            "showdown": "摊牌中"
        }
        
        # 构建详细的状态信息
        current_pot = fmt_chips(game.pot) if game.pot is not None else "0K"
        current_bet = fmt_chips(game.current_bet) if game.current_bet > 0 else "无"
        small_blind_text = fmt_chips(game.small_blind) if game.small_blind is not None else "0K"
        big_blind_text = fmt_chips(game.big_blind) if game.big_blind is not None else "0K"
        
        status_lines = [
            f"🎮 德州扑克游戏状态",
            "=" * 35,
            "",
            f"🆔 游戏ID: {game.game_id}",
            f"🎯 当前阶段: {phase_display.get(game.phase.value, game.phase.value.upper())}",
            f"💰 当前底池: {current_pot}",
            f"📈 当前下注额: {current_bet}",
            f"🔵 小盲注: {small_blind_text} | 🔴 大盲注: {big_blind_text}",
            "",
            f"👥 玩家信息 ({len(game.players)}人):"
        ]
        
        # 详细的玩家信息展示
        for i, player in enumerate(game.players):
            chips_text = fmt_chips(player.chips) if player.chips is not None else "0K"
            
            # 玩家状态图标
            status_icons = []
            if i == game.dealer_index:
                status_icons.append("🎯庄")
            if i == (game.dealer_index + 1) % len(game.players) and len(game.players) > 2:
                status_icons.append("🔵SB")
            elif i == (game.dealer_index + 2) % len(game.players) and len(game.players) > 2:
                status_icons.append("🔴BB")
            elif len(game.players) == 2:
                if i == game.dealer_index:
                    status_icons.append("🔵SB")
                else:
                    status_icons.append("🔴BB")
            
            # 行动状态图标
            if player.is_folded:
                status_icons.append("❌弃牌")
            elif player.is_all_in:
                status_icons.append("🎯全下")
            elif game.phase.value in ["pre_flop", "flop", "turn", "river"] and game.get_active_player() == player:
                status_icons.append("⏰行动中")
            
            status_text = f" [{' '.join(status_icons)}]" if status_icons else ""
            
            # 基础玩家信息
            player_line = f"  {i+1}. {player.nickname}{status_text}"
            detail_line = f"      💼 筹码: {chips_text}"
            
            # 下注信息
            if player.current_bet > 0:
                bet_text = fmt_chips(player.current_bet) if player.current_bet is not None else "0K"
                detail_line += f" | 💸 已下注: {bet_text}"
            
            status_lines.extend([player_line, detail_line, ""])
        
        # 公共牌信息（如果有的话）
        if game.community_cards:
            community_str = " ".join(str(card) for card in game.community_cards)
            status_lines.extend([
                "🎴 公共牌:",
                f"  {community_str}",
                ""
            ])
        
        # 显示当前行动玩家和可用操作
        if game.phase.value in ["pre_flop", "flop", "turn", "river"]:
            active_player = game.get_active_player()
            if active_player:
                call_amount = game.current_bet - active_player.current_bet
                action_timeout = self.storage.get_plugin_config_value('action_timeout', 30)
                
                status_lines.extend([
                    "🎯 当前行动:",
                    f"  ⏰ 轮到 {active_player.nickname} 操作",
                    f"  ⏳ 超时时间: {action_timeout} 秒",
                    ""
                ])
                
                # 显示详细的可用操作
                action_lines = ["💡 可用操作:"]
                
                if call_amount > 0:
                    if call_amount <= active_player.chips:
                        action_lines.append(f"  🔹 /跟注 - 跟注 {fmt_chips(call_amount)}")
                    else:
                        action_lines.append(f"  🔸 筹码不足跟注 {fmt_chips(call_amount)}")
                    action_lines.append("  🔹 /弃牌 - 放弃本轮")
                else:
                    action_lines.append("  🔹 /让牌 - 不下注继续")
                
                if active_player.chips > 0:
                    min_bet = 1
                    action_lines.extend([
                        f"  🔹 /加注 [金额] - 加注(最少{fmt_chips(min_bet)})",
                        f"  🔹 /全下 - 全部押上"
                    ])
                
                status_lines.extend(action_lines)
        
        elif game.phase.value == "waiting":
            min_players = self.storage.get_plugin_config_value('min_players', 2)
            max_players = self.storage.get_plugin_config_value('max_players', 9)
            default_buyin = self.storage.get_plugin_config_value('default_buyin', 50)
            
            status_lines.extend([
                "🎯 游戏准备:",
                ""
            ])
            
            if len(game.players) >= min_players:
                status_lines.extend([
                    "✅ 玩家数量足够，可以开始游戏",
                    "",
                    "🚀 使用指令:",
                    "  🔹 /德州开始 - 开始游戏"
                ])
            else:
                need_players = min_players - len(game.players)
                status_lines.extend([
                    f"⏳ 还需要 {need_players} 名玩家才能开始",
                    f"📊 当前: {len(game.players)}/{max_players} 人",
                    "",
                    "👥 邀请更多玩家:",
                    f"  🔹 /德州加入 {default_buyin} - 使用推荐金额",
                    f"  🔹 /德州加入 [金额] - 自定义买入"
                ])
        
        elif game.phase.value == "showdown":
            status_lines.extend([
                "",
                "🃏 游戏已进入摊牌阶段",
                "🏆 正在计算结果，请稍候..."
            ])
        
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
            
            if success:
                # 获取更新后的游戏状态
                game = self.game_engine.get_game_state(group_id)
                if game:
                    # 构建完整的回复信息，包含下一个操作者提示
                    full_message = self._build_action_result_message(game, message)
                    yield event.plain_result(full_message)
                    
                    # 如果阶段改变，发送新的公共牌
                    if game.phase.value in ["flop", "turn", "river"]:
                        community_img_path = await self._send_community_cards(group_id)
                        if community_img_path:
                            yield event.image_result(community_img_path)
                    
                    # 如果游戏结束，发送详细结算信息和图片
                    elif game.phase.value == "showdown":
                        # 发送详细的文字结算信息
                        settlement_info = self._build_game_end_message(group_id)
                        if settlement_info:
                            yield event.plain_result(settlement_info)
                        
                        # 发送结算图片
                        showdown_img_path = await self._send_showdown_result(group_id)
                        if showdown_img_path:
                            yield event.image_result(showdown_img_path)
                        
                        # 清理该游戏的所有临时文件
                        self._cleanup_temp_files(group_id)
                else:
                    # 确保message是字符串
                    message_text = str(message) if message is not None else "操作完成"
                    yield event.plain_result(message_text)
            else:
                # 确保message是字符串  
                message_text = str(message) if message is not None else "操作失败"
                yield event.plain_result(message_text)
            
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
                ranking_msg = [
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
                yield event.plain_result("\n".join(ranking_msg))
                return
            
            # 构建精美的排行榜
            ranking_msg = [
                "🏆 德州扑克排行榜",
                "=" * 30,
                ""
            ]
            
            # 排名奖杯图标
            medal_icons = ["🥇", "🥈", "🥉"]
            
            for i, player_data in enumerate(ranking, 1):
                nickname = player_data.get('nickname', '未知')
                winnings = player_data.get('total_winnings', 0)
                games = player_data.get('games_played', 0)
                hands_won = player_data.get('hands_won', 0)
                
                # 计算胜率
                win_rate = round((hands_won / games * 100) if games > 0 else 0, 1)
                
                # 获取排名图标
                if i <= 3:
                    rank_icon = medal_icons[i-1]
                elif i <= 5:
                    rank_icon = "🌟"
                else:
                    rank_icon = f"{i:2d}."
                
                # 格式化盈利显示
                winnings_text = fmt_chips(winnings) if winnings != 0 else "±0"
                if winnings > 0:
                    winnings_display = f"💚 +{winnings_text}"
                elif winnings < 0:
                    winnings_display = f"💸 {winnings_text}"
                else:
                    winnings_display = f"⚪ {winnings_text}"
                
                # 构建排名行
                player_line = f"{rank_icon} {nickname}"
                stats_line = f"    💰 {winnings_display} | 🎮 {games}局 | 🏆 {hands_won}胜 | 📊 {win_rate}%"
                
                ranking_msg.extend([player_line, stats_line, ""])
            
            # 添加说明
            ranking_msg.extend([
                "📊 排名说明:",
                "• 💰 总盈利：累计盈亏金额",
                "• 🎮 游戏局数：参与的总游戏数",
                "• 🏆 胜利场次：获胜的手牌数",
                "• 📊 胜率：获胜率百分比",
                "",
                "💡 提示: 定期更新，最多显示前10名"
            ])
            
            yield event.plain_result("\n".join(ranking_msg))
            
        except Exception as e:
            logger.error(f"显示排行榜失败: {e}")
            yield event.plain_result("❌ 系统错误，请稍后重试")
    
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
        min_players = self.storage.get_plugin_config_value('min_players', 2)
        max_players = self.storage.get_plugin_config_value('max_players', 9)
        action_timeout = self.storage.get_plugin_config_value('action_timeout', 30)
        
        help_msg = [
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
            f"┣ /德州创建 [{default_small_blind}] [{default_big_blind}]",
            f"┃   🏗️  创建游戏房间 (盲注以K为单位)",
            f"┣ /德州加入 [{default_buyin}]",
            f"┃   🚪 加入游戏 (买入 {fmt_chips(min_buyin)}~{fmt_chips(max_buyin)})",
            "┣ /德州开始",
            f"┃   🎯 开始游戏 ({min_players}~{max_players}人)",
            "┗ /德州状态",
            "    📊 查看游戏详细状态",
            "",
            "🎲 游戏操作:",
            "┣ /跟注",
            "┃   💸 跟上当前下注额",
            "┣ /加注 [金额]",
            "┃   📈 加注指定金额 (最小1K)",
            "┣ /弃牌",
            "┃   🗑️  放弃当前手牌",
            "┣ /让牌",
            "┃   ✋ 不下注继续游戏(check)",
            "┗ /全下",
            f"    🎯 押上所有筹码 ({action_timeout}秒超时)",
            "",
            "📊 查询功能:",
            "┣ /德州排行",
            "┃   🏆 查看玩家排行榜",
            "┗ /德州帮助",
            "    ❓ 显示此帮助信息",
            "",
            "📖 游戏规则:",
            "🃏 基本流程:",
            "  • 每人发2张手牌(私聊发送)",
            "  • 发5张公共牌(群内图片)",
            "  • 进行4轮下注(翻牌前→翻牌→转牌→河牌)",
            "  • 比较牌型大小决定胜负",
            "",
            "🎯 牌型排序(从大到小):",
            "  🔥 皇家同花顺 > 同花顺 > 四条",
            "  💎 葫芦 > 同花 > 顺子 > 三条",
            "  🎴 两对 > 一对 > 高牌",
            "",
            "⚠️  注意事项:",
            f"• 行动超时 {action_timeout} 秒自动弃牌",
            "• 私聊接收手牌，群内查看公共牌",
            "• 支持精美图片渲染",
            "• 详细的游戏流程提示"
        ]
        
        yield event.plain_result("\n".join(help_msg))
    
    # ==================== 私有方法 ====================
    
    def _build_action_result_message(self, game, original_message: str) -> str:
        """构建包含下一个操作者提示的完整行动结果消息"""
        try:
            message_parts = [str(original_message) if original_message else "操作完成"]
            
            # 构建阶段显示文本
            phase_display = {
                "pre_flop": "翻牌前",
                "flop": "翻牌圈", 
                "turn": "转牌圈",
                "river": "河牌圈",
                "showdown": "摊牌中",
                "finished": "游戏结束"
            }
            
            # 检查是否刚刚进入新阶段
            phase_just_changed = getattr(game, '_phase_just_changed', False)
            if phase_just_changed and game.phase.value in ["flop", "turn", "river"]:
                phase_name = phase_display.get(game.phase.value, game.phase.value)
                
                # 根据不同阶段提供详细说明
                phase_details = {
                    "flop": "🃏 翻牌阶段：3张公共牌已发出",
                    "turn": "🎯 转牌阶段：第4张公共牌已发出",
                    "river": "🔥 河牌阶段：最后1张公共牌已发出，即将进入最终决战！"
                }
                
                phase_info = phase_details.get(game.phase.value, f"🎯 进入 {phase_name} 阶段")
                message_parts.extend([
                    "=" * 30,
                    phase_info,
                    "=" * 30
                ])
            
            # 如果游戏仍在进行，添加下一个操作者信息
            if game.phase.value in ["pre_flop", "flop", "turn", "river"]:
                active_player = game.get_active_player()
                if active_player:
                    call_amount = game.current_bet - active_player.current_bet
                    
                    # 当前游戏状态信息
                    current_pot = fmt_chips(game.pot) if game.pot is not None else "0K"
                    current_bet = fmt_chips(game.current_bet) if game.current_bet > 0 else "无"
                    
                    message_parts.extend([
                        "",
                        f"💰 当前底池: {current_pot}",
                        f"📈 当前下注额: {current_bet}"
                    ])
                    
                    # 下一个玩家信息
                    chips_text = fmt_chips(active_player.chips) if active_player.chips is not None else "0K"
                    message_parts.extend([
                        "",
                        f"⏰ 轮到 {active_player.nickname} 行动",
                        f"💼 剩余筹码: {chips_text}"
                    ])
                    
                    # 显示详细的可用操作
                    action_lines = ["", "💡 可用操作:"]
                    
                    if call_amount > 0:
                        if call_amount <= active_player.chips:
                            action_lines.append(f"  🔹 /跟注 - 跟注 {fmt_chips(call_amount)}")
                        else:
                            action_lines.append(f"  🔸 筹码不足以跟注 {fmt_chips(call_amount)}")
                        action_lines.append("  🔹 /弃牌 - 放弃本轮游戏")
                    else:
                        action_lines.append("  🔹 /让牌 - 不下注继续游戏")
                    
                    if active_player.chips > 0:
                        min_bet = 1  # 最小加注金额
                        action_lines.extend([
                            f"  🔹 /加注 [金额] - 加注(最少{fmt_chips(min_bet)})",
                            f"  🔹 /全下 - 押上全部筹码({chips_text})"
                        ])
                    
                    message_parts.extend(action_lines)
            
            elif game.phase.value == "showdown":
                # 摊牌阶段，显示所有未弃牌玩家
                active_players = [p for p in game.players if not p.is_folded]
                if len(active_players) > 1:
                    player_names = [p.nickname for p in active_players]
                    message_parts.append(f"\n🃏 摊牌对决: {' vs '.join(player_names)}")
                else:
                    message_parts.append(f"\n🏆 {active_players[0].nickname} 获胜！")
            
            elif game.phase.value == "finished":
                message_parts.append("\n🎮 游戏结束，感谢参与！")
            
            return "\n".join(message_parts)
            
        except Exception as e:
            logger.error(f"构建行动结果消息失败: {e}")
            return str(original_message) if original_message else "操作完成"
    
    def _build_game_start_message(self, group_id: str) -> Optional[str]:
        """构建游戏开始时的详细信息"""
        try:
            game = self.game_engine.get_game_state(group_id)
            if not game:
                return None
            
            from .utils.money_formatter import fmt_chips
            
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
                if i == (game.dealer_index + 1) % len(game.players):
                    position_text += " [小盲👤]"
                elif i == (game.dealer_index + 2) % len(game.players):
                    position_text += " [大盲👤]"
                
                message_parts.append(f"  {i+1}. {player.nickname} - 筹码: {chips_text}{position_text}")
            
            message_parts.extend([
                "",
                "🎯 行动顺序:",
                "• 翻牌前：大盲注玩家左侧开始行动"
            ])
            
            # 显示当前行动玩家
            active_player = game.get_active_player()
            if active_player:
                call_amount = game.current_bet - active_player.current_bet
                message_parts.extend([
                    "",
                    f"⏰ 首个行动玩家: {active_player.nickname}",
                    ""
                ])
                
                # 显示可用操作
                available_actions = []
                if call_amount > 0:
                    if call_amount <= active_player.chips:
                        available_actions.append(f"/跟注 ({fmt_chips(call_amount)})")
                    available_actions.append("/弃牌")
                else:
                    available_actions.append("/让牌")
                
                if active_player.chips > 0:
                    min_bet = self.storage.get_plugin_config_value('min_bet', 1)
                    available_actions.append(f"/加注 [金额] (最少{fmt_chips(min_bet)})")
                    available_actions.append("/全下")
                
                if available_actions:
                    message_parts.extend([
                        "💡 可用指令:",
                        "  " + " | ".join(available_actions)
                    ])
            
            message_parts.extend([
                "",
                "🃏 每位玩家已收到私聊手牌消息",
                "🎲 祝各位游戏愉快！"
            ])
            
            return "\n".join(message_parts)
            
        except Exception as e:
            logger.error(f"构建游戏开始消息失败: {e}")
            return "🎮 德州扑克游戏开始！请查看私聊获取手牌信息。"
    
    def _build_game_end_message(self, group_id: str) -> Optional[str]:
        """构建游戏结束时的详细结算信息"""
        try:
            game = self.game_engine.get_game_state(group_id)
            if not game:
                return None
            
            from .utils.money_formatter import fmt_chips
            from .services.hand_evaluator import HandEvaluator
            
            message_parts = [
                f"🏆 游戏 {game.game_id} 结算",
                "=" * 30,
                ""
            ]
            
            # 获取所有未弃牌的玩家和他们的手牌评估
            active_players = [p for p in game.players if not p.is_folded]
            if not active_players:
                return "游戏异常结束"
            
            # 评估手牌并排序
            player_hands = []
            for player in active_players:
                if len(player.hole_cards) >= 2 and len(game.community_cards) >= 3:
                    hand_rank, values = HandEvaluator.evaluate_hand(player.hole_cards, game.community_cards)
                    hand_desc = HandEvaluator.get_hand_description(hand_rank, values)
                    player_hands.append((player, hand_rank, values, hand_desc))
                else:
                    player_hands.append((player, None, [], "未知"))
            
            # 按手牌强度排序
            player_hands.sort(key=lambda x: (x[1].value if x[1] else 0, x[2]), reverse=True)
            
            # 找出获胜者
            if player_hands and player_hands[0][1]:
                best_hand = player_hands[0]
                winners = [best_hand[0]]
                
                # 找出所有并列的获胜者
                for player, rank, values, desc in player_hands[1:]:
                    if rank and HandEvaluator.compare_hands((rank, values), (best_hand[1], best_hand[2])) == 0:
                        winners.append(player)
                    else:
                        break
            else:
                winners = active_players[:1]  # 如果无法评估，默认第一个玩家获胜
            
            # 显示获胜者信息
            if len(winners) == 1:
                winner = winners[0]
                winner_hand = next((h for h in player_hands if h[0] == winner), None)
                pot_share = game.pot
                
                message_parts.extend([
                    f"🏆 获胜者: {winner.nickname}",
                    f"💰 获得奖池: {fmt_chips(pot_share)}",
                    f"🃏 获胜牌型: {winner_hand[3] if winner_hand and winner_hand[3] != '未知' else '未知'}",
                    ""
                ])
            else:
                pot_share = game.pot // len(winners)
                winner_names = [w.nickname for w in winners]
                message_parts.extend([
                    f"🏆 平分获胜者: {' & '.join(winner_names)}",
                    f"💰 每人获得: {fmt_chips(pot_share)}",
                    f"🃏 获胜牌型: {player_hands[0][3] if player_hands[0][3] != '未知' else '未知'}",
                    ""
                ])
            
            # 显示所有参与摊牌的玩家手牌
            if len(active_players) > 1:
                message_parts.extend([
                    "🃏 摊牌结果:",
                    ""
                ])
                
                for i, (player, rank, values, hand_desc) in enumerate(player_hands):
                    is_winner = player in winners
                    status_icon = "🏆" if is_winner else "　"
                    
                    hole_cards_str = " ".join(str(card) for card in player.hole_cards[:2])
                    message_parts.append(
                        f"{status_icon} {i+1}. {player.nickname}: {hole_cards_str} ({hand_desc})"
                    )
                
                message_parts.append("")
            
            # 显示公共牌
            if game.community_cards:
                community_str = " ".join(str(card) for card in game.community_cards)
                message_parts.extend([
                    f"🎴 公共牌: {community_str}",
                    ""
                ])
            
            # 显示最终筹码状况
            message_parts.extend([
                "💼 最终筹码:",
                ""
            ])
            
            # 计算筹码变化（使用记录的初始筹码）
            for player in game.players:
                current_chips = player.chips
                initial_chips = player.initial_chips if hasattr(player, 'initial_chips') and player.initial_chips > 0 else self.storage.get_plugin_config_value('default_buyin', 50)
                
                # 计算盈亏
                change = current_chips - initial_chips
                change_text = ""
                if change > 0:
                    change_text = f" (+{fmt_chips(change)})"
                elif change < 0:
                    change_text = f" ({fmt_chips(change)})"
                else:
                    change_text = " (±0)"
                
                fold_status = " [已弃牌]" if player.is_folded else ""
                message_parts.append(
                    f"　• {player.nickname}: {fmt_chips(current_chips)}{change_text}{fold_status}"
                )
            
            message_parts.extend([
                "",
                f"💰 总奖池: {fmt_chips(game.pot)}",
                "🎮 游戏结束，感谢参与！"
            ])
            
            return "\n".join(message_parts)
            
        except Exception as e:
            logger.error(f"构建游戏结算消息失败: {e}")
            return "🏆 游戏结束！请查看结算图片了解详情。"
    
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
                            
                            # 构建手牌文本内容
                            card_text = f"🃏 {player.nickname}，您的手牌："
                            
                            # 尝试私聊发送手牌图片
                            private_result = await self._send_private_hand_image(
                                player.user_id, 
                                player.nickname,
                                card_text,
                                img_path
                            )
                            
                            if not private_result:
                                # 私聊失败，在群内@玩家提醒查看私聊
                                logger.warning(f"私聊发送手牌失败，玩家: {player.nickname}")
                            
                    except Exception as e:
                        logger.error(f"为玩家 {player.nickname} 生成手牌图片失败: {e}")
            
        except Exception as e:
            logger.error(f"发送手牌失败: {e}")
    
    async def _send_private_message(self, user_id: str, nickname: str, text: str) -> bool:
        """发送私聊消息"""
        try:
            # 获取当前事件的平台信息（需要从其他地方获取，这里暂时模拟）
            # 在实际使用中，需要通过其他方式获取platform信息
            platform_name = "aiocqhttp"  # 假设是QQ平台
            
            # 获取平台适配器
            adapter = None
            for adapter_inst in self.context.platform_manager.get_insts():
                if adapter_inst.meta().name.lower() == platform_name.lower():
                    adapter = adapter_inst
                    break
                    
            if adapter is None:
                logger.error(f"未找到 {platform_name} 平台适配器")
                return False
            
            # 根据平台类型发送私聊消息
            if platform_name == "aiocqhttp":
                # QQ平台私聊发送
                try:
                    user_id_int = int(user_id)  # 确保user_id为整数
                    await adapter.bot.send_private_msg(user_id=user_id_int, message=text)
                    logger.info(f"私聊发送成功，玩家: {nickname}")
                    return True
                except Exception as e:
                    logger.error(f"QQ私聊发送失败（用户可能未添加好友）: {e}")
                    return False
            else:
                # 其他平台（微信等）
                try:
                    await adapter.client.post_text(user_id, text)
                    logger.info(f"私聊发送成功，玩家: {nickname}")
                    return True
                except Exception as e:
                    logger.error(f"私聊发送失败: {e}")
                    return False
                    
        except Exception as e:
            logger.error(f"发送私聊消息失败: {e}")
            return False
    
    async def _send_private_hand_image(self, user_id: str, nickname: str, text: str, img_path: str) -> bool:
        """发送私聊手牌图片"""
        try:
            # 获取当前事件的平台信息
            platform_name = "aiocqhttp"  # 假设是QQ平台
            
            # 获取平台适配器
            adapter = None
            for adapter_inst in self.context.platform_manager.get_insts():
                if adapter_inst.meta().name.lower() == platform_name.lower():
                    adapter = adapter_inst
                    break
                    
            if adapter is None:
                logger.error(f"未找到 {platform_name} 平台适配器")
                return False
            
            # 根据平台类型发送私聊图片
            if platform_name == "aiocqhttp":
                # QQ平台私聊发送图片
                try:
                    user_id_int = int(user_id)
                    # 发送文本 + 图片
                    message = [
                        {"type": "text", "data": {"text": text}},
                        {"type": "image", "data": {"file": f"file:///{img_path}"}}
                    ]
                    await adapter.bot.send_private_msg(user_id=user_id_int, message=message)
                    logger.info(f"私聊手牌图片发送成功，玩家: {nickname}")
                    return True
                except Exception as e:
                    logger.error(f"QQ私聊发送图片失败（用户可能未添加好友）: {e}")
                    return False
            else:
                # 其他平台（微信等）
                try:
                    # 发送文本
                    await adapter.client.post_text(user_id, text)
                    # 发送图片
                    with open(img_path, 'rb') as f:
                        await adapter.client.post_image(user_id, f.read())
                    logger.info(f"私聊手牌图片发送成功，玩家: {nickname}")
                    return True
                except Exception as e:
                    logger.error(f"私聊发送图片失败: {e}")
                    return False
                    
        except Exception as e:
            logger.error(f"发送私聊手牌图片失败: {e}")
            return False
    
    async def _send_community_cards(self, group_id: str):
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
                
                return img_path  # 直接返回图片路径
            
            return None
            
        except Exception as e:
            logger.error(f"发送公共牌失败: {e}")
            return None
    
    async def _send_showdown_result(self, group_id: str):
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
                
                return img_path  # 直接返回图片路径
            
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