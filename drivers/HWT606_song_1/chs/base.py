"""
JY901S 传感器基础类
"""
import time
from abc import ABC, abstractmethod
from typing import Callable, Optional

class JY901SBase(ABC):
    """JY901S 传感器基础抽象类"""
    
    def __init__(self, name: str, port: str, baud: int = 921600):
        self.name = name
        self.port = port
        self.baud = baud
        self.device = None
        self._is_open = False  # 添加这一行
        self._data_callbacks = []
        
    @abstractmethod
    def open(self):
        """打开设备"""
        pass
    
    @abstractmethod
    def close(self):
        """关闭设备"""
        pass
    
    @abstractmethod
    def read_config(self):
        """读取配置"""
        pass
    
    @abstractmethod
    def write_config(self, **kwargs):
        """写入配置"""
        pass
    
    def register_callback(self, callback: Callable):
        """注册数据更新回调"""
        self._data_callbacks.append(callback)
    
    def _notify_callbacks(self, data):
        """通知所有回调"""
        for callback in self._data_callbacks:
            callback(data)