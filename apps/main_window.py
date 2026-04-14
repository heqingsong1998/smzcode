"""
主程序入口
传感器数据采集系统 - 第一阶段
"""
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from gui.main_window import MainWindow


def main():
    """主函数"""
    # 创建应用
    app = QApplication(sys.argv)
    
    # 设置应用信息
    app.setApplicationName("传感器数据采集系统")
    app.setOrganizationName("SMC304")
    app.setApplicationVersion("1.0.0")
    
    # 设置高DPI支持（适配高分辨率屏幕）
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # 设置全局样式
    app.setStyle("Fusion")
    
    # 可选：设置深色/浅色主题
    # _set_dark_theme(app)  # 取消注释以启用深色主题
    
    # 创建主窗口
    try:
        window = MainWindow(config_path="config/default.yaml")
        window.show()
        
        print("=" * 60)
        print("传感器数据采集系统 v1.0 - 第一阶段")
        print("=" * 60)
        print("[INFO] 系统已启动")
        print("[INFO] 配置文件: config/default.yaml")
        print("[INFO] 数据目录: data/sessions/")
        print("[INFO] 支持传感器:")
        print("       - HWT606 姿态传感器 x2")
        print("       - 粘附脚传感器")
        print("       - 六轴力传感器")
        print("[INFO] 刷新频率: 10Hz")
        print("=" * 60)
        
    except Exception as e:
        print(f"[ERROR] 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 运行应用
    return app.exec_()


def _set_dark_theme(app):
    """
    设置深色主题（可选）
    
    Args:
        app: QApplication实例
    """
    from PyQt5.QtGui import QPalette, QColor
    from PyQt5.QtCore import Qt
    
    palette = QPalette()
    
    # 窗口背景
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    
    # 按钮
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, QColor(25, 25, 25))
    palette.setColor(QPalette.ToolTipText, Qt.white)
    
    # 文本
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    
    # 链接
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    
    # 禁用状态
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    
    app.setPalette(palette)


if __name__ == "__main__":
    sys.exit(main())