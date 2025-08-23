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


# 便捷别名
fmt_chips = MoneyFormatter.format_chips
fmt_pot = MoneyFormatter.format_pot
fmt_player = MoneyFormatter.format_player_chips
fmt_bet = MoneyFormatter.format_bet_action
