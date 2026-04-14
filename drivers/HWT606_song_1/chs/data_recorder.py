"""
JY901S 数据记录器
"""
import datetime
from typing import Optional

class DataRecorder:
    """数据记录器类"""
    
    def __init__(self):
        self._file: Optional[object] = None
        self._is_recording = False
    
    @property
    def is_recording(self) -> bool:
        """是否正在记录"""
        return self._is_recording
    
    def start(self, filename: Optional[str] = None):
        """
        开始记录数据
        
        Args:
            filename: 文件名，默认使用时间戳
        """
        if self._is_recording:
            print("[WARN] 已经在记录数据")
            return
        
        if filename is None:
            filename = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        
        self._file = open(filename, "w", encoding="utf-8")
        self._is_recording = True
        
        # 写入表头
        header = (
            "Chiptime\t"
            "ax(g)\tay(g)\taz(g)\t"
            "wx(deg/s)\twy(deg/s)\twz(deg/s)\t"
            "AngleX(deg)\tAngleY(deg)\tAngleZ(deg)\t"
            "T(°)\t"
            "magx\tmagy\tmagz\t"
            "lon\tlat\t"
            "Yaw\tSpeed\t"
            "q1\tq2\tq3\tq4\n"
        )
        self._file.write(header)
        print(f"[INFO] 开始记录数据到文件: {filename}")
    
    def write(self, device_model):
        """
        写入一行数据
        
        Args:
            device_model: 设备模型对象
        """
        if not self._is_recording:
            return
        
        data = [
            str(device_model.getDeviceData("Chiptime")),
            str(device_model.getDeviceData("accX")),
            str(device_model.getDeviceData("accY")),
            str(device_model.getDeviceData("accZ")),
            str(device_model.getDeviceData("gyroX")),
            str(device_model.getDeviceData("gyroY")),
            str(device_model.getDeviceData("gyroZ")),
            str(device_model.getDeviceData("angleX")),
            str(device_model.getDeviceData("angleY")),
            str(device_model.getDeviceData("angleZ")),
            str(device_model.getDeviceData("temperature")),
            str(device_model.getDeviceData("magX")),
            str(device_model.getDeviceData("magY")),
            str(device_model.getDeviceData("magZ")),
            str(device_model.getDeviceData("lon")),
            str(device_model.getDeviceData("lat")),
            str(device_model.getDeviceData("Yaw")),
            str(device_model.getDeviceData("Speed")),
            str(device_model.getDeviceData("q1")),
            str(device_model.getDeviceData("q2")),
            str(device_model.getDeviceData("q3")),
            str(device_model.getDeviceData("q4"))
        ]
        
        self._file.write("\t".join(data) + "\n")
    
    def stop(self):
        """停止记录数据"""
        if not self._is_recording:
            return
        
        self._is_recording = False
        if self._file:
            self._file.close()
            self._file = None
        print("[INFO] 结束记录数据")