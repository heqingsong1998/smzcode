"""Sensor base class (abstract)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple, Optional


class SensorBase(ABC):
    """Abstract base class for sensors."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connected: bool = False

    @abstractmethod
    def connect(self) -> bool:
        """Open physical connection (e.g., serial)."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> bool:
        """Close connection and stop streaming."""
        raise NotImplementedError

    @abstractmethod
    def configure(self) -> bool:
        """Configure sensor parameters (sampling rate, checksum, etc.)."""
        raise NotImplementedError

    @abstractmethod
    def start_stream(self) -> bool:
        """Start continuous streaming."""
        raise NotImplementedError

    @abstractmethod
    def stop_stream(self) -> bool:
        """Stop continuous streaming."""
        raise NotImplementedError

    @abstractmethod
    def zero_channels(self, channels: Optional[List[int]] = None) -> bool:
        """Zero specified channels; None means all channels."""
        raise NotImplementedError

    @abstractmethod
    def read_data_with_timestamp(self) -> List[Tuple[int, int, List[Tuple[float, float, float, float, float, float]]]]:
        """Return queued frames: [(pkg_no, frame_ts_ns, groups), ...] and clear internal queue."""
        raise NotImplementedError

    def read_data(self) -> List[Tuple[int, List[Tuple[float, float, float, float, float, float]]]]:
        """Convenience: drop timestamp."""
        frames = self.read_data_with_timestamp()
        return [(pkg_no, groups) for (pkg_no, _ts, groups) in frames]
