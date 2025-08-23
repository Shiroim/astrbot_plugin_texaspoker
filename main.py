"""德州扑克AstrBot插件 - 重构版

完整的德州扑克群内多人对战系统，支持：
- 完整德州扑克规则
- 精美图形渲染
- 实时统计数据
- 超时自动弃牌
"""

import asyncio
from typing import AsyncGenerator, Dict, Any
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import command
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 导入重构后的模块
from .controllers.game_controller import GameController
from .services.command_handler import CommandHandler
from .services.player_service import PlayerService
from .services.message_service import UniversalMessageService
from .utils.storage_manager import StorageManager
from .utils.data_migration import DataMigration
from .utils.decorators import command_error_handler
from .utils.user_isolation import UserIsolation
from .utils.error_handler import GameError


@register("astrbot_plugin_texaspoker", "YourName", "德州扑克群内多人对战插件", "1.0.1")
class TexasPokerPlugin(Star):
    """
    德州扑克插件 - 重构版
    
    功能特点：
    - 🃏 完整的德州扑克规则实现
    - 🎨 精美的扑克牌图形渲染
    - 👥 群内多人实时对战
    - 📊 玩家统计数据记录
    - ⏰ 超时自动弃牌机制
    - 🔧 模块化架构设计
    """
    
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化核心服务
        self.storage = StorageManager("texaspoker", context)
        self.player_service = PlayerService(self.storage)
        self.message_service = UniversalMessageService(context)
        self.game_controller = GameController(self.storage, self.player_service)
        self.command_handler = CommandHandler(
            self.storage, 
            self.player_service, 
            self.game_controller
        )
        
        logger.info("德州扑克插件初始化完成")
    
    async def initialize(self):
        """插件初始化"""
        try:
            # 执行数据迁移（如果需要）
            await self._perform_data_migration()
            
            # 初始化游戏控制器
            await self.game_controller.initialize()
            
            # 设置行动提示回调
            self.game_controller.set_action_prompt_callback(self._send_action_prompt_message)
            
            logger.info("德州扑克插件启动完成")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}")
            raise GameError("插件初始化失败", str(e))
    
    async def terminate(self):
        """插件销毁"""
        try:
            # 安全关闭游戏控制器
            await self.game_controller.terminate()
            
            logger.info("德州扑克插件已安全停止")
        except Exception as e:
            logger.error(f"插件停止时出错: {e}")
    
    async def _perform_data_migration(self):
        """执行数据迁移"""
        try:
            migration = DataMigration(self.storage)
            
            if migration.needs_migration():
                logger.info("检测到需要数据迁移，开始执行用户隔离迁移...")
                result = migration.migrate_user_data()
                
                if result['errors']:
                    logger.warning(f"数据迁移完成，但有错误: {result['errors']}")
                else:
                    logger.info(f"数据迁移成功完成，迁移了 {result['players_migrated']} 个玩家")
            else:
                logger.debug("无需数据迁移")
                
        except Exception as e:
            logger.error(f"执行数据迁移失败: {e}")
            # 迁移失败不应该阻止插件启动，只记录错误
    
    # ==================== 游戏管理命令 ====================
    
    @command("德州注册")
    async def register_player(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """注册德州扑克玩家"""
        async for result in self.command_handler.register_player(event):
            yield result
    
    @command("德州创建")
    async def create_game(self, event: AstrMessageEvent, small_blind: int = None, 
                         big_blind: int = None) -> AsyncGenerator[MessageEventResult, None]:
        """创建德州扑克游戏"""
        async for result in self.command_handler.create_game(event, small_blind, big_blind):
            yield result
    
    @command("德州加入")
    async def join_game(self, event: AstrMessageEvent, buyin: int = None) -> AsyncGenerator[MessageEventResult, None]:
        """加入德州扑克游戏"""
        async for result in self.command_handler.join_game(event, buyin):
            yield result
    
    @command("德州开始")
    async def start_game(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """开始德州扑克游戏"""
        async for result in self.command_handler.start_game(event):
            yield result
        
        # 发送手牌给每个玩家
        await self._send_hand_cards_to_players(event)
    
    @command("德州状态")
    async def show_game_status(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示游戏状态"""
        async for result in self.command_handler.show_game_status(event):
            yield result
    
    # ==================== 游戏操作命令 ====================
    
    @command("跟注")
    async def call_action(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """跟注"""
        async for result in self.command_handler.handle_player_action(event, "call"):
            yield result
    
    @command("加注")
    async def raise_action(self, event: AstrMessageEvent, amount: int = None) -> AsyncGenerator[MessageEventResult, None]:
        """加注"""
        if amount is None:
            yield event.plain_result("请指定加注金额，例如：/加注 10")
            return
            
        async for result in self.command_handler.handle_player_action(event, "raise", amount):
            yield result
    
    @command("弃牌")
    async def fold_action(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """弃牌"""
        async for result in self.command_handler.handle_player_action(event, "fold"):
            yield result
    
    @command("让牌")
    async def check_action(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """让牌"""
        async for result in self.command_handler.handle_player_action(event, "check"):
            yield result
    
    @command("全下")
    async def all_in_action(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """全下"""
        async for result in self.command_handler.handle_player_action(event, "all_in"):
            yield result
    
    # ==================== 查询命令 ====================
    
    @command("德州余额")
    async def show_balance(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示玩家银行余额和统计信息"""
        async for result in self.command_handler.show_balance(event):
            yield result
    
    @command("德州排行")
    async def show_ranking(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示排行榜"""
        async for result in self.command_handler.show_ranking(event):
            yield result
    
    @command("德州帮助")
    async def show_help(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示帮助信息"""
        async for result in self.command_handler.show_help(event):
            yield result
    
    # ==================== 私有方法 ====================
    
    async def _send_hand_cards_to_players(self, event: AstrMessageEvent) -> None:
        """发送手牌给每个玩家（通过消息服务）"""
        try:
            group_id = event.get_group_id() or UserIsolation.get_isolated_user_id(event)
            game = self.game_controller.get_game_state(group_id)
            
            if not game or len(game.players) == 0:
                return
            
            # 获取所有玩家的手牌图片
            hand_images = {}
            for player in game.players:
                if len(player.hole_cards) >= 2:
                        # 渲染手牌图片
                    hand_img = self.game_controller.renderer.render_hand_cards(player, game)
                        filename = f"hand_{player.user_id}_{game.game_id}.png"
                    img_path = self.game_controller.renderer.save_image(hand_img, filename)
                        if img_path:
                        hand_images[player.user_id] = img_path
                        # 添加到临时文件跟踪
                        self.game_controller.temp_files.setdefault(group_id, []).append(img_path)
            
            # 批量发送手牌
            players_info = [{'user_id': p.user_id, 'nickname': p.nickname} for p in game.players]
            send_results = await self.message_service.send_hand_cards_to_players(players_info, hand_images)
            
            # 记录发送结果
            success_count = sum(1 for success in send_results.values() if success)
            total_count = len(send_results)
            
            if success_count == total_count:
                logger.info(f"手牌发送完成，成功 {success_count}/{total_count}")
            else:
                logger.warning(f"手牌发送部分失败，成功 {success_count}/{total_count}")
            
        except Exception as e:
            logger.error(f"发送手牌失败: {e}")
    
    async def _send_action_prompt_message(self, group_id: str, message: str) -> None:
        """发送行动提示消息到群聊"""
        try:
            # 通过消息服务发送到群聊
            success = await self.message_service.send_group_text(group_id, message)
            if not success:
                logger.warning(f"发送行动提示消息失败: {group_id}")
                except Exception as e:
            logger.error(f"发送行动提示消息异常: {e}")
    
    async def get_plugin_status(self) -> Dict[str, Any]:
        """获取插件状态（用于监控和调试）"""
        try:
            return {
                'active_games': len(self.game_controller.game_engine.active_games),
                'temp_files': sum(len(files) for files in self.game_controller.temp_files.values()),
                'storage_stats': self.storage.get_storage_statistics(),
                'memory_usage': await self._get_memory_usage()
            }
                except Exception as e:
            logger.error(f"获取插件状态失败: {e}")
            return {'error': str(e)}
    
    async def _get_memory_usage(self) -> Dict[str, Any]:
        """获取内存使用情况"""
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            return {
                'rss_mb': round(memory_info.rss / 1024 / 1024, 2),
                'vms_mb': round(memory_info.vms / 1024 / 1024, 2),
                'percent': round(process.memory_percent(), 2)
            }
        except ImportError:
            return {'error': 'psutil not available'}
        except Exception as e:
            return {'error': str(e)}
