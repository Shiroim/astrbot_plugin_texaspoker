"""数据存储工具

基于AstrBot的标准数据存储接口，提供德州扑克游戏的数据持久化功能。
支持游戏状态、玩家统计、历史记录等数据的存储和管理。
"""
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from astrbot.api.star import StarTools, Context
from astrbot.api import logger


class DataStorage:
    """
    数据存储管理器
    
    提供德州扑克游戏所需的所有数据存储功能：
    - 游戏状态存储和恢复
    - 玩家统计数据管理
    - 游戏历史记录保存
    - 配置数据访问
    """
    
    def __init__(self, plugin_name: str = "texaspoker", context: Optional[Context] = None):
        """
        初始化数据存储
        
        Args:
            plugin_name: 插件名称
            context: AstrBot上下文对象，用于访问配置
        """
        self.plugin_name = plugin_name
        self.context = context
        self.data_dir = StarTools.get_data_dir(plugin_name)
        self._ensure_data_structure()
    
    def _ensure_data_structure(self) -> None:
        """
        确保数据目录结构存在
        
        创建必要的数据文件和目录结构
        """
        try:
            # 创建必要的数据文件
            files = {
                'games.json': {},           # 游戏数据
                'players.json': {},         # 玩家统计数据
                'game_history.json': {},    # 游戏历史记录
                'config.json': {}           # 本地配置
            }
            
            for filename, default_data in files.items():
                file_path = self.data_dir / filename
                if not file_path.exists():
                    self._save_json(filename, default_data)
            
            logger.debug(f"数据存储结构初始化完成: {self.data_dir}")
            
        except Exception as e:
            logger.error(f"初始化数据存储结构失败: {e}")
            raise
    
    def _get_file_path(self, filename: str) -> Path:
        """获取文件路径"""
        return self.data_dir / filename
    
    def _load_json(self, filename: str) -> Dict[str, Any]:
        """加载JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"加载文件失败 {filename}: {e}")
            return {}
    
    def _save_json(self, filename: str, data: Dict[str, Any]):
        """保存JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存文件失败 {filename}: {e}")
    
    # 游戏数据操作
    def get_game(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取群组的游戏数据"""
        games = self._load_json('games.json')
        return games.get(group_id)
    
    def save_game(self, group_id: str, game_data: Dict[str, Any]):
        """保存游戏数据"""
        games = self._load_json('games.json')
        games[group_id] = game_data
        self._save_json('games.json', games)
    
    def delete_game(self, group_id: str):
        """删除游戏数据"""
        games = self._load_json('games.json')
        if group_id in games:
            del games[group_id]
            self._save_json('games.json', games)
    
    def get_all_games(self) -> Dict[str, Any]:
        """获取所有游戏数据"""
        return self._load_json('games.json')
    
    # 玩家数据操作
    def get_player(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取玩家数据"""
        players = self._load_json('players.json')
        return players.get(user_id)
    
    def save_player(self, user_id: str, player_data: Dict[str, Any]):
        """保存玩家数据"""
        players = self._load_json('players.json')
        players[user_id] = player_data
        self._save_json('players.json', players)
    
    def get_all_players(self) -> Dict[str, Any]:
        """获取所有玩家数据"""
        return self._load_json('players.json')
    
    def delete_player(self, user_id: str):
        """删除玩家数据"""
        players = self._load_json('players.json')
        if user_id in players:
            del players[user_id]
            self._save_json('players.json', players)
    
    def update_player_stats(self, user_id: str, nickname: str, chips_change: int = 0, 
                          games_played: int = 0, hands_won: int = 0) -> None:
        """
        更新玩家统计数据
        
        Args:
            user_id: 用户ID
            nickname: 用户昵称
            chips_change: 筹码变化
            games_played: 增加的游戏局数
            hands_won: 增加的获胜手数
        """
        try:
            players = self._load_json('players.json')
            
            if user_id not in players:
                # 创建新玩家记录
                import time
                players[user_id] = {
                    'user_id': user_id,
                    'nickname': nickname,
                    'total_chips': 0,
                    'total_winnings': 0,
                    'games_played': 0,
                    'hands_won': 0,
                    'created_at': int(time.time())
                }
            
            player_data = players[user_id]
            player_data['nickname'] = nickname  # 更新昵称
            player_data['total_chips'] += chips_change
            player_data['total_winnings'] += chips_change
            player_data['games_played'] += games_played
            player_data['hands_won'] += hands_won
            
            import time
            player_data['last_played'] = int(time.time())
            
            self._save_json('players.json', players)
            logger.debug(f"玩家统计数据已更新: {nickname}")
            
        except Exception as e:
            logger.error(f"更新玩家统计数据失败 {nickname}: {e}")
            raise
    
    # 游戏历史记录操作
    def save_game_history(self, game_id: str, history_data: Dict[str, Any]):
        """保存游戏历史记录"""
        history = self._load_json('game_history.json')
        history[game_id] = history_data
        self._save_json('game_history.json', history)
    
    def get_game_history(self, game_id: str) -> Optional[Dict[str, Any]]:
        """获取游戏历史记录"""
        history = self._load_json('game_history.json')
        return history.get(game_id)
    
    def get_recent_games(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的游戏记录"""
        history = self._load_json('game_history.json')
        games = list(history.values())
        # 按时间排序
        games.sort(key=lambda x: x.get('ended_at', 0), reverse=True)
        return games[:limit]
    
    # 排行榜功能
    def get_group_ranking(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取群组排行榜"""
        # 这里简化处理，实际应该按群组统计
        players = self._load_json('players.json')
        ranking = list(players.values())
        # 按总盈利排序
        ranking.sort(key=lambda x: x.get('total_winnings', 0), reverse=True)
        return ranking[:limit]
    
    # 配置操作
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return self._load_json('config.json')
    
    def save_config(self, config: Dict[str, Any]):
        """保存配置"""
        self._save_json('config.json', config)
    
    def get_plugin_config_value(self, key: str, default=None) -> Any:
        """
        获取插件配置值
        
        优先从AstrBot的标准配置获取，如果失败则使用本地配置回退
        
        Args:
            key: 配置键名
            default: 默认值
            
        Returns:
            配置值
        """
        try:
            # 首先尝试从AstrBot的标准配置获取
            if self.context:
                plugin_config = self.context.get_plugin_config(self.plugin_name)
                if plugin_config and key in plugin_config:
                    value = plugin_config[key]
                    logger.debug(f"从标准配置获取 {key}: {value}")
                    return value
            
            # 回退到本地配置文件
            local_config = self.get_config()
            if key in local_config:
                value = local_config[key]
                logger.debug(f"从本地配置获取 {key}: {value}")
                return value
            
            # 返回默认值
            logger.debug(f"使用默认配置值 {key}: {default}")
            return default
            
        except Exception as e:
            logger.warning(f"获取配置值失败 {key}: {e}")
            return default
