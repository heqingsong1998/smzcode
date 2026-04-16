"""
连接管理面板 - 管理四个传感器的连接
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QLabel, QGridLayout)
from PyQt5.QtCore import pyqtSignal, Qt

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from gui.widgets.status_indicator import StatusIndicator


class SensorConnectionWidget(QWidget):
    """单个传感器连接控件"""
    
    connect_clicked = pyqtSignal(str)      # 连接按钮点击 (sensor_id)
    disconnect_clicked = pyqtSignal(str)   # 断开按钮点击 (sensor_id)
    
    def __init__(
        self,
        sensor_id: str,
        name: str,
        endpoint: str,
        baud: int | None,
        protocol: str = "串口",
        parent=None,
    ):
        """
        初始化传感器连接控件
        
        Args:
            sensor_id: 传感器ID
            name: 传感器名称
            endpoint: 连接目标（串口号 或 IP:端口）
            baud: 波特率（非串口可为 None）
            protocol: 通信方式（例如 串口/以太网）
            parent: 父组件
        """
        super().__init__(parent)
        
        self.sensor_id = sensor_id
        self.name = name
        self.endpoint = endpoint
        self.baud = baud
        self.protocol = protocol
        self.is_connected = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 传感器名称
        name_label = QLabel(f"<b>{self.name}</b>")
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)
        
        # 连接信息
        protocol_label = QLabel(f"通信: {self.protocol}")
        protocol_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(protocol_label)

        endpoint_label = QLabel(f"目标: {self.endpoint}")
        endpoint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(endpoint_label)

        if self.baud is not None:
            baud_label = QLabel(f"波特率: {self.baud}")
            baud_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(baud_label)
        
        # 连接按钮
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.connect_btn)
        
        # 状态指示灯
        self.status_indicator = StatusIndicator(show_text=True, indicator_size=10)
        self.status_indicator.set_disconnected()
        layout.addWidget(self.status_indicator)
        
        self.setLayout(layout)
        
        # 设置样式
        self.setStyleSheet("""
            SensorConnectionWidget {
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: #f9f9f9;
            }
        """)
    
    def _on_connect_clicked(self):
        """连接按钮点击处理"""
        if self.is_connected:
            self.disconnect_clicked.emit(self.sensor_id)
        else:
            self.connect_clicked.emit(self.sensor_id)
    
    def set_connected(self, connected: bool):
        """设置连接状态"""
        self.is_connected = connected
        
        if connected:
            self.connect_btn.setText("断开")
            self.status_indicator.set_connected()
        else:
            self.connect_btn.setText("连接")
            self.status_indicator.set_disconnected()
    
    def set_error(self):
        """设置错误状态"""
        self.status_indicator.set_error()
        self.is_connected = False
        self.connect_btn.setText("连接")
    
    def set_busy(self):
        """设置忙碌状态"""
        self.status_indicator.set_busy()
        self.connect_btn.setEnabled(False)
    
    def set_idle(self):
        """设置空闲状态"""
        self.connect_btn.setEnabled(True)


class ConnectionPanel(QWidget):
    """连接管理面板"""
    
    # 信号定义
    connect_sensor = pyqtSignal(str)      # 连接传感器 (sensor_id)
    disconnect_sensor = pyqtSignal(str)   # 断开传感器 (sensor_id)
    connect_all = pyqtSignal()            # 连接所有
    disconnect_all = pyqtSignal()         # 断开所有
    
    def __init__(self, config: dict, parent=None):
        """
        初始化连接管理面板
        
        Args:
            config: 配置字典
            parent: 父组件
        """
        super().__init__(parent)
        
        self.config = config
        self.sensor_widgets = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        
        # 面板标题
        title_label = QLabel("<h3>传感器连接管理</h3>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 传感器连接区域
        sensors_layout = QGridLayout()
        sensors_layout.setSpacing(10)
        
        # 粘附脚传感器
        nianfujiao_config = self.config['sensor']['nianfujiao']
        nianfujiao_widget = SensorConnectionWidget(
            'nianfujiao',
            '粘附脚传感器',
            endpoint=nianfujiao_config['port'],
            baud=nianfujiao_config['baud'],
            protocol='串口',
        )
        nianfujiao_widget.connect_clicked.connect(self.connect_sensor.emit)
        nianfujiao_widget.disconnect_clicked.connect(self.disconnect_sensor.emit)
        self.sensor_widgets['nianfujiao'] = nianfujiao_widget
        sensors_layout.addWidget(nianfujiao_widget, 0, 0)
        
        # 六轴力传感器
        liuzhouli_config = self.config['sensor']['m8128b1']
        transport = str(liuzhouli_config.get('transport', 'serial')).strip().lower()
        if transport in ('ethernet', 'tcp', 'eth'):
            protocol = '以太网'
            endpoint = f"{liuzhouli_config.get('ip', 'UNKNOWN')}:{liuzhouli_config.get('tcp_port', 4008)}"
            baud = None
        else:
            protocol = '串口'
            endpoint = liuzhouli_config.get('port', 'UNKNOWN')
            baud = liuzhouli_config.get('baudrate', 115200)

        liuzhouli_widget = SensorConnectionWidget(
            'liuzhouli',
            '六轴力传感器',
            endpoint=endpoint,
            baud=baud,
            protocol=protocol,
        )
        liuzhouli_widget.connect_clicked.connect(self.connect_sensor.emit)
        liuzhouli_widget.disconnect_clicked.connect(self.disconnect_sensor.emit)
        self.sensor_widgets['liuzhouli'] = liuzhouli_widget
        sensors_layout.addWidget(liuzhouli_widget, 0, 1)
        
        layout.addLayout(sensors_layout)
        
        # 批量操作按钮
        batch_layout = QHBoxLayout()
        
        connect_all_btn = QPushButton("连接所有")
        connect_all_btn.clicked.connect(self.connect_all.emit)
        batch_layout.addWidget(connect_all_btn)
        
        disconnect_all_btn = QPushButton("断开所有")
        disconnect_all_btn.clicked.connect(self.disconnect_all.emit)
        batch_layout.addWidget(disconnect_all_btn)
        
        layout.addLayout(batch_layout)
        
        self.setLayout(layout)
    
    def update_sensor_status(self, sensor_id: str, connected: bool):
        """
        更新传感器连接状态
        
        Args:
            sensor_id: 传感器ID
            connected: 是否已连接
        """
        if sensor_id in self.sensor_widgets:
            self.sensor_widgets[sensor_id].set_connected(connected)
    
    def set_sensor_error(self, sensor_id: str):
        """
        设置传感器错误状态
        
        Args:
            sensor_id: 传感器ID
        """
        if sensor_id in self.sensor_widgets:
            self.sensor_widgets[sensor_id].set_error()
    
    def set_all_busy(self, busy: bool):
        """
        设置所有传感器忙碌/空闲状态
        
        Args:
            busy: 是否忙碌
        """
        for widget in self.sensor_widgets.values():
            if busy:
                widget.set_busy()
            else:
                widget.set_idle()
