"""
日志显示组件
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime
from PyQt5.QtGui import QTextCursor, QColor, QTextCharFormat
import sys
from io import StringIO


class LogWidget(QWidget):
    """日志显示组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
        # 重定向 stdout 和 stderr
        self.stdout_redirector = StreamRedirector(self._append_log)
        self.stderr_redirector = StreamRedirector(self._append_log, is_error=True)
        
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        self.clear_btn = QPushButton("🗑️ 清空日志")
        self.clear_btn.clicked.connect(self._clear_log)
        toolbar.addWidget(self.clear_btn)
        
        self.autoscroll_btn = QPushButton("📜 自动滚动: 开")
        self.autoscroll_btn.setCheckable(True)
        self.autoscroll_btn.setChecked(True)
        self.autoscroll_btn.clicked.connect(self._toggle_autoscroll)
        toolbar.addWidget(self.autoscroll_btn)
        
        toolbar.addStretch()
        
        layout.addLayout(toolbar)
        
        # 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                border: 1px solid #3c3c3c;
            }
        """)
        layout.addWidget(self.log_text)
        
        self.setLayout(layout)
        
        # 自动滚动标志
        self.auto_scroll = True
    
    def _append_log(self, text: str, is_error: bool = False):
        """
        追加日志
        
        Args:
            text: 日志文本
            is_error: 是否为错误信息
        """
        if not text.strip():
            return
        
        # 添加时间戳
        timestamp = QDateTime.currentDateTime().toString("[yyyy-MM-dd HH:mm:ss.zzz]")
        
        # 移动到末尾
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # 设置时间戳格式（灰色）
        time_format = QTextCharFormat()
        time_format.setForeground(QColor("#808080"))
        cursor.setCharFormat(time_format)
        cursor.insertText(timestamp + " ")
        
        # 设置日志内容格式
        text_format = QTextCharFormat()
        
        # 根据日志级别设置颜色
        if is_error or "[ERROR]" in text:
            text_format.setForeground(QColor("#f48771"))  # 红色
        elif "[WARNING]" in text or "[WARN]" in text:
            text_format.setForeground(QColor("#dcdcaa"))  # 黄色
        elif "[INFO]" in text:
            text_format.setForeground(QColor("#4ec9b0"))  # 青色
        elif "[DEBUG]" in text:
            text_format.setForeground(QColor("#c586c0"))  # 紫色
        elif "[SUCCESS]" in text or "成功" in text or "✅" in text:
            text_format.setForeground(QColor("#4ec9b0"))  # 绿色
        else:
            text_format.setForeground(QColor("#d4d4d4"))  # 默认白色
        
        cursor.setCharFormat(text_format)
        cursor.insertText(text + "\n")
        
        # 自动滚动到底部
        if self.auto_scroll:
            self.log_text.setTextCursor(cursor)
            self.log_text.ensureCursorVisible()
    
    def _clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self._append_log("📝 日志已清空")
    
    def _toggle_autoscroll(self, checked: bool):
        """切换自动滚动"""
        self.auto_scroll = checked
        if checked:
            self.autoscroll_btn.setText("📜 自动滚动: 开")
        else:
            self.autoscroll_btn.setText("📜 自动滚动: 关")
    
    def start_capture(self):
        """开始捕获标准输出"""
        sys.stdout = self.stdout_redirector
        sys.stderr = self.stderr_redirector
    
    def stop_capture(self):
        """停止捕获标准输出"""
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


class StreamRedirector(StringIO):
    """流重定向器"""
    
    def __init__(self, callback, is_error=False):
        super().__init__()
        self.callback = callback
        self.is_error = is_error
        self.original_stream = sys.stderr if is_error else sys.stdout
    
    def write(self, text):
        """重写 write 方法"""
        # 同时输出到原始流（保留控制台输出）
        self.original_stream.write(text)
        self.original_stream.flush()
        
        # 回调到GUI
        if text and text != '\n':
            self.callback(text, self.is_error)
    
    def flush(self):
        """刷新"""
        self.original_stream.flush()