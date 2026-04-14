"""
数据显示面板 - 显示四个传感器的实时数据
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QLabel, QGridLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class HWT606DisplayWidget(QWidget):
    """HWT606传感器数据显示组"""
    
    def __init__(self, sensor_name: str, parent=None):
        super().__init__(parent)
        self.sensor_name = sensor_name
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 标题
        title = QLabel(f"<b>{self.sensor_name}</b>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 数据网格
        grid = QGridLayout()
        grid.setSpacing(5)
        
        # 创建数据标签
        font = QFont("Courier New", 10)
        
        # 加速度
        acc_label = QLabel("<b>加速度 (g):</b>")
        grid.addWidget(acc_label, 0, 0)
        
        self.acc_x_label = QLabel("X: 0.000")
        self.acc_x_label.setFont(font)
        grid.addWidget(self.acc_x_label, 1, 0)
        
        self.acc_y_label = QLabel("Y: 0.000")
        self.acc_y_label.setFont(font)
        grid.addWidget(self.acc_y_label, 2, 0)
        
        self.acc_z_label = QLabel("Z: 0.000")
        self.acc_z_label.setFont(font)
        grid.addWidget(self.acc_z_label, 3, 0)
        
        # 角速度
        gyro_label = QLabel("<b>角速度 (°/s):</b>")
        grid.addWidget(gyro_label, 0, 1)
        
        self.gyro_x_label = QLabel("X: 0.000")
        self.gyro_x_label.setFont(font)
        grid.addWidget(self.gyro_x_label, 1, 1)
        
        self.gyro_y_label = QLabel("Y: 0.000")
        self.gyro_y_label.setFont(font)
        grid.addWidget(self.gyro_y_label, 2, 1)
        
        self.gyro_z_label = QLabel("Z: 0.000")
        self.gyro_z_label.setFont(font)
        grid.addWidget(self.gyro_z_label, 3, 1)
        
        # 角度
        angle_label = QLabel("<b>角度 (°):</b>")
        grid.addWidget(angle_label, 0, 2)
        
        self.angle_x_label = QLabel("Roll: 0.00")
        self.angle_x_label.setFont(font)
        grid.addWidget(self.angle_x_label, 1, 2)
        
        self.angle_y_label = QLabel("Pitch: 0.00")
        self.angle_y_label.setFont(font)
        grid.addWidget(self.angle_y_label, 2, 2)
        
        self.angle_z_label = QLabel("Yaw: 0.00")
        self.angle_z_label.setFont(font)
        grid.addWidget(self.angle_z_label, 3, 2)
        
        #速度
        vel_label = QLabel("<b>速度 (m/s):</b>")
        grid.addWidget(vel_label, 0, 3)

        self.vel_x_label = QLabel("X: 0.000")
        self.vel_x_label.setFont(font)
        grid.addWidget(self.vel_x_label, 1, 3)

        self.vel_y_label = QLabel("Y: 0.000")
        self.vel_y_label.setFont(font)
        grid.addWidget(self.vel_y_label, 2, 3)

        self.vel_z_label = QLabel("Z: 0.000")
        self.vel_z_label.setFont(font)
        grid.addWidget(self.vel_z_label, 3, 3)

        layout.addLayout(grid)
        self.setLayout(layout)
        
        # 样式
        self.setStyleSheet("""
            HWT606DisplayWidget {
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: #f0f8ff;
            }
        """)
    
    def update_data(self, data: dict):
        """
        更新数据显示
        
        Args:
            data: 数据字典
        """
        # 加速度
        self.acc_x_label.setText(f"X: {data.get('acc_x', 0.0):+.3f}")
        self.acc_y_label.setText(f"Y: {data.get('acc_y', 0.0):+.3f}")
        self.acc_z_label.setText(f"Z: {data.get('acc_z', 0.0):+.3f}")
        
        # 角速度
        self.gyro_x_label.setText(f"X: {data.get('gyro_x', 0.0):+.3f}")
        self.gyro_y_label.setText(f"Y: {data.get('gyro_y', 0.0):+.3f}")
        self.gyro_z_label.setText(f"Z: {data.get('gyro_z', 0.0):+.3f}")
        
        # 角度
        self.angle_x_label.setText(f"Roll: {data.get('angle_x', 0.0):+.2f}")
        self.angle_y_label.setText(f"Pitch: {data.get('angle_y', 0.0):+.2f}")
        self.angle_z_label.setText(f"Yaw: {data.get('angle_z', 0.0):+.2f}")

        # 速度
        self.vel_x_label.setText(f"X: {data.get('vel_x', 0.0):+.3f}")
        self.vel_y_label.setText(f"Y: {data.get('vel_y', 0.0):+.3f}")
        self.vel_z_label.setText(f"Z: {data.get('vel_z', 0.0):+.3f}")



class LiuZhouLiDisplayWidget(QWidget):
    """六轴力传感器数据显示组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 标题
        title = QLabel("<b>六轴力传感器</b>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 数据网格
        grid = QGridLayout()
        grid.setSpacing(10)
        
        font = QFont("Courier New", 11)
        
        # �?(N)
        force_label = QLabel("<b>力 (N):</b>")
        grid.addWidget(force_label, 0, 0)
        
        self.fx_label = QLabel("Fx: +0.0000")
        self.fx_label.setFont(font)
        grid.addWidget(self.fx_label, 1, 0)
        
        self.fy_label = QLabel("Fy: +0.0000")
        self.fy_label.setFont(font)
        grid.addWidget(self.fy_label, 2, 0)
        
        self.fz_label = QLabel("Fz: +0.0000")
        self.fz_label.setFont(font)
        grid.addWidget(self.fz_label, 3, 0)
        
        # 力矩 (N·m)
        moment_label = QLabel("<b>力矩 (N·m):</b>")
        grid.addWidget(moment_label, 0, 1)
        
        self.mx_label = QLabel("Mx: +0.000000")
        self.mx_label.setFont(font)
        grid.addWidget(self.mx_label, 1, 1)
        
        self.my_label = QLabel("My: +0.000000")
        self.my_label.setFont(font)
        grid.addWidget(self.my_label, 2, 1)
        
        self.mz_label = QLabel("Mz: +0.000000")
        self.mz_label.setFont(font)
        grid.addWidget(self.mz_label, 3, 1)
        
        layout.addLayout(grid)
        self.setLayout(layout)
        
        # 样式
        self.setStyleSheet("""
            LiuZhouLiDisplayWidget {
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: #fff8dc;
            }
        """)
    
    def update_data(self, data: dict):
        """
        更新数据显示
        
        Args:
            data: 数据字典 {'Fx': float, 'Fy': float, ...}
        """
        try:
            # 安全获取浮点数值（防御性编程）
            def safe_float(value, default=0.0):
                """安全转换为浮点数"""
                if isinstance(value, (list, tuple)):
                    return float(value[0]) if len(value) > 0 else default
                return float(value)
            
            fx = safe_float(data.get('Fx', 0.0))
            fy = safe_float(data.get('Fy', 0.0))
            fz = safe_float(data.get('Fz', 0.0))
            mx = safe_float(data.get('Mx', 0.0))
            my = safe_float(data.get('My', 0.0))
            mz = safe_float(data.get('Mz', 0.0))
            
            self.fx_label.setText(f"Fx: {fx:+.4f}")
            self.fy_label.setText(f"Fy: {fy:+.4f}")
            self.fz_label.setText(f"Fz: {fz:+.4f}")
            self.mx_label.setText(f"Mx: {mx:+.6f}")
            self.my_label.setText(f"My: {my:+.6f}")
            self.mz_label.setText(f"Mz: {mz:+.6f}")
            
        except Exception as e:
            print(f"[ERROR] 更新六轴力显示失败: {e}")
            print(f"[DEBUG] 数据类型: {type(data)}")
            print(f"[DEBUG] 数据内容: {data}")


class NianFuJiaoDisplayWidget(QWidget):
    """粘附脚传感器 Style0 数据显示组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        title = QLabel("<b>粘附脚传感器</b>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        headers = [
            'Fx1', 'Fy1', 'Fz1+', 'Mx1', 'My1', 'JJJ1_1', 'JJJ1_2',
            'Fx2', 'Fy2', 'Fz2+', 'Mx2', 'My2', 'flag1', 'flag2',
            'FZ1-', 'FZ2-'
        ]
        self.style0_table = self._create_table(16, headers)
        layout.addWidget(self.style0_table)
        self.setLayout(layout)

    def _create_table(self, col_count: int, headers: list) -> QTableWidget:
        table = QTableWidget(2, col_count)
        table.setHorizontalHeaderLabels(headers)
        table.setVerticalHeaderLabels(['原始值', '标定值'])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)

        for row in range(2):
            for col in range(col_count):
                    table.setItem(row, col, QTableWidgetItem("0"))
        return table

    def update_data(self, style: int, data: dict):
        if style != 0:
            return
        self._update_table(self.style0_table, data)

    def _update_table(self, table: QTableWidget, data: dict):
        """更新表格数据（style0 包含原始值和标定值）"""
        raw_values = data.get('raw', [])
        calibrated_values = data.get('calibrated', [])

        col_count = table.columnCount()
        for col in range(min(col_count, len(raw_values))):
            item = table.item(0, col)
            if item:
                item.setText(f"{raw_values[col]}")
        for col in range(min(col_count, len(calibrated_values))):
            item = table.item(1, col)
            if item:
                item.setText(f"{calibrated_values[col]:.4f}")
class DataDisplayPanel(QWidget):
    """数据显示面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        
        # 面板标题
        title_label = QLabel("<h3>传感器数据显示</h3>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # HWT606传感器区
        hwt606_layout = QHBoxLayout()
        
        self.hwt606_1_widget = HWT606DisplayWidget("HWT606 传感1")
        hwt606_layout.addWidget(self.hwt606_1_widget)
        
        self.hwt606_2_widget = HWT606DisplayWidget("HWT606 传感2")
        hwt606_layout.addWidget(self.hwt606_2_widget)
        
        layout.addLayout(hwt606_layout)
        
        # 六轴力传感器
        self.liuzhouli_widget = LiuZhouLiDisplayWidget()
        layout.addWidget(self.liuzhouli_widget)
        
        # 粘附脚传感器
        self.nianfujiao_widget = NianFuJiaoDisplayWidget()
        layout.addWidget(self.nianfujiao_widget)
        
        self.setLayout(layout)
    
    def update_hwt606_1_data(self, data: dict):
        """更新HWT606-1数据"""
        self.hwt606_1_widget.update_data(data)
    
    def update_hwt606_2_data(self, data: dict):
        """更新HWT606-2数据"""
        self.hwt606_2_widget.update_data(data)
    
    def update_liuzhouli_data(self, data: dict):
        """更新六轴力数据"""
        self.liuzhouli_widget.update_data(data)
    
    def update_nianfujiao_data(self, style: int, data: dict):
        """更新粘附脚数据"""
        self.nianfujiao_widget.update_data(style, data)
