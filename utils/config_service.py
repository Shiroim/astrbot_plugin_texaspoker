"""配置管理服务

提供插件配置的统一管理
"""
import json
from typing import Any, Dict, Optional, List, Tuple
from pathlib import Path
from astrbot.api.star import StarTools, Context
from astrbot.api import logger


class ConfigService:
    """配置管理服务"""
    
    def __init__(self, plugin_name: str = "texaspoker", context: Optional[Context] = None):
        """
        初始化配置服务
        
        Args:
            plugin_name: 插件名称
            context: AstrBot上下文对象
        """
        self.plugin_name = plugin_name
        self.context = context
        self.data_dir = StarTools.get_data_dir(plugin_name)
        self._local_config_file = self.data_dir / "config.json"
        self._ensure_config_structure()
    
    def _ensure_config_structure(self) -> None:
        """确保配置文件结构存在"""
        try:
            if not self._local_config_file.exists():
                self._save_local_config({})
            logger.debug(f"配置结构初始化完成: {self._local_config_file}")
        except Exception as e:
            logger.error(f"初始化配置结构失败: {e}")
            raise
    
    def _load_local_config(self) -> Dict[str, Any]:
        """加载本地配置文件"""
        try:
            if self._local_config_file.exists():
                with open(self._local_config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"加载本地配置失败: {e}")
            return {}
    
    def _save_local_config(self, config: Dict[str, Any]) -> None:
        """保存本地配置文件"""
        try:
            with open(self._local_config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存本地配置失败: {e}")
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        优先级：AstrBot标准配置 > 本地配置 > 默认值
        
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
            local_config = self._load_local_config()
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
    
    def set_local_config_value(self, key: str, value: Any) -> bool:
        """
        设置本地配置值
        
        Args:
            key: 配置键名
            value: 配置值
            
        Returns:
            是否设置成功
        """
        try:
            local_config = self._load_local_config()
            local_config[key] = value
            self._save_local_config(local_config)
            logger.info(f"本地配置已更新 {key}: {value}")
            return True
        except Exception as e:
            logger.error(f"设置本地配置失败 {key}: {e}")
            return False
    
    def get_all_config(self) -> Dict[str, Any]:
        """
        获取所有配置
        
        Returns:
            合并后的配置字典
        """
        try:
            # 从默认配置开始
            merged_config = self.get_default_config()
            
            # 合并本地配置
            local_config = self._load_local_config()
            merged_config.update(local_config)
            
            # 合并AstrBot标准配置
            if self.context:
                plugin_config = self.context.get_plugin_config(self.plugin_name)
                if plugin_config:
                    merged_config.update(plugin_config)
            
            return merged_config
        except Exception as e:
            logger.error(f"获取全部配置失败: {e}")
            return self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """
        获取默认配置（所有筹码金额以K为单位存储）
        
        Returns:
            默认配置字典
        """
        return {
            'default_chips': 500,       # 玩家初始筹码 (500K)
            'default_buyin': 50,        # 默认买入金额 (50K)
            'small_blind': 1,           # 默认小盲注 (1K)
            'big_blind': 2,             # 默认大盲注 (2K)
            'min_buyin': 10,            # 最小买入金额 (10K)
            'max_buyin': 200,           # 最大买入金额 (200K)
            'min_bet': 1,               # 最小下注金额 (1K)
            'action_timeout': 30,       # 玩家行动超时时间(秒)
            'min_players': 2,           # 最少玩家数
            'max_players': 9,           # 最多玩家数
            'auto_cleanup_days': 30,    # 自动清理历史记录天数
            'max_temp_files': 100,      # 最大临时文件数
        }
    
    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证和修正配置值
        
        Args:
            config: 要验证的配置
            
        Returns:
            验证后的配置
        """
        validated = config.copy()
        default = self.get_default_config()
        
        # 验证数值范围（筹码相关配置以K为单位）
        validations = {
            'default_chips': (100, 10000),     # 初始筹码 (100K-10000K)
            'default_buyin': (10, 500),        # 默认买入 (10K-500K)
            'small_blind': (1, 100),           # 小盲注 (1K-100K)
            'big_blind': (2, 200),             # 大盲注 (2K-200K)
            'min_buyin': (5, 100),             # 最小买入 (5K-100K)
            'max_buyin': (50, 1000),           # 最大买入 (50K-1000K)
            'min_bet': (1, 10),                # 最小下注 (1K-10K)
            'action_timeout': (5, 300),        # 超时时间
            'min_players': (2, 2),             # 最少玩家数
            'max_players': (3, 9),             # 最多玩家数
            'auto_cleanup_days': (1, 365),     # 清理天数
            'max_temp_files': (10, 1000),      # 最大临时文件数
        }
        
        for key, (min_val, max_val) in validations.items():
            if key in validated:
                value = validated[key]
                if not isinstance(value, int) or value < min_val or value > max_val:
                    logger.warning(f"配置值 {key}={value} 无效，使用默认值 {default[key]}")
                    validated[key] = default[key]
        
        # 验证盲注关系
        if validated.get('big_blind', 0) <= validated.get('small_blind', 0):
            logger.warning("大盲注必须大于小盲注，使用默认值")
            validated['small_blind'] = default['small_blind']
            validated['big_blind'] = default['big_blind']
        
        return validated
    
    def reset_to_default(self) -> bool:
        """
        重置为默认配置
        
        Returns:
            是否重置成功
        """
        try:
            self._save_local_config(self.get_default_config())
            logger.info("配置已重置为默认值")
            return True
        except Exception as e:
            logger.error(f"重置配置失败: {e}")
            return False
    
    def export_config(self) -> str:
        """
        导出配置为JSON字符串
        
        Returns:
            配置JSON字符串
        """
        try:
            config = self.get_all_config()
            return json.dumps(config, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"导出配置失败: {e}")
            return "{}"
    
    def import_config(self, config_json: str) -> bool:
        """
        从JSON字符串导入配置
        
        Args:
            config_json: 配置JSON字符串
            
        Returns:
            是否导入成功
        """
        try:
            config = json.loads(config_json)
            validated_config = self.validate_config(config)
            self._save_local_config(validated_config)
            logger.info("配置导入成功")
            return True
        except Exception as e:
            logger.error(f"导入配置失败: {e}")
            return False
