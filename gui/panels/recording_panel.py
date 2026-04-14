"""
采集控制面板 - 数据采集和保存控制
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QLabel, QFileDialog)
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont
import os


class RecordingPanel(QWidget):
    """采集控制面板"""
    
    # 信号定义
    start_recording = pyqtSignal()   # 开始采集
    stop_recording = pyqtSignal()    # 停止采集
    open_folder = pyqtSignal(str)    # 打开文件夹 (folder_path)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.is_recording = False
        self.recording_duration = 0  # 采集时长（秒）
        
        # 定时器（更新采集时长）
        self.duration_timer = QTimer()
        self.duration_timer.timeout.connect(self._update_duration)
        self.duration_timer.setInterval(1000)  # 1秒更新一次
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        
        # 面板标题
        title_label = QLabel("<h3>数据采集控制</h3>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 控制按钮区域
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("🔴 开始采集")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.start_btn.clicked.connect(self._on_start_clicked)
        button_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏸️ 停止采集")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        button_layout.addWidget(self.stop_btn)
        
        self.folder_btn = QPushButton("📁 打开目录")
        self.folder_btn.setMinimumHeight(40)
        self.folder_btn.clicked.connect(self._on_open_folder)
        button_layout.addWidget(self.folder_btn)
        
        layout.addLayout(button_layout)
        
        # 状态信息区域
        status_group = QGroupBox("采集状态")
        status_layout = QVBoxLayout()
        
        font = QFont("Courier New", 10)
        
        # 采集状态
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("采集状态:"))
        self.status_label = QLabel("⏸️ 已停止")
        self.status_label.setFont(font)
        self.status_label.setStyleSheet("color: #666;")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        status_layout.addLayout(status_row)
        
        # 采集时长
        duration_row = QHBoxLayout()
        duration_row.addWidget(QLabel("采集时长:"))
        self.duration_label = QLabel("00:00:00")
        self.duration_label.setFont(font)
        duration_row.addWidget(self.duration_label)
        duration_row.addStretch()
        status_layout.addLayout(duration_row)
        
        # 数据条数
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("数据条数:"))
        self.count_label = QLabel("粘附脚: 0 | 六轴力: 0")
        self.count_label.setFont(font)
        count_row.addWidget(self.count_label)
        count_row.addStretch()
        status_layout.addLayout(count_row)
        
        # 存储路径
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("存储路径:"))
        self.path_label = QLabel("未开始采集")
        self.path_label.setFont(font)
        self.path_label.setWordWrap(True)
        path_row.addWidget(self.path_label)
        path_row.addStretch()
        status_layout.addLayout(path_row)
        
        # 文件大小
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("文件大小:"))
        self.size_label = QLabel("0 MB")
        self.size_label.setFont(font)
        size_row.addWidget(self.size_label)
        size_row.addStretch()
        status_layout.addLayout(size_row)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        self.setLayout(layout)
    
    def _on_start_clicked(self):
        """开始采集按钮点击"""
        self.is_recording = True
        self.recording_duration = 0
        
        # 更新UI
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("🔴 采集中")
        self.status_label.setStyleSheet("color: #f44336; font-weight: bold;")
        
        # 启动定时器
        self.duration_timer.start()
        
        # 发送信号
        self.start_recording.emit()
    
    def _on_stop_clicked(self):
        """停止采集按钮点击"""
        self.is_recording = False
        
        # 更新UI
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("⏸️ 已停止")
        self.status_label.setStyleSheet("color: #666;")
        
        # 停止定时器
        self.duration_timer.stop()
        
        # 发送信号
        self.stop_recording.emit()
    
    def _on_open_folder(self):
        """打开文件夹按钮点击"""
        path = self.path_label.text()
        if path and path != "未开始采集" and os.path.exists(path):
            self.open_folder.emit(path)
        else:
            # 打开默认数据目录
            default_path = os.path.join(os.getcwd(), "data", "sessions")
            if os.path.exists(default_path):
                self.open_folder.emit(default_path)
    
    def _update_duration(self):
        """更新采集时长"""
        self.recording_duration += 1
        
        hours = self.recording_duration // 3600
        minutes = (self.recording_duration % 3600) // 60
        seconds = self.recording_duration % 60
        
        self.duration_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    
    def update_data_counts(self, counts: dict):
        """
        更新数据条数
        
        Args:
            counts: 数据条数字典 {'hwt606_1': 100, 'hwt606_2': 98, ...}
        """
        text = (f"粘附脚: {counts.get('nianfujiao', 0)} | "
                f"六轴力: {counts.get('liuzhouli', 0)}")
        self.count_label.setText(text)
    
    def update_storage_path(self, path: str):
        """
        更新存储路径
        
        Args:
            path: 存储路径
        """
        self.path_label.setText(path)
    
    def update_file_size(self, size_mb: float):
        """
        更新文件大小
        
        Args:
            size_mb: 文件大小（MB）
        """
        self.size_label.setText(f"{size_mb:.2f} MB")
    
    def reset(self):
        """重置面板"""
        self.is_recording = False
        self.recording_duration = 0
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("⏸️ 已停止")
        self.status_label.setStyleSheet("color: #666;")
        self.duration_label.setText("00:00:00")
        self.count_label.setText("粘附脚: 0 | 六轴力: 0")
        self.path_label.setText("未开始采集")
        self.size_label.setText("0 MB")
        
        self.duration_timer.stop()
