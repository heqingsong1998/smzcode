"""
主窗口 - 整合所有面板和功能
"""
import sys
import os
import subprocess
import platform
from typing import Optional

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QSplitter, QMessageBox, QApplication)
from PyQt5.QtCore import Qt, QTimer

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from gui.panels.connection_panel import ConnectionPanel
from gui.panels.control_panel import ControlPanel
from gui.panels.data_display_panel import DataDisplayPanel
from gui.panels.recording_panel import RecordingPanel

from core.sensor_manager import SensorManager
from core.data_recorder import DataRecorder
from gui.widgets.log_widget import LogWidget


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self, config_path: str = "config/default.yaml"):
        super().__init__()
        
        self.config_path = config_path
        
        # 创建核心组件
        self.sensor_manager = SensorManager(config_path)
        self.data_recorder = DataRecorder()
        
        # 定时器（更新文件大小等统计信息）
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_statistics)
        self.stats_timer.setInterval(1000)  # 1秒更新一次
        
        self._setup_ui()
        self._connect_signals()
        
        self.setWindowTitle("传感器数据采集系统 v1.0")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)
    
    def _setup_ui(self):
        """设置UI"""
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # 创建左右分隔器
        horizontal_splitter = QSplitter(Qt.Horizontal)
        
        # === 左侧面板（保持不变）===
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)
        
        # 连接管理面板
        self.connection_panel = ConnectionPanel(self.sensor_manager.config)
        left_layout.addWidget(self.connection_panel)
        
        # 控制面板
        self.control_panel = ControlPanel()
        left_layout.addWidget(self.control_panel)
        
        # 采集控制面板
        self.recording_panel = RecordingPanel()
        left_layout.addWidget(self.recording_panel)
        
        horizontal_splitter.addWidget(left_widget)
        
        # === 右侧面板（数据显示 + 日志）===
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_widget.setLayout(right_layout)
        
        # 创建右侧上下分隔器
        right_splitter = QSplitter(Qt.Vertical)
        
        # 数据显示面板
        self.data_display_panel = DataDisplayPanel()
        right_splitter.addWidget(self.data_display_panel)
        
        # 日志显示面板
        self.log_widget = LogWidget()
        right_splitter.addWidget(self.log_widget)
        
        # 设置数据显示和日志的比例（数据60%，日志40%）
        right_splitter.setStretchFactor(0, 6)
        right_splitter.setStretchFactor(1, 4)
        
        right_layout.addWidget(right_splitter)
        horizontal_splitter.addWidget(right_widget)
        
        # 设置左右分隔比例（左30%，右70%）
        horizontal_splitter.setStretchFactor(0, 3)
        horizontal_splitter.setStretchFactor(1, 7)
        
        main_layout.addWidget(horizontal_splitter)
        
        # 启动日志捕获
        self.log_widget.start_capture()
        
        # 输出欢迎信息
        print("=" * 60)
        print("[INFO] 传感器数据采集系统 v1.0 已启动")
        print("=" * 60)
    
    def _connect_signals(self):
        """连接信号和槽"""
        # ========== 连接管理信号 ==========
        self.connection_panel.connect_sensor.connect(self._on_connect_sensor)
        self.connection_panel.disconnect_sensor.connect(self._on_disconnect_sensor)
        self.connection_panel.connect_all.connect(self._on_connect_all)
        self.connection_panel.disconnect_all.connect(self._on_disconnect_all)

        # ========== 数据记录回调（高频直接调用，不通过信号） ==========
        # 仅保留当前需要采集的两个传感器（粘附脚 + 六轴力）
        self.sensor_manager.record_callback_nianfujiao = self.data_recorder.write_nianfujiao_data
        self.sensor_manager.record_callback_liuzhouli = self.data_recorder.write_liuzhouli_data
        
        # ========== 传感器状态变化信号 ==========
        self.sensor_manager.connection_status_changed.connect(
            self._on_sensor_status_changed
        )
        self.sensor_manager.error_occurred.connect(self._on_sensor_error)
        
        # ========== 控制面板信号 ==========
        # 粘附脚
        self.control_panel.nianfujiao_reply.connect(
            self.sensor_manager.nianfujiao_reply
        )
        self.control_panel.nianfujiao_engage.connect(
            self.sensor_manager.nianfujiao_engage
        )
        self.control_panel.nianfujiao_zero.connect(
            self.sensor_manager.nianfujiao_zero
        )
        
        # 六轴力
        self.control_panel.liuzhouli_zero.connect(
            self.sensor_manager.liuzhouli_zero
        )
        
        # ========== 数据更新信号 ==========
        self.sensor_manager.nianfujiao_data_updated.connect(
            self._on_nianfujiao_data_updated
        )
        self.sensor_manager.liuzhouli_data_updated.connect(
            self._on_liuzhouli_data_updated
        )
        
        # ========== 采集控制信号 ==========
        self.recording_panel.start_recording.connect(self._on_start_recording)
        self.recording_panel.stop_recording.connect(self._on_stop_recording)
        self.recording_panel.open_folder.connect(self._on_open_folder)
    
    # ==================== 连接管理槽函数 ====================
    
    def _on_connect_sensor(self, sensor_id: str):
        """连接传感器"""
        self.connection_panel.set_all_busy(True)
        
        success = False
        if sensor_id == 'nianfujiao':
            success = self.sensor_manager.connect_nianfujiao()
        elif sensor_id == 'liuzhouli':
            success = self.sensor_manager.connect_liuzhouli()
        
        self.connection_panel.set_all_busy(False)
        
        if success:
            QMessageBox.information(self, "成功", f"{sensor_id} 连接成功！")
        else:
            QMessageBox.warning(self, "失败", f"{sensor_id} 连接失败，请检查连接参数和配置！")
    
    def _on_disconnect_sensor(self, sensor_id: str):
        """断开传感器"""
        if sensor_id == 'nianfujiao':
            self.sensor_manager.disconnect_nianfujiao()
        elif sensor_id == 'liuzhouli':
            self.sensor_manager.disconnect_liuzhouli()
        
        QMessageBox.information(self, "成功", f"{sensor_id} 已断开！")
    
    def _on_connect_all(self):
        """连接所有传感器"""
        self.connection_panel.set_all_busy(True)
        
        results = {
            'nianfujiao': self.sensor_manager.connect_nianfujiao(),
            'liuzhouli': self.sensor_manager.connect_liuzhouli()
        }
        
        self.connection_panel.set_all_busy(False)
        
        success_count = sum(results.values())
        if success_count == 2:
            QMessageBox.information(self, "成功", "所有传感器连接成功！")
        else:
            failed = [k for k, v in results.items() if not v]
            QMessageBox.warning(
                self, "部分失败", 
                f"成功: {success_count}/2\n失败: {', '.join(failed)}"
            )
    
    def _on_disconnect_all(self):
        """断开所有传感器"""
        # 如果正在采集，先停止
        if self.data_recorder.is_recording:
            self._on_stop_recording()
        
        self.sensor_manager.disconnect_all()
        QMessageBox.information(self, "成功", "所有传感器已断开！")
    
    def _on_sensor_status_changed(self, sensor_id: str, connected: bool):
        """传感器连接状态变化"""
        # 更新连接面板状态
        self.connection_panel.update_sensor_status(sensor_id, connected)
        
        # 更新控制面板按钮状态
        self.control_panel.update_button_states(
            self.sensor_manager.get_all_status()
        )
    
    def _on_sensor_error(self, sensor_id: str, error_msg: str):
        """传感器错误"""
        self.connection_panel.set_sensor_error(sensor_id)
        QMessageBox.critical(self, f"{sensor_id} 错误", error_msg)
    
    # ==================== 数据更新槽函数 ====================
    
    def _on_hwt606_1_data_updated(self, data: dict):
        """HWT606-1数据更新"""
        # 更新显示
        self.data_display_panel.update_hwt606_1_data(data)
        
        # 如果正在采集，写入数据
        if self.data_recorder.is_recording:
            self.data_recorder.write_hwt606_data('hwt606_1', data)
    
    def _on_hwt606_2_data_updated(self, data: dict):
        """HWT606-2数据更新"""
        self.data_display_panel.update_hwt606_2_data(data)
        
        if self.data_recorder.is_recording:
            self.data_recorder.write_hwt606_data('hwt606_2', data)
    
    def _on_nianfujiao_data_updated(self, style: int, data: dict):
        """粘附脚数据更新"""
        self.data_display_panel.update_nianfujiao_data(style, data)
        
        if self.data_recorder.is_recording:
            self.data_recorder.write_nianfujiao_data(style, data)
    
    def _on_liuzhouli_data_updated(self, data: dict):
        """六轴力数据更新"""
        self.data_display_panel.update_liuzhouli_data(data)
        
        if self.data_recorder.is_recording:
            self.data_recorder.write_liuzhouli_data(data)
    
    # ==================== 采集控制槽函数 ====================
    
    def _on_start_recording(self):
        """开始采集"""
        # 检查是否有传感器连接
        if not any(self.sensor_manager.get_all_status().values()):
            QMessageBox.warning(self, "警告", "请先连接至少一个传感器！")
            self.recording_panel.reset()
            return
        
        # 启动数据记录
        if self.data_recorder.start_recording():
            # 更新存储路径
            session_path = self.data_recorder.get_session_path()
            self.recording_panel.update_storage_path(session_path)
            
            # 启动统计定时器
            self.stats_timer.start()
            
            QMessageBox.information(self, "成功", "开始采集数据！")
        else:
            QMessageBox.critical(self, "错误", "启动数据采集失败！")
            self.recording_panel.reset()
    
    def _on_stop_recording(self):
        """停止采集"""
        if self.data_recorder.stop_recording():
            # 停止统计定时器
            self.stats_timer.stop()
            
            # 最后更新一次统计信息
            self._update_statistics()
            
            QMessageBox.information(
                self, "成功", 
                f"数据采集已停止！\n存储路径: {self.data_recorder.get_session_path()}"
            )
        else:
            QMessageBox.warning(self, "警告", "未在采集中！")
    
    def _on_open_folder(self, folder_path: str):
        """打开文件夹"""
        try:
            if platform.system() == 'Windows':
                os.startfile(folder_path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', folder_path])
            else:  # Linux
                subprocess.run(['xdg-open', folder_path])
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开文件夹: {str(e)}")
    
    # ==================== 统计信息更新 ====================
    
    def _update_statistics(self):
        """更新统计信息（数据条数、文件大小）"""
        if not self.data_recorder.is_recording:
            return
        
        # 更新数据条数
        self.recording_panel.update_data_counts(self.data_recorder.data_counts)
        
        # 更新文件大小
        session_path = self.data_recorder.get_session_path()
        if session_path and os.path.exists(session_path):
            total_size = 0
            for root, dirs, files in os.walk(session_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    total_size += os.path.getsize(file_path)
            
            size_mb = total_size / (1024 * 1024)
            self.recording_panel.update_file_size(size_mb)
    
    # ==================== 窗口关闭事件 ====================
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 如果正在采集，提示用户
        if self.data_recorder.is_recording:
            reply = QMessageBox.question(
                self, '确认退出',
                "正在采集数据，确定要退出吗？\n数据将会保存。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                event.ignore()
                return
            
            # 停止采集
            self.data_recorder.stop_recording()
        
        # 断开所有传感器
        self.sensor_manager.disconnect_all()
        
        event.accept()
