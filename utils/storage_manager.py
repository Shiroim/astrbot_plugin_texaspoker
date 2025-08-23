"""统一存储管理器

整合所有存储服务，提供统一的数据访问接口
"""
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from astrbot.api.star import StarTools, Context
from astrbot.api import logger


class StorageManager:
    """统一存储管理器"""
    
    def __init__(self, plugin_name: str = "texaspoker", context: Optional[Context] = None):
        """
        初始化存储管理器
        
        Args:
            plugin_name: 插件名称
            context: AstrBot上下文对象
        """
        self.plugin_name = plugin_name
        self.context = context
        self.data_dir = StarTools.get_data_dir(plugin_name)
        self._ensure_data_structure()
        
        logger.info("统一存储管理器初始化完成")
    
    def _ensure_data_structure(self) -> None:
        """确保数据目录结构存在"""
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
    
    # ==================== 配置管理 ====================
    
    def get_plugin_config_value(self, key: str, default: Any = None) -> Any:
        """
        获取插件配置值
        
        优先从AstrBot的标准配置获取，如果失败则使用本地配置回退
        """
        try:
            # 首先尝试从AstrBot的标准配置获取
            if self.context:
                # 修复: 使用正确的AstrBot配置API
                plugin_metadata = self.context.get_registered_star(self.plugin_name)
                if plugin_metadata and plugin_metadata.config and key in plugin_metadata.config:
                    value = plugin_metadata.config[key]
                    logger.debug(f"从标准配置获取 {key}: {value}")
                    return value
            
            # 回退到本地配置文件
            local_config = self._load_json('config.json')
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
    
    def set_local_config(self, key: str, value: Any) -> bool:
        """设置本地配置值"""
        try:
            config = self._load_json('config.json')
            config[key] = value
            self._save_json('config.json', config)
            return True
        except Exception as e:
            logger.error(f"设置本地配置失败 {key}: {e}")
            return False
    
    def get_all_config(self) -> Dict[str, Any]:
        """获取所有配置"""
        try:
            config = {}
            
            # 加载本地配置
            local_config = self._load_json('config.json')
            config.update(local_config)
            
            # 如果有AstrBot配置，覆盖本地配置
            if self.context:
                try:
                    # 修复: 使用正确的AstrBot配置API
                    plugin_metadata = self.context.get_registered_star(self.plugin_name)
                    if plugin_metadata and plugin_metadata.config:
                        # 合并插件配置
                        for k, v in plugin_metadata.config.items():
                            config[k] = v
                except Exception as e:
                    logger.debug(f"获取标准配置失败: {e}")
            
            return config
            
        except Exception as e:
            logger.error(f"获取所有配置失败: {e}")
            return {}
    
    # ==================== 游戏数据管理 ====================
    
    def get_game(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取游戏数据"""
        games = self._load_json('games.json')
        return games.get(group_id)
    
    def save_game(self, group_id: str, game_data: Dict[str, Any]) -> None:
        """保存游戏数据"""
        games = self._load_json('games.json')
        games[group_id] = game_data
        self._save_json('games.json', games)
    
    def delete_game(self, group_id: str) -> None:
        """删除游戏数据"""
        games = self._load_json('games.json')
        if group_id in games:
            del games[group_id]
            self._save_json('games.json', games)
    
    def get_all_games(self) -> Dict[str, Any]:
        """获取所有游戏数据"""
        return self._load_json('games.json')
    
    def save_game_history(self, game_id: str, history_data: Dict[str, Any]) -> None:
        """保存游戏历史"""
        history = self._load_json('game_history.json')
        history[game_id] = history_data
        self._save_json('game_history.json', history)
    
    def get_recent_games(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近游戏记录"""
        history = self._load_json('game_history.json')
        games = list(history.values())
        # 按结束时间排序
        games.sort(key=lambda x: x.get('ended_at', 0), reverse=True)
        return games[:limit]
    
    def get_group_game_history(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取群组游戏历史"""
        history = self._load_json('game_history.json')
        group_games = []
        for game_data in history.values():
            if game_data.get('group_id') == group_id:
                group_games.append(game_data)
        
        # 按结束时间排序
        group_games.sort(key=lambda x: x.get('ended_at', 0), reverse=True)
        return group_games[:limit]
    
    # ==================== 玩家数据管理 ====================
    
    def get_player(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取玩家数据"""
        players = self._load_json('players.json')
        return players.get(user_id)
    
    def save_player(self, user_id: str, player_data: Dict[str, Any]) -> None:
        """保存玩家数据"""
        players = self._load_json('players.json')
        players[user_id] = player_data
        self._save_json('players.json', players)
    
    def get_player_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取玩家信息（新的统一接口）"""
        return self.get_player(user_id)
    
    def save_player_info(self, user_id: str, player_data: Dict[str, Any]) -> None:
        """保存玩家信息（新的统一接口）"""
        self.save_player(user_id, player_data)
    
    def delete_player_info(self, user_id: str) -> None:
        """删除玩家信息"""
        players = self._load_json('players.json')
        if user_id in players:
            del players[user_id]
            self._save_json('players.json', players)
    
    def get_all_players(self) -> Dict[str, Any]:
        """获取所有玩家数据"""
        return self._load_json('players.json')
    
    def update_player_stats(self, user_id: str, nickname: str, chips_change: int = 0,
                          games_played: int = 0, hands_won: int = 0) -> None:
        """更新玩家统计数据"""
        try:
            players = self._load_json('players.json')
            
            if user_id not in players:
                # 创建新玩家记录
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
            
            player_data['last_played'] = int(time.time())
            
            self._save_json('players.json', players)
            logger.debug(f"玩家统计数据已更新: {nickname}")
            
        except Exception as e:
            logger.error(f"更新玩家统计数据失败 {nickname}: {e}")
            raise
    
    def get_group_ranking(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取群组排行榜"""
        # 这里简化处理，实际应该按群组统计
        players = self._load_json('players.json')
        ranking = list(players.values())
        # 按总盈利排序
        ranking.sort(key=lambda x: x.get('total_winnings', 0), reverse=True)
        return ranking[:limit]
    
    # ==================== 数据迁移管理 ====================
    
    def get_migration_info(self) -> Dict[str, Any]:
        """获取迁移信息"""
        return self._load_json('migration_info.json')
    
    def save_migration_info(self, migration_info: Dict[str, Any]) -> None:
        """保存迁移信息"""
        self._save_json('migration_info.json', migration_info)
    
    def mark_migration_complete(self, migration_type: str) -> None:
        """标记特定类型的迁移已完成"""
        migration_info = self.get_migration_info()
        migration_info[migration_type] = True
        migration_info[f'{migration_type}_date'] = int(time.time())
        self.save_migration_info(migration_info)
    
    def is_migration_completed(self, migration_type: str) -> bool:
        """检查特定类型的迁移是否已完成"""
        migration_info = self.get_migration_info()
        return migration_info.get(migration_type, False)
    
    # ==================== 数据维护 ====================
    
    def cleanup_old_data(self, keep_days: int = None) -> Dict[str, int]:
        """
        清理旧数据
        
        Args:
            keep_days: 保留天数，默认从配置获取
            
        Returns:
            清理统计信息
        """
        if keep_days is None:
            keep_days = self.get_plugin_config_value('auto_cleanup_days', 30)
        
        results = {}
        
        try:
            # 清理游戏历史
            game_cleaned = self._cleanup_old_history(keep_days)
            results['games_cleaned'] = game_cleaned
            
            # 这里可以添加更多清理逻辑
            logger.info(f"数据清理完成: {results}")
            
        except Exception as e:
            logger.error(f"数据清理失败: {e}")
            
        return results
    
    def _cleanup_old_history(self, keep_days: int) -> int:
        """清理旧的游戏历史记录"""
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
    
    def get_storage_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            stats = {}
            
            # 游戏统计
            active_games = self.get_all_games()
            history = self._load_json('game_history.json')
            
            stats.update({
                'active_games_count': len(active_games),
                'total_games_played': len(history),
                'total_groups': len(set(game.get('group_id') for game in history.values() if game.get('group_id'))),
                'recent_activity': len([g for g in history.values() 
                                      if g.get('ended_at', 0) > (int(time.time()) - 7 * 24 * 60 * 60)])
            })
            
            # 玩家统计
            all_players = self.get_all_players()
            stats['total_players'] = len(all_players)
            
            # 配置统计
            config = self.get_all_config()
            stats['config_items'] = len(config)
            
            return stats
            
        except Exception as e:
            logger.error(f"获取存储统计失败: {e}")
            return {}
    
    def backup_all_data(self) -> Optional[Dict[str, Any]]:
        """
        备份所有数据
        
        Returns:
            备份数据字典，失败返回None
        """
        try:
            backup = {
                'version': '1.0',
                'timestamp': int(time.time()),
                'games': self.get_all_games(),
                'game_history': self._load_json('game_history.json'),
                'players': self.get_all_players(),
                'config': self._load_json('config.json'),
            }
            
            logger.info("数据备份完成")
            return backup
            
        except Exception as e:
            logger.error(f"数据备份失败: {e}")
            return None
    
    def restore_from_backup(self, backup_data: Dict[str, Any]) -> bool:
        """
        从备份恢复数据
        
        Args:
            backup_data: 备份数据字典
            
        Returns:
            是否恢复成功
        """
        try:
            # 验证备份格式
            if 'version' not in backup_data or backup_data['version'] != '1.0':
                raise ValueError("不支持的备份格式")
            
            # 恢复游戏数据
            if 'games' in backup_data:
                self._save_json('games.json', backup_data['games'])
            
            if 'game_history' in backup_data:
                self._save_json('game_history.json', backup_data['game_history'])
            
            # 恢复玩家数据
            if 'players' in backup_data:
                self._save_json('players.json', backup_data['players'])
            
            # 恢复配置
            if 'config' in backup_data:
                self._save_json('config.json', backup_data['config'])
            
            logger.info("数据恢复完成")
            return True
            
        except Exception as e:
            logger.error(f"数据恢复失败: {e}")
            return False
    
    def migrate_legacy_data(self) -> bool:
        """
        迁移旧版本数据到新结构
        
        Returns:
            是否迁移成功
        """
        try:
            # 这里可以实现数据结构升级逻辑
            # 比如从旧的单一JSON文件迁移到分离的服务结构
            
            logger.info("数据迁移检查完成")
            return True
            
        except Exception as e:
            logger.error(f"数据迁移失败: {e}")
            return False


# 保持向后兼容的别名
TexasPokerStorage = StorageManager
