"""数据迁移工具

处理从非隔离用户ID到隔离用户ID的数据迁移。
确保现有用户数据不会丢失，平滑过渡到新的隔离机制。
"""

import time
from typing import Dict, Any, List, Optional, Tuple
from astrbot.api import logger

from .user_isolation import UserIsolation


class DataMigration:
    """
    数据迁移工具类
    
    负责将现有的非隔离用户数据迁移到新的隔离机制下，
    确保现有用户的数据和游戏状态不会丢失。
    """
    
    def __init__(self, storage_manager):
        """
        初始化数据迁移工具
        
        Args:
            storage_manager: 存储管理器实例
        """
        self.storage = storage_manager
        self.migration_log = []
    
    def needs_migration(self) -> bool:
        """
        检查是否需要进行数据迁移
        
        Returns:
            True表示需要迁移，False表示已经迁移过或无需迁移
        """
        try:
            # 检查迁移标记文件
            migration_info = self.storage.get_migration_info()
            if migration_info.get('user_isolation_migrated', False):
                logger.info("用户隔离数据迁移已完成，跳过迁移")
                return False
            
            # 检查是否有旧格式的用户数据
            all_players = self.storage.get_all_players()
            has_legacy_data = any(UserIsolation.is_legacy_user_id(user_id) for user_id in all_players.keys())
            
            if has_legacy_data:
                logger.info("检测到旧格式用户数据，需要进行迁移")
                return True
            else:
                # 标记为已迁移（可能是全新安装）
                self.storage.mark_migration_complete('user_isolation_migrated')
                return False
                
        except Exception as e:
            logger.error(f"检查迁移状态失败: {e}")
            return False
    
    def migrate_user_data(self) -> Dict[str, Any]:
        """
        迁移用户数据到隔离格式
        
        Returns:
            迁移结果统计
        """
        migration_result = {
            'players_migrated': 0,
            'games_affected': 0,
            'errors': [],
            'start_time': time.time()
        }
        
        try:
            logger.info("开始用户数据隔离迁移...")
            
            # 1. 迁移玩家数据
            self._migrate_players(migration_result)
            
            # 2. 迁移活动游戏数据
            self._migrate_active_games(migration_result)
            
            # 3. 迁移统计数据
            self._migrate_statistics(migration_result)
            
            # 4. 标记迁移完成
            migration_info = {
                'user_isolation_migrated': True,
                'migration_date': int(time.time()),
                'migration_result': migration_result
            }
            self.storage.save_migration_info(migration_info)
            
            migration_result['end_time'] = time.time()
            migration_result['duration'] = migration_result['end_time'] - migration_result['start_time']
            
            logger.info(f"用户数据迁移完成: {migration_result}")
            return migration_result
            
        except Exception as e:
            error_msg = f"用户数据迁移失败: {e}"
            logger.error(error_msg)
            migration_result['errors'].append(error_msg)
            return migration_result
    
    def _migrate_players(self, result: Dict[str, Any]):
        """迁移玩家数据"""
        try:
            all_players = self.storage.get_all_players()
            legacy_players = {
                user_id: data for user_id, data in all_players.items() 
                if UserIsolation.is_legacy_user_id(user_id)
            }
            
            for old_user_id, player_data in legacy_players.items():
                try:
                    # 为旧用户创建默认的隔离ID（默认群聊）
                    new_user_id = UserIsolation.create_default_isolated_id(
                        old_user_id, 
                        platform="default", 
                        session="default"
                    )
                    
                    # 添加迁移标记
                    player_data['migrated_from'] = old_user_id
                    player_data['migration_date'] = int(time.time())
                    
                    # 保存到新ID下
                    self.storage.save_player_info(new_user_id, player_data)
                    
                    # 删除旧数据
                    self.storage.delete_player_info(old_user_id)
                    
                    result['players_migrated'] += 1
                    self.migration_log.append(f"迁移玩家: {old_user_id} -> {new_user_id}")
                    
                    logger.debug(f"玩家数据迁移完成: {old_user_id} -> {new_user_id}")
                    
                except Exception as e:
                    error_msg = f"迁移玩家 {old_user_id} 失败: {e}"
                    logger.error(error_msg)
                    result['errors'].append(error_msg)
            
        except Exception as e:
            error_msg = f"迁移玩家数据失败: {e}"
            logger.error(error_msg)
            result['errors'].append(error_msg)
    
    def _migrate_active_games(self, result: Dict[str, Any]):
        """迁移活动游戏中的玩家ID"""
        try:
            all_games = self.storage.get_all_games()
            
            for group_id, game_data in all_games.items():
                try:
                    game_modified = False
                    players = game_data.get('players', [])
                    
                    for player_data in players:
                        old_user_id = player_data.get('user_id')
                        if old_user_id and UserIsolation.is_legacy_user_id(old_user_id):
                            # 更新为新的隔离ID
                            new_user_id = UserIsolation.create_default_isolated_id(old_user_id)
                            player_data['user_id'] = new_user_id
                            game_modified = True
                            
                            self.migration_log.append(f"游戏 {group_id} 中玩家ID更新: {old_user_id} -> {new_user_id}")
                    
                    if game_modified:
                        self.storage.save_game(group_id, game_data)
                        result['games_affected'] += 1
                        logger.debug(f"游戏 {group_id} 的玩家ID已更新")
                        
                except Exception as e:
                    error_msg = f"迁移游戏 {group_id} 失败: {e}"
                    logger.error(error_msg)
                    result['errors'].append(error_msg)
                    
        except Exception as e:
            error_msg = f"迁移活动游戏失败: {e}"
            logger.error(error_msg)
            result['errors'].append(error_msg)
    
    def _migrate_statistics(self, result: Dict[str, Any]):
        """迁移统计数据"""
        try:
            # 如果有全局统计数据需要迁移，在这里处理
            # 目前德州扑克插件的统计数据主要存储在玩家数据中，已在_migrate_players中处理
            logger.debug("统计数据迁移检查完成")
            
        except Exception as e:
            error_msg = f"迁移统计数据失败: {e}"
            logger.error(error_msg)
            result['errors'].append(error_msg)
    
    def rollback_migration(self) -> bool:
        """
        回滚迁移（紧急情况下使用）
        
        Returns:
            True表示回滚成功，False表示回滚失败
        """
        try:
            logger.warning("开始回滚用户数据迁移...")
            
            # 查找所有迁移过的数据
            all_players = self.storage.get_all_players()
            migrated_players = {
                user_id: data for user_id, data in all_players.items()
                if data.get('migrated_from')
            }
            
            rollback_count = 0
            for new_user_id, player_data in migrated_players.items():
                try:
                    old_user_id = player_data.get('migrated_from')
                    if old_user_id:
                        # 清除迁移标记
                        player_data.pop('migrated_from', None)
                        player_data.pop('migration_date', None)
                        
                        # 恢复到旧ID
                        self.storage.save_player_info(old_user_id, player_data)
                        
                        # 删除新ID数据
                        self.storage.delete_player_info(new_user_id)
                        
                        rollback_count += 1
                        logger.debug(f"回滚玩家数据: {new_user_id} -> {old_user_id}")
                        
                except Exception as e:
                    logger.error(f"回滚玩家 {new_user_id} 失败: {e}")
            
            # 清除迁移标记
            migration_info = self.storage.get_migration_info()
            migration_info['user_isolation_migrated'] = False
            self.storage.save_migration_info(migration_info)
            
            logger.warning(f"迁移回滚完成，回滚了 {rollback_count} 个玩家的数据")
            return True
            
        except Exception as e:
            logger.error(f"回滚迁移失败: {e}")
            return False
    
    def get_migration_log(self) -> List[str]:
        """
        获取迁移日志
        
        Returns:
            迁移操作的详细日志列表
        """
        return self.migration_log.copy()
