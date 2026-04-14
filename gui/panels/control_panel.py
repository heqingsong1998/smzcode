"""
控制面板 - 传感器控制操作
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QLabel, QGridLayout)
from PyQt5.QtCore import pyqtSignal, Qt


class ControlPanel(QWidget):
    """传感器控制面板"""
    
    # HWT606-1 信号
    hwt606_1_accel_calib = pyqtSignal()
    hwt606_1_angle_zero = pyqtSignal()
    hwt606_1_reset_baseline = pyqtSignal()
    
    # HWT606-2 信号
    hwt606_2_accel_calib = pyqtSignal()
    hwt606_2_angle_zero = pyqtSignal()
    hwt606_2_reset_baseline = pyqtSignal()
    
    # 粘附脚 信号
    nianfujiao_reply = pyqtSignal()
    nianfujiao_engage = pyqtSignal()
    nianfujiao_zero = pyqtSignal()
    
    # 六轴力 信号
    liuzhouli_zero = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        
        # 面板标题
        title_label = QLabel("<h3>传感器控制</h3>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # HWT606-1 控制组
        hwt606_1_group = QGroupBox("HWT606 传感器1")
        hwt606_1_layout = QHBoxLayout()
        
        self.hwt606_1_accel_btn = QPushButton("加速度校准")
        self.hwt606_1_accel_btn.clicked.connect(self.hwt606_1_accel_calib.emit)
        hwt606_1_layout.addWidget(self.hwt606_1_accel_btn)
        
        self.hwt606_1_zero_btn = QPushButton("角度清零")
        self.hwt606_1_zero_btn.clicked.connect(self.hwt606_1_angle_zero.emit)
        hwt606_1_layout.addWidget(self.hwt606_1_zero_btn)
        
        self.hwt606_1_reset_btn = QPushButton("重置基准")
        self.hwt606_1_reset_btn.clicked.connect(self.hwt606_1_reset_baseline.emit)
        hwt606_1_layout.addWidget(self.hwt606_1_reset_btn)
        
        hwt606_1_group.setLayout(hwt606_1_layout)
        layout.addWidget(hwt606_1_group)
        
        # HWT606-2 控制组
        hwt606_2_group = QGroupBox("HWT606 传感器2")
        hwt606_2_layout = QHBoxLayout()
        
        self.hwt606_2_accel_btn = QPushButton("加速度校准")
        self.hwt606_2_accel_btn.clicked.connect(self.hwt606_2_accel_calib.emit)
        hwt606_2_layout.addWidget(self.hwt606_2_accel_btn)
        
        self.hwt606_2_zero_btn = QPushButton("角度清零")
        self.hwt606_2_zero_btn.clicked.connect(self.hwt606_2_angle_zero.emit)
        hwt606_2_layout.addWidget(self.hwt606_2_zero_btn)
        
        self.hwt606_2_reset_btn = QPushButton("重置基准")
        self.hwt606_2_reset_btn.clicked.connect(self.hwt606_2_reset_baseline.emit)
        hwt606_2_layout.addWidget(self.hwt606_2_reset_btn)
        
        hwt606_2_group.setLayout(hwt606_2_layout)
        layout.addWidget(hwt606_2_group)
        
        # 粘附脚控制组
        nianfujiao_group = QGroupBox("粘附脚传感器")
        nianfujiao_layout = QHBoxLayout()
        
        self.nianfujiao_reply_btn = QPushButton("回复")
        self.nianfujiao_reply_btn.setToolTip("恢复到默认状态")
        self.nianfujiao_reply_btn.clicked.connect(self.nianfujiao_reply.emit)
        nianfujiao_layout.addWidget(self.nianfujiao_reply_btn)
        
        self.nianfujiao_engage_btn = QPushButton("吸合")
        self.nianfujiao_engage_btn.clicked.connect(self.nianfujiao_engage.emit)
        nianfujiao_layout.addWidget(self.nianfujiao_engage_btn)
        
        self.nianfujiao_zero_btn = QPushButton("清零")
        self.nianfujiao_zero_btn.clicked.connect(self.nianfujiao_zero.emit)
        nianfujiao_layout.addWidget(self.nianfujiao_zero_btn)
        
        nianfujiao_group.setLayout(nianfujiao_layout)
        layout.addWidget(nianfujiao_group)
        
        # 六轴力控制组
        liuzhouli_group = QGroupBox("六轴力传感器")
        liuzhouli_layout = QHBoxLayout()
        
        self.liuzhouli_zero_btn = QPushButton("清零")
        self.liuzhouli_zero_btn.clicked.connect(self.liuzhouli_zero.emit)
        liuzhouli_layout.addWidget(self.liuzhouli_zero_btn)
        
        liuzhouli_group.setLayout(liuzhouli_layout)
        layout.addWidget(liuzhouli_group)
        
        # 添加弹性空间
        layout.addStretch()
        
        self.setLayout(layout)
        
        # 初始禁用所有按钮
        self._set_all_buttons_enabled(False)
    
    def _set_all_buttons_enabled(self, enabled: bool):
        """设置所有按钮启用/禁用"""
        # HWT606-1
        self.hwt606_1_accel_btn.setEnabled(enabled)
        self.hwt606_1_zero_btn.setEnabled(enabled)
        self.hwt606_1_reset_btn.setEnabled(enabled)
        
        # HWT606-2
        self.hwt606_2_accel_btn.setEnabled(enabled)
        self.hwt606_2_zero_btn.setEnabled(enabled)
        self.hwt606_2_reset_btn.setEnabled(enabled)
        
        # 粘附脚
        self.nianfujiao_reply_btn.setEnabled(enabled)
        self.nianfujiao_engage_btn.setEnabled(enabled)
        self.nianfujiao_zero_btn.setEnabled(enabled)
        
        # 六轴力
        self.liuzhouli_zero_btn.setEnabled(enabled)
    
    def update_button_states(self, connection_status: dict):
        """
        根据连接状态更新按钮
        
        Args:
            connection_status: 连接状态字典
        """
        # HWT606-1
        hwt606_1_connected = connection_status.get('hwt606_1', False)
        self.hwt606_1_accel_btn.setEnabled(hwt606_1_connected)
        self.hwt606_1_zero_btn.setEnabled(hwt606_1_connected)
        self.hwt606_1_reset_btn.setEnabled(hwt606_1_connected)
        
        # HWT606-2
        hwt606_2_connected = connection_status.get('hwt606_2', False)
        self.hwt606_2_accel_btn.setEnabled(hwt606_2_connected)
        self.hwt606_2_zero_btn.setEnabled(hwt606_2_connected)
        self.hwt606_2_reset_btn.setEnabled(hwt606_2_connected)
        
        # 粘附脚
        nianfujiao_connected = connection_status.get('nianfujiao', False)
        self.nianfujiao_reply_btn.setEnabled(nianfujiao_connected)
        self.nianfujiao_engage_btn.setEnabled(nianfujiao_connected)
        self.nianfujiao_zero_btn.setEnabled(nianfujiao_connected)
        
        # 六轴力
        liuzhouli_connected = connection_status.get('liuzhouli', False)
        self.liuzhouli_zero_btn.setEnabled(liuzhouli_connected)