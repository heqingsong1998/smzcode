"""
JY901S 设备主类
"""

from .lib import device_model as deviceModel
from .lib.data_processor.roles.jy901s_dataProcessor import JY901SDataProcessor
from .lib.protocol_resolver.roles.wit_protocol_resolver import WitProtocolResolver

# 修改为绝对导入
from .base import JY901SBase
from .utils import (
    get_default_port, 
    read_device_config, 
    write_device_config,
    angle_zero_calibration,
    apply_angle_baseline
)
from .data_recorder import DataRecorder




class JY901SDevice(JY901SBase):
    """JY901S 传感器设备类"""
    
    def __init__(self, name: str = "JY901S", port: str = None, baud: int = 921600):
        if port is None:
            port = get_default_port()
        
        super().__init__(name, port, baud)
        
        # 初始化设备模型
        self.device = deviceModel.DeviceModel(
            name,
            WitProtocolResolver(),
            JY901SDataProcessor(),
            "51_0"
        )
        
        # 配置串口
        self.device.serialConfig.portName = port
        self.device.serialConfig.baud = baud
        
        # 数据记录器
        self.recorder = DataRecorder()

        # 角度基准值（用于角度清零）
        self.angle_baseline = None
        
        # 注册数据更新回调
        self.device.dataProcessor.onVarChanged.append(self._on_data_update)
    
    def open(self):
        """打开设备"""
        self.device.openDevice()
        self._is_open = True  # 设置状态
        print(f"[INFO] 设备 {self.name} 已打开 (端口: {self.port}, 波特率: {self.baud})")
    
    def close(self):
        """关闭设备"""
        self.device.closeDevice()
        self.recorder.stop()
        self._is_open = False  # 设置状态
        print(f"[INFO] 设备 {self.name} 已关闭")
    
    def read_config(self) -> dict:
        """读取配置"""
        return read_device_config(self.device)
    
    def write_config(self, **kwargs):
        """写入配置"""
        write_device_config(self.device, **kwargs)
    
    def start_recording(self, filename: str = None):
        """开始记录数据"""
        self.recorder.start(filename)
    
    def stop_recording(self):
        """停止记录数据"""
        self.recorder.stop()
    
    def _on_data_update(self, device_model):
        """数据更新回调"""
        # 打印数据
        self._print_data(device_model)
        
        # 记录数据
        if self.recorder.is_recording:
            self.recorder.write(device_model)
        
        # 通知外部回调
        self._notify_callbacks(device_model)
    
    def angle_zero(self):
        """
        角度清零 - 将当前角度设为零点基准
        
        Returns:
            bool: 是否成功清零
        """
        # 检查设备是否已打开
        if not self._is_open:
            print("[ERROR] 设备未打开，无法执行角度清零")
            return False
        
        # 等待一下确保有数据
        import time
        time.sleep(0.1)
        
        # 检查数据是否有效
        angle_x = self.device.getDeviceData("angleX")
        angle_y = self.device.getDeviceData("angleY")
        angle_z = self.device.getDeviceData("angleZ")
        
        if angle_x is None or angle_y is None or angle_z is None:
            print("[ERROR] 无法读取角度数据，请确保设备正在发送数据")
            print("[INFO] 提示：设备可能需要更多时间初始化，请稍后再试")
            return False
        
        self.angle_baseline = angle_zero_calibration(self.device)
        return True
    
    def reset_angle_baseline(self):
        """
        重置角度基准值（取消角度清零）
        """
        self.angle_baseline = None
        print("[INFO] 角度基准值已重置")
    
    def get_calibrated_angles(self) -> tuple:
        """
        获取经过清零校准的角度值
        
        Returns:
            (roll, pitch, yaw) 元组，如果数据无效返回 (0.0, 0.0, 0.0)
        """
        angle_x = self.device.getDeviceData("angleX")
        angle_y = self.device.getDeviceData("angleY")
        angle_z = self.device.getDeviceData("angleZ")
        
        # 检查数据是否有效
        if angle_x is None or angle_y is None or angle_z is None:
            print("[WARN] 角度数据无效，请确保设备已正确连接并接收数据")
            return 0.0, 0.0, 0.0
        
        if self.angle_baseline is not None:
            return apply_angle_baseline(angle_x, angle_y, angle_z, self.angle_baseline)
        else:
            return angle_x, angle_y, angle_z
    
    def _print_data(self, device_model):
        """打印传感器数据"""
        # 获取原始角度
        angle_x_raw = device_model.getDeviceData('angleX')
        angle_y_raw = device_model.getDeviceData('angleY')
        angle_z_raw = device_model.getDeviceData('angleZ')
        
        # 检查数据有效性
        if angle_x_raw is None or angle_y_raw is None or angle_z_raw is None:
            angle_str = "角度: (数据无效)"
        elif self.angle_baseline is not None:
            # 如果启用了角度清零，显示校准后的值
            angle_x, angle_y, angle_z = apply_angle_baseline(
                angle_x_raw, angle_y_raw, angle_z_raw, self.angle_baseline
            )
            angle_str = f"角度(校准): ({angle_x:.2f}, {angle_y:.2f}, {angle_z:.2f})"
        else:
            angle_str = f"角度: ({angle_x_raw:.2f}, {angle_y_raw:.2f}, {angle_z_raw:.2f})"
        
        # print(
        #     f"芯片时间: {device_model.getDeviceData('Chiptime')} | "
        #     f"温度: {device_model.getDeviceData('temperature')} | "
        #     f"加速度: ({device_model.getDeviceData('accX')}, "
        #     f"{device_model.getDeviceData('accY')}, "
        #     f"{device_model.getDeviceData('accZ')}) | "
        #     f"角速度: ({device_model.getDeviceData('gyroX')}, "
        #     f"{device_model.getDeviceData('gyroY')}, "
        #     f"{device_model.getDeviceData('gyroZ')}) | "
        #     f"{angle_str}"
        # )