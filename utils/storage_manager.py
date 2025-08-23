"""统一存储管理器

整合所有存储服务，提供统一的数据访问接口
"""
import time
from typing import Dict, Any, List, Optional, Tuple
from ..services.game_service import GameStorageService
from .config_service import ConfigService
from .data_storage import DataStorage
from astrbot.api.star import Context
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
        
        # 初始化各个存储服务
        self.config_service = ConfigService(plugin_name, context)
        self.game_service = GameStorageService(plugin_name)
        self.legacy_storage = DataStorage(plugin_name, context)  # 保留兼容性
        
        logger.info("统一存储管理器初始化完成")
    
    # ==================== 配置管理 ====================
    
    def get_plugin_config_value(self, key: str, default: Any = None) -> Any:
        """获取插件配置值"""
        return self.config_service.get_config_value(key, default)
    
    def set_local_config(self, key: str, value: Any) -> bool:
        """设置本地配置值"""
        return self.config_service.set_local_config_value(key, value)
    
    def get_all_config(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self.config_service.get_all_config()
    
    def validate_and_get_config(self) -> Dict[str, Any]:
        """获取验证后的配置"""
        config = self.config_service.get_all_config()
        return self.config_service.validate_config(config)
    
    # ==================== 游戏数据管理 ====================
    
    def get_game(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取游戏数据"""
        return self.game_service.get_game(group_id)
    
    def save_game(self, group_id: str, game_data: Dict[str, Any]) -> None:
        """保存游戏数据"""
        self.game_service.save_game(group_id, game_data)
    
    def delete_game(self, group_id: str) -> None:
        """删除游戏数据"""
        self.game_service.delete_game(group_id)
    
    def get_all_games(self) -> Dict[str, Any]:
        """获取所有游戏数据"""
        return self.game_service.get_all_games()
    
    def save_game_history(self, game_id: str, history_data: Dict[str, Any]) -> None:
        """保存游戏历史"""
        self.game_service.save_game_history(game_id, history_data)
    
    def get_recent_games(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近游戏记录"""
        return self.game_service.get_recent_games(limit)
    
    def get_group_game_history(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取群组游戏历史"""
        return self.game_service.get_group_game_history(group_id, limit)
    
    # ==================== 玩家数据管理 ====================
    
    def get_player(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取玩家数据"""
        return self.legacy_storage.get_player(user_id)
    
    def save_player(self, user_id: str, player_data: Dict[str, Any]) -> None:
        """保存玩家数据"""
        self.legacy_storage.save_player(user_id, player_data)
    
    def update_player_stats(self, user_id: str, nickname: str, chips_change: int = 0,
                          games_played: int = 0, hands_won: int = 0) -> None:
        """更新玩家统计"""
        self.legacy_storage.update_player_stats(
            user_id, nickname, chips_change, games_played, hands_won
        )
    
    def get_group_ranking(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取群组排行榜"""
        return self.legacy_storage.get_group_ranking(group_id, limit)
    
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
            game_cleaned = self.game_service.cleanup_old_history(keep_days)
            results['games_cleaned'] = game_cleaned
            
            # 这里可以添加更多清理逻辑
            logger.info(f"数据清理完成: {results}")
            
        except Exception as e:
            logger.error(f"数据清理失败: {e}")
            
        return results
    
    def get_storage_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            stats = {}
            
            # 游戏统计
            game_stats = self.game_service.get_statistics()
            stats.update(game_stats)
            
            # 玩家统计
            all_players = self.legacy_storage.get_all_players()
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
                'games': self.game_service.get_all_games(),
                'game_history': self.game_service._load_json('game_history.json'),
                'players': self.legacy_storage.get_all_players(),
                'config': self.config_service._load_local_config(),
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
                self.game_service._save_json('games.json', backup_data['games'])
            
            if 'game_history' in backup_data:
                self.game_service._save_json('game_history.json', backup_data['game_history'])
            
            # 恢复玩家数据
            if 'players' in backup_data:
                self.legacy_storage._save_json('players.json', backup_data['players'])
            
            # 恢复配置
            if 'config' in backup_data:
                self.config_service._save_local_config(backup_data['config'])
            
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
