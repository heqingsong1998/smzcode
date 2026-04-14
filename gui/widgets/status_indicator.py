"""
状态指示灯组件
"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QBrush


class StatusIndicator(QWidget):
    """状态指示灯组件"""
    
    # 状态枚举
    STATUS_DISCONNECTED = 0  # 未连接（灰色）
    STATUS_CONNECTED = 1     # 已连接（绿色）
    STATUS_ERROR = 2         # 错误（红色）
    STATUS_BUSY = 3          # 忙碌（黄色）
    
    # 状态颜色映射
    STATUS_COLORS = {
        STATUS_DISCONNECTED: QColor(128, 128, 128),  # 灰色
        STATUS_CONNECTED: QColor(0, 200, 0),         # 绿色
        STATUS_ERROR: QColor(255, 0, 0),             # 红色
        STATUS_BUSY: QColor(255, 200, 0)             # 黄色
    }
    
    # 状态文本映射
    STATUS_TEXTS = {
        STATUS_DISCONNECTED: "未连接",
        STATUS_CONNECTED: "已连接",
        STATUS_ERROR: "错误",
        STATUS_BUSY: "忙碌"
    }
    
    def __init__(self, parent=None, show_text=True, indicator_size=12):
        """
        初始化状态指示灯
        
        Args:
            parent: 父组件
            show_text: 是否显示状态文本
            indicator_size: 指示灯大小（直径）
        """
        super().__init__(parent)
        
        self._status = self.STATUS_DISCONNECTED
        self._show_text = show_text
        self._indicator_size = indicator_size
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # 状态文本标签
        if self._show_text:
            self.text_label = QLabel(self.STATUS_TEXTS[self._status])
            layout.addWidget(self.text_label)
        
        self.setLayout(layout)
        self.setFixedHeight(self._indicator_size + 4)
    
    def paintEvent(self, event):
        """绘制指示灯"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 获取当前状态颜色
        color = self.STATUS_COLORS.get(self._status, QColor(128, 128, 128))
        
        # 绘制圆形指示灯
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        
        # 计算绘制位置（右侧）
        x = self.width() - self._indicator_size - 2
        y = (self.height() - self._indicator_size) // 2
        
        painter.drawEllipse(x, y, self._indicator_size, self._indicator_size)
    
    @pyqtProperty(int)
    def status(self):
        """获取当前状态"""
        return self._status
    
    @status.setter
    def status(self, value):
        """设置状态"""
        if value != self._status:
            self._status = value
            if self._show_text:
                self.text_label.setText(self.STATUS_TEXTS.get(value, "未知"))
            self.update()  # 触发重绘
    
    def set_disconnected(self):
        """设置为未连接状态"""
        self.status = self.STATUS_DISCONNECTED
    
    def set_connected(self):
        """设置为已连接状态"""
        self.status = self.STATUS_CONNECTED
    
    def set_error(self):
        """设置为错误状态"""
        self.status = self.STATUS_ERROR
    
    def set_busy(self):
        """设置为忙碌状态"""
        self.status = self.STATUS_BUSY
    
    def sizeHint(self):
        """推荐大小"""
        from PyQt5.QtCore import QSize
        width = 80 if self._show_text else self._indicator_size + 4
        return QSize(width, self._indicator_size + 4)