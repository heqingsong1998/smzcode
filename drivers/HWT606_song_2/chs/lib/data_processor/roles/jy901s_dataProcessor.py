# coding:UTF-8
from ..interface.i_data_processor import IDataProcessor

"""
    JY901S数据处理器
"""


class JY901SDataProcessor(IDataProcessor):
    # 🔧 修复: 将类变量改为实例变量，避免多设备共享回调列表
    # onVarChanged = []  # 注释掉原有的类变量
    
    def __init__(self):
        """初始化实例变量"""
        self.onVarChanged = []
    
    def onOpen(self, deviceModel):
        pass

    def onClose(self):
        pass

    def onUpdate(self, *args):
        """触发回调（改为实例方法）"""
        for fun in self.onVarChanged:
            fun(*args)