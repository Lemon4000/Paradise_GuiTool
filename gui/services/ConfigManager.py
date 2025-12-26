# -*- coding: utf-8 -*-
"""
Configuration Manager
Save and load user configurations, including baud rate list, default baud rate, last used baud rate, etc.
"""
import json
import os
import sys
from typing import List, Optional

# 日志输出控制
ENABLE_LOGGING = True
try:
    # 尝试从 config 模块导入
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _root_dir = os.path.dirname(os.path.dirname(_current_dir))
    sys.path.insert(0, _root_dir)
    from config.config import ENABLE_LOGGING
except (ImportError, ModuleNotFoundError):
    # 如果导入失败，使用默认值
    ENABLE_LOGGING = True


class ConfigManager:
    """Configuration Manager"""
    
    DEFAULT_CONFIG = {
        "baud_rates": [9600, 19200, 38400, 57600, 76800, 115200, 230400, 460800, 921600, 2000000],
        "default_baud_rate": 2000000,
        "last_baud_rate": 2000000,
        "last_hex_path": "",
        "custom_baud_rates": []
    }
    
    def __init__(self, config_path: str = "config/user_config.json"):
        self.config_path = config_path
        self.config = self.DEFAULT_CONFIG.copy()
        self.load()
    
    def load(self):
        """Load configuration file"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    for key in self.DEFAULT_CONFIG:
                        if key in loaded_config:
                            self.config[key] = loaded_config[key]
            except Exception as e:
                if ENABLE_LOGGING:
                    print(f"Failed to load config: {e}")
                self.config = self.DEFAULT_CONFIG.copy()
        else:
            self.save()
    
    def save(self):
        """Save configuration file"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            if ENABLE_LOGGING:
                print(f"Failed to save config: {e}")
    
    def get_baud_rates(self) -> List[int]:
        """Get all baud rates (including custom)"""
        baud_rates = list(self.config["baud_rates"])
        custom_rates = self.config.get("custom_baud_rates", [])
        all_rates = sorted(list(set(baud_rates + custom_rates)))
        return all_rates
    
    def add_custom_baud_rate(self, baud_rate: int) -> bool:
        """Add custom baud rate"""
        if baud_rate < 300 or baud_rate > 3000000:
            return False
        
        all_rates = self.get_baud_rates()
        if baud_rate not in all_rates:
            custom_rates = self.config.get("custom_baud_rates", [])
            custom_rates.append(baud_rate)
            self.config["custom_baud_rates"] = custom_rates
            self.save()
            return True
        return False
    
    def remove_custom_baud_rate(self, baud_rate: int) -> bool:
        """Remove custom baud rate"""
        custom_rates = self.config.get("custom_baud_rates", [])
        if baud_rate in custom_rates:
            custom_rates.remove(baud_rate)
            self.config["custom_baud_rates"] = custom_rates
            self.save()
            return True
        return False
    
    def set_default_baud_rate(self, baud_rate: int):
        """Set default baud rate"""
        self.config["default_baud_rate"] = baud_rate
        self.save()
    
    def get_default_baud_rate(self) -> int:
        """Get default baud rate"""
        return self.config.get("default_baud_rate", 2000000)
    
    def set_last_baud_rate(self, baud_rate: int):
        """Set last used baud rate"""
        self.config["last_baud_rate"] = baud_rate
        self.save()
    
    def get_last_baud_rate(self) -> int:
        """Get last used baud rate"""
        return self.config.get("last_baud_rate", self.get_default_baud_rate())
    
    def set_last_hex_path(self, path: str):
        """Set last used HEX file path"""
        self.config["last_hex_path"] = path
        self.save()
    
    def get_last_hex_path(self) -> str:
        """Get last used HEX file path"""
        return self.config.get("last_hex_path", "")
    
    def is_custom_baud_rate(self, baud_rate: int) -> bool:
        """Check if baud rate is custom"""
        custom_rates = self.config.get("custom_baud_rates", [])
        return baud_rate in custom_rates
