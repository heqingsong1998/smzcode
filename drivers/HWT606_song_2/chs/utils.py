"""
JY901S 工具函数
"""
import time
import platform

def get_default_port() -> str:
    """获取默认串口名称"""
    if platform.system().lower() == 'linux':
        return "/dev/ttyUSB0"
    else:
        return "COM22"

def acceleration_calibration(device, sleep_time: float = 0.1):
    """
    执行加速度计校准
    
    Args:
        device: 设备对象
        sleep_time: 校准后等待时间
    """
    device.AccelerationCalibration()
    time.sleep(sleep_time)
    print("[INFO] 加速度计校准完成")

def field_calibration(device):
    """
    执行磁场校准
    
    Args:
        device: 设备对象
    """
    device.BeginFiledCalibration()
    user_input = input("请分别绕XYZ轴慢速转动一圈，完成后输入 Y 结束校准: ").lower()
    
    if user_input == "y":
        device.EndFiledCalibration()
        print("[INFO] 磁场校准完成")
    else:
        print("[INFO] 磁场校准取消")

def angle_zero_calibration(device) -> dict:
    """
    角度清零校准 - 记录当前角度作为基准值
    
    Args:
        device: 设备对象
    
    Returns:
        包含基准角度值的字典 {'roll': x, 'pitch': y, 'yaw': z}
    """
    # 读取当前角度值
    angle_x = device.getDeviceData("angleX")
    angle_y = device.getDeviceData("angleY")
    angle_z = device.getDeviceData("angleZ")
    
    baseline = {
        'roll': angle_x if angle_x is not None else 0.0,
        'pitch': angle_y if angle_y is not None else 0.0,
        'yaw': angle_z if angle_z is not None else 0.0
    }
    
    print(f"[INFO] 角度清零完成")
    print(f"       基准值 - Roll: {baseline['roll']:.2f}°, "
          f"Pitch: {baseline['pitch']:.2f}°, "
          f"Yaw: {baseline['yaw']:.2f}°")
    
    return baseline

def apply_angle_baseline(angle_x, angle_y, angle_z, baseline: dict) -> tuple:
    """
    应用角度基准值偏移
    
    Args:
        angle_x: 原始Roll角度
        angle_y: 原始Pitch角度
        angle_z: 原始Yaw角度
        baseline: 基准值字典
    
    Returns:
        补偿后的角度值 (roll, pitch, yaw)
    """
    if baseline is None:
        return angle_x, angle_y, angle_z
    
    # 检查角度值是否为None
    if angle_x is None or angle_y is None or angle_z is None:
        print("[WARN] 角度数据为空，返回原始值")
        return angle_x or 0.0, angle_y or 0.0, angle_z or 0.0
    
    # 减去基准值
    roll = angle_x - baseline.get('roll', 0.0)
    pitch = angle_y - baseline.get('pitch', 0.0)
    yaw = angle_z - baseline.get('yaw', 0.0)
    
    # 处理角度跨越±180°的情况
    roll = _normalize_angle(roll)
    pitch = _normalize_angle(pitch)
    yaw = _normalize_angle(yaw)
    
    return roll, pitch, yaw

def _normalize_angle(angle: float) -> float:
    """
    将角度归一化到 [-180, 180] 区间
    
    Args:
        angle: 输入角度
    
    Returns:
        归一化后的角度
    """
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle

def read_device_config(device) -> dict:
    """
    读取设备配置信息
    
    Args:
        device: 设备对象
    
    Returns:
        配置信息字典
    """
    config = {}
    
    # 读取数据内容、回传速率、通讯速率
    vals = device.readReg(0x02, 3)
    if len(vals) > 0:
        config['data_rate'] = vals
        print(f"[CONFIG] 数据速率配置: {vals}")
    
    # 读取安装方向、算法
    vals = device.readReg(0x23, 2)
    if len(vals) > 0:
        config['direction'] = vals
        print(f"[CONFIG] 安装方向配置: {vals}")
    
    return config

def write_device_config(device, rate: int = 11, direction_h_v: int = 0, 
                        direction_axis: int = 0):
    """
    写入设备配置
    
    Args:
        device: 设备对象
        rate: 回传速率 (6=10Hz)
        direction_h_v: 安装方向-水平垂直
        direction_axis: 安装方向-九轴六轴
    """
    device.unlock()
    time.sleep(0.1)
    
    device.writeReg(0x03, rate)
    time.sleep(0.1)
    
    device.writeReg(0x23, direction_h_v)
    time.sleep(0.1)
    
    device.writeReg(0x24, direction_axis)
    time.sleep(0.1)
    
    device.save()
    print("[INFO] 配置已保存")