"""传感器基类定义"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple, Optional


class SensorBase(ABC):
    """传感器抽象基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connected: bool = False

    @abstractmethod
    def connect(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def configure(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def start_stream(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stop_stream(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def zero_channels(self, channels: Optional[List[int]] = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def read_data_with_timestamp(
        self,
    ) -> List[Tuple[int, int, List[Tuple[float, float, float, float, float, float]]]]:
        """读取帧队列并清空：[(pkg_no, frame_ts_ns, groups), ...]"""
        raise NotImplementedError

    def read_data(self) -> List[Tuple[int, List[Tuple[float, float, float, float, float, float]]]]:
        frames = self.read_data_with_timestamp()
        return [(pkg_no, groups) for (pkg_no, _ts, groups) in frames]
