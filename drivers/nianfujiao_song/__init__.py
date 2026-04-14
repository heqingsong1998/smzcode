"""
粘附脚传感器驱动包
"""
from .nianfujiao_device import NianFuJiaoDevice
from .base import Style0Data

__all__ = [
    "NianFuJiaoDevice",
    "Style0Data",
]

# 协议更新：仅保留样式0数据帧，JJJ2_1/2 改为 flag1/flag2
__version__ = "2.0.0"
