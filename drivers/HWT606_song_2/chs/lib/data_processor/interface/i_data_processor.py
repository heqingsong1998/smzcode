# coding:UTF-8
from abc import abstractmethod, ABCMeta


class IDataProcessor(metaclass=ABCMeta):
    """
    数据处理器接口类
    :param metaclass:
    :return:
    """
    # 🔧 修复: onVarChanged 应该在子类的 __init__ 中初始化为实例变量
    # onVarChanged = []  # 注释掉类变量

    @abstractmethod
    def onOpen(self, deviceModel):
        pass

    @abstractmethod
    def onClose(self):
        pass

    @abstractmethod
    def onUpdate(self, *args):
        """触发回调（应该是实例方法）"""
        pass