"""游戏管理服务

专门处理游戏数据的存储和管理
"""
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from astrbot.api.star import StarTools
from astrbot.api import logger


class GameStorageService:
    """游戏存储服务"""
    
    def __init__(self, plugin_name: str = "texaspoker"):
        """
        初始化游戏存储服务
        
        Args:
            plugin_name: 插件名称
        """
        self.plugin_name = plugin_name
        self.data_dir = StarTools.get_data_dir(plugin_name)
        self._ensure_game_data_structure()
    
    def _ensure_game_data_structure(self) -> None:
        """确保游戏数据结构存在"""
        try:
            # 创建游戏相关的数据文件
            files = {
                'games.json': {},           # 当前进行中的游戏
                'game_history.json': {},    # 游戏历史记录
            }
            
            for filename, default_data in files.items():
                file_path = self.data_dir / filename
                if not file_path.exists():
                    self._save_json(filename, default_data)
            
            logger.debug(f"游戏存储结构初始化完成: {self.data_dir}")
            
        except Exception as e:
            logger.error(f"初始化游戏存储结构失败: {e}")
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
            logger.error(f"加载游戏文件失败 {filename}: {e}")
            return {}
    
    def _save_json(self, filename: str, data: Dict[str, Any]):
        """保存JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存游戏文件失败 {filename}: {e}")
    
    # 当前游戏数据操作
    def get_game(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取群组的游戏数据"""
        games = self._load_json('games.json')
        return games.get(group_id)
    
    def save_game(self, group_id: str, game_data: Dict[str, Any]):
        """保存游戏数据"""
        games = self._load_json('games.json')
        games[group_id] = game_data
        self._save_json('games.json', games)
        logger.debug(f"游戏数据已保存: {group_id}")
    
    def delete_game(self, group_id: str):
        """删除游戏数据"""
        games = self._load_json('games.json')
        if group_id in games:
            del games[group_id]
            self._save_json('games.json', games)
            logger.debug(f"游戏数据已删除: {group_id}")
    
    def get_all_games(self) -> Dict[str, Any]:
        """获取所有进行中的游戏数据"""
        return self._load_json('games.json')
    
    def get_active_game_count(self) -> int:
        """获取进行中的游戏数量"""
        games = self._load_json('games.json')
        return len(games)
    
    def get_group_game_count(self, group_id: str) -> int:
        """获取特定群组的游戏次数（从历史记录统计）"""
        history = self._load_json('game_history.json')
        count = 0
        for game_data in history.values():
            if game_data.get('group_id') == group_id:
                count += 1
        return count
    
    # 游戏历史记录操作
    def save_game_history(self, game_id: str, history_data: Dict[str, Any]):
        """保存游戏历史记录"""
        history = self._load_json('game_history.json')
        history[game_id] = history_data
        self._save_json('game_history.json', history)
        logger.debug(f"游戏历史已保存: {game_id}")
    
    def get_game_history(self, game_id: str) -> Optional[Dict[str, Any]]:
        """获取游戏历史记录"""
        history = self._load_json('game_history.json')
        return history.get(game_id)
    
    def get_recent_games(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的游戏记录"""
        history = self._load_json('game_history.json')
        games = list(history.values())
        # 按结束时间排序
        games.sort(key=lambda x: x.get('ended_at', 0), reverse=True)
        return games[:limit]
    
    def get_group_game_history(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取特定群组的游戏历史"""
        history = self._load_json('game_history.json')
        group_games = []
        for game_data in history.values():
            if game_data.get('group_id') == group_id:
                group_games.append(game_data)
        
        # 按结束时间排序
        group_games.sort(key=lambda x: x.get('ended_at', 0), reverse=True)
        return group_games[:limit]
    
    def cleanup_old_history(self, keep_days: int = 30) -> int:
        """
        清理旧的游戏历史记录
        
        Args:
            keep_days: 保留天数
            
        Returns:
            清理的记录数量
        """
        import time
        
        current_time = int(time.time())
        cutoff_time = current_time - (keep_days * 24 * 60 * 60)
        
        history = self._load_json('game_history.json')
        to_delete = []
        
        for game_id, game_data in history.items():
            ended_at = game_data.get('ended_at', 0)
            if ended_at < cutoff_time:
                to_delete.append(game_id)
        
        for game_id in to_delete:
            del history[game_id]
        
        if to_delete:
            self._save_json('game_history.json', history)
            logger.info(f"清理了 {len(to_delete)} 条旧游戏记录")
        
        return len(to_delete)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取游戏统计数据"""
        try:
            active_games = self.get_all_games()
            history = self._load_json('game_history.json')
            
            return {
                'active_games_count': len(active_games),
                'total_games_played': len(history),
                'total_groups': len(set(game.get('group_id') for game in history.values() if game.get('group_id'))),
                'recent_activity': len([g for g in history.values() 
                                      if g.get('ended_at', 0) > (int(time.time()) - 7 * 24 * 60 * 60)])
            }
        except Exception as e:
            logger.error(f"获取游戏统计失败: {e}")
            return {}
