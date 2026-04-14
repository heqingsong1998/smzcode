"""
粘附脚传感器基础类

当前协议仅保留样式0数据帧 (Style0)。
新版样式0为 24 个 int16 字段：
- 前 16 项保持原语义（含 flag1 / flag2）
- 新增 flag_fz / flag_fx / flag_d / reserved_1..reserved_5
"""
import serial
from abc import ABC, abstractmethod
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class Style0Data:
    """样式0数据结构 (24个字段)"""
    Fx1: int
    Fy1: int
    Fz1_plus: int
    Mx1: int
    My1: int
    JJJ1_1: int
    JJJ1_2: int
    Fx2: int
    Fy2: int
    Fz2_plus: int
    Mx2: int
    My2: int
    flag1: int      # 原 JJJ2_1
    flag2: int      # 原 JJJ2_2
    FZ1_minus: int
    FZ2_minus: int
    flag_fz: int
    flag_fx: int
    flag_d: int
    reserved_1: int
    reserved_2: int
    reserved_3: int
    reserved_4: int
    reserved_5: int


class NianFuJiaoBase(ABC):
    """粘附脚传感器基础抽象类"""
    
    def __init__(self, port: str, baud: int = 115200):
        self.port = port
        self.baud = baud
        self.serial_conn: Optional[serial.Serial] = None
        self._is_open = False
        self._callbacks: list[Callable] = []
    
    @property
    def is_open(self) -> bool:
        """设备是否已打开"""
        return self._is_open
    
    # ========= 串口与初始化 =========
    @abstractmethod
    def open(self):
        """打开设备"""
        raise NotImplementedError
    
    @abstractmethod
    def close(self):
        """关闭设备"""
        raise NotImplementedError
    
    @abstractmethod
    def send_init_frames(self):
        """发送初始化帧"""
        raise NotImplementedError
    
    # ========= 控制指令 =========
    @abstractmethod
    def send_reply(self) -> bool:
        """发送回复指令"""
        raise NotImplementedError
    
    @abstractmethod
    def send_engage(self) -> bool:
        """发送吸合指令"""
        raise NotImplementedError
    
    @abstractmethod
    def send_zero(self) -> bool:
        """发送清零指令"""
        raise NotImplementedError
    
    # ========= 回调管理 =========
    def register_callback(self, callback: Callable):
        """注册数据回调函数，callback(data_type: str, data)"""
        if callback not in self._callbacks:
            self._callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable):
        """注销数据回调函数"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _notify_callbacks(self, data_type: str, data):
        """通知所有回调函数"""
        for callback in list(self._callbacks):
            try:
                callback(data_type, data)
            except Exception as e:
                print(f"[ERROR] 回调函数执行失败: {e}")
