"""传感器工具函数"""
from __future__ import annotations

from typing import Any, Dict

from .m8128b1 import M8128B1Sensor


def create_sensor(sensor_type: str, config: Dict[str, Any]):
    if sensor_type.lower() in ("m8128b1", "m8128"):
        return M8128B1Sensor(config)
    raise ValueError(f"不支持的传感器类型: {sensor_type}")


def initialize_sensor(sensor, auto_config: bool = True) -> bool:
    print("=== 传感器初始化 ===")
    try:
        if not sensor.connect():
            return False
        if auto_config and not sensor.configure():
            return False
        print("🎉 传感器初始化完成")
        return True
    except Exception as e:
        print(f"❌ 传感器初始化失败: {e}")
        return False
