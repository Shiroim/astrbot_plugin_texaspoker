"""筹码格式化工具

提供筹码金额的格式化显示功能
注意：所有金额内部以K为单位存储
"""
from typing import Union


class MoneyFormatter:
    """筹码金额格式化器"""
    
    @staticmethod
    def format_chips(amount: Union[int, float]) -> str:
        """
        格式化筹码显示
        
        Args:
            amount: 筹码数量（以K为单位）
            
        Returns:
            格式化后的字符串，如 "500K"、"1.5K"
        """
        if isinstance(amount, float):
            if amount.is_integer():
                return f"{int(amount)}K"
            else:
                return f"{amount:.1f}K"
        else:
            return f"{amount}K"
    
    @staticmethod
    def format_chips_with_label(amount: Union[int, float], label: str) -> str:
        """
        格式化带标签的筹码显示
        
        Args:
            amount: 筹码数量（以K为单位）
            label: 标签，如 "筹码"、"下注"等
            
        Returns:
            格式化后的字符串，如 "筹码: 500K"
        """
        return f"{label}: {MoneyFormatter.format_chips(amount)}"
    
    @staticmethod
    def parse_chips_input(text: str) -> Union[int, None]:
        """
        解析用户输入的筹码数量
        
        Args:
            text: 用户输入，可能包含 "K" 后缀
            
        Returns:
            筹码数量（以K为单位），解析失败返回None
        """
        if not text:
            return None
            
        # 移除空格并转换为小写
        text = text.strip().lower()
        
        # 移除K后缀
        if text.endswith('k'):
            text = text[:-1]
        
        try:
            value = float(text)
            # 只接受正数
            if value > 0:
                return int(value) if value.is_integer() else value
            return None
        except ValueError:
            return None
    
    @staticmethod
    def format_pot(pot_amount: Union[int, float]) -> str:
        """
        格式化底池显示
        
        Args:
            pot_amount: 底池金额（以K为单位）
            
        Returns:
            格式化后的字符串，如 "💰 底池: 150K"
        """
        return f"💰 底池: {MoneyFormatter.format_chips(pot_amount)}"
    
    @staticmethod
    def format_bet_action(player_name: str, action: str, amount: Union[int, float] = 0) -> str:
        """
        格式化下注行动显示
        
        Args:
            player_name: 玩家昵称
            action: 行动类型（跟注、加注等）
            amount: 金额（以K为单位）
            
        Returns:
            格式化后的行动描述
        """
        if amount > 0:
            return f"{player_name} {action} {MoneyFormatter.format_chips(amount)}"
        else:
            return f"{player_name} {action}"
    
    @staticmethod
    def format_player_chips(player_name: str, chips: Union[int, float], 
                          current_bet: Union[int, float] = 0) -> str:
        """
        格式化玩家筹码显示
        
        Args:
            player_name: 玩家昵称
            chips: 剩余筹码（以K为单位）
            current_bet: 当前下注（以K为单位）
            
        Returns:
            格式化后的玩家信息
        """
        result = f"{player_name} - 筹码: {MoneyFormatter.format_chips(chips)}"
        if current_bet > 0:
            result += f" (已下注: {MoneyFormatter.format_chips(current_bet)})"
        return result
    
    @staticmethod
    def format_blind_info(small_blind: Union[int, float], big_blind: Union[int, float]) -> str:
        """
        格式化盲注信息显示
        
        Args:
            small_blind: 小盲注（以K为单位）
            big_blind: 大盲注（以K为单位）
            
        Returns:
            格式化后的盲注信息
        """
        return (f"小盲注: {MoneyFormatter.format_chips(small_blind)}, "
                f"大盲注: {MoneyFormatter.format_chips(big_blind)}")
    
    @staticmethod
    def format_buyin_info(buyin_amount: Union[int, float], 
                         remaining_bank: Union[int, float]) -> str:
        """
        格式化买入信息显示
        
        Args:
            buyin_amount: 买入金额（以K为单位）
            remaining_bank: 剩余银行资金（以K为单位）
            
        Returns:
            格式化后的买入信息
        """
        return (f"💸 买入成功！买入金额: {MoneyFormatter.format_chips(buyin_amount)}, "
                f"银行剩余: {MoneyFormatter.format_chips(remaining_bank)}")
    
    @staticmethod
    def format_winnings_display(winnings: Union[int, float]) -> str:
        """
        格式化盈亏显示（带颜色图标）
        
        Args:
            winnings: 盈亏金额（以K为单位）
            
        Returns:
            格式化后的盈亏显示，包含图标
        """
        winnings_text = MoneyFormatter.format_chips(abs(winnings)) if winnings != 0 else "0K"
        
        if winnings > 0:
            return f"💚 +{winnings_text}"
        elif winnings < 0:
            return f"💸 -{winnings_text}"
        else:
            return f"⚪ ±0K"
    
    @staticmethod
    def format_balance_info(player_info: dict, nickname: str) -> list:
        """
        格式化完整的余额信息（通用方法）
        
        Args:
            player_info: 玩家信息字典
            nickname: 玩家昵称
            
        Returns:
            格式化后的余额信息列表（每行一个字符串）
        """
        import time
        import datetime
        
        # 提取数据
        total_chips = player_info.get('total_chips', 0)
        total_winnings = player_info.get('total_winnings', 0)
        games_played = player_info.get('games_played', 0)
        hands_won = player_info.get('hands_won', 0)
        total_buyin = player_info.get('total_buyin', 0)
        created_at = player_info.get('created_at', 0)
        
        # 计算胜率
        win_rate = round((hands_won / games_played * 100) if games_played > 0 else 0, 1)
        
        # 格式化金额
        balance_text = MoneyFormatter.format_chips(total_chips)
        winnings_display = MoneyFormatter.format_winnings_display(total_winnings)
        buyin_text = MoneyFormatter.format_chips(total_buyin)
        
        # 构建余额信息
        balance_lines = [
            f"💰 {nickname} 的银行账户",
            "=" * 35,
            "",
            "💼 账户余额:",
            f"  🏦 银行存款: {balance_text}",
            f"  📊 累计盈亏: {winnings_display}",
            "",
            "🎯 游戏统计:",
            f"  🎮 参与局数: {games_played} 局",
            f"  🏆 获胜场次: {hands_won} 场",
            f"  📈 胜率: {win_rate}%",
            f"  💰 累计买入: {buyin_text}",
            "",
            "💡 快速操作:",
            "  • /德州创建 - 创建游戏房间",
            "  • /德州状态 - 查看当前游戏",
            "  • /德州排行 - 查看群内排名"
        ]
        
        # 添加账龄信息
        if created_at > 0:
            register_date = datetime.datetime.fromtimestamp(created_at).strftime("%Y-%m-%d")
            days_since_register = (int(time.time()) - created_at) // (24 * 3600)
            balance_lines.extend([
                "",
                "📅 账户信息:",
                f"  📝 注册日期: {register_date}",
                f"  ⏱️  账龄: {days_since_register} 天"
            ])
        
        return balance_lines
    
    @staticmethod
    def format_error_message(title: str, error: str, suggestions: list = None) -> list:
        """
        格式化错误消息（统一格式）
        
        Args:
            title: 错误标题
            error: 错误描述
            suggestions: 建议列表
            
        Returns:
            格式化后的错误消息列表
        """
        error_lines = [
            f"❌ {title}",
            "",
            f"🔍 失败原因: {error}",
            ""
        ]
        
        if suggestions:
            error_lines.extend([
                "💡 可能的解决方案:",
                *[f"• {suggestion}" for suggestion in suggestions]
            ])
        
        return error_lines
    
    @staticmethod
    def format_game_action_result(original_message: str, pot_amount: Union[int, float], 
                                current_bet: Union[int, float], next_player: str = None,
                                available_actions: list = None) -> list:
        """
        格式化游戏行动结果（通用方法）
        
        Args:
            original_message: 原始行动消息
            pot_amount: 底池金额
            current_bet: 当前下注额
            next_player: 下一个行动玩家
            available_actions: 可用行动列表
            
        Returns:
            格式化后的完整行动结果
        """
        result_lines = [str(original_message)]
        
        # 游戏状态信息
        pot_text = MoneyFormatter.format_chips(pot_amount)
        bet_text = MoneyFormatter.format_chips(current_bet) if current_bet > 0 else "无"
        
        result_lines.extend([
            "",
            f"💰 当前底池: {pot_text}",
            f"📈 当前下注额: {bet_text}"
        ])
        
        # 下一个玩家信息
        if next_player:
            result_lines.extend([
                "",
                f"⏰ 轮到 {next_player} 行动"
            ])
            
            if available_actions:
                result_lines.extend([
                    "",
                    "💡 可用操作:",
                    *[f"  🔹 {action}" for action in available_actions]
                ])
        
        return result_lines


# 便捷别名
fmt_chips = MoneyFormatter.format_chips
fmt_pot = MoneyFormatter.format_pot
fmt_player = MoneyFormatter.format_player_chips
fmt_bet = MoneyFormatter.format_bet_action
fmt_winnings = MoneyFormatter.format_winnings_display
fmt_balance = MoneyFormatter.format_balance_info
fmt_error = MoneyFormatter.format_error_message
fmt_action_result = MoneyFormatter.format_game_action_result
