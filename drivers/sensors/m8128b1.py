"""M8128B1 六轴力传感器驱动（按帧阻塞读取版本）"""

from __future__ import annotations

import struct
import threading
import time
import zlib
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import serial

from .base import SensorBase

try:
    perf_counter_ns = time.perf_counter_ns
except AttributeError:  # pragma: no cover
    def perf_counter_ns() -> int:
        return int(time.perf_counter() * 1e9)


class M8128B1Sensor(SensorBase):
    HDR = b"\xAA\x55"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.ser: Optional[serial.Serial] = None

        self.ser_lock = threading.RLock()

        max_queue_len = int(config.get("max_queue_len", 2000))
        self._rx_queue = deque(maxlen=max_queue_len)  # (pkg_no, ts_ns, groups)
        self._rx_queue_lock = threading.Lock()

        self._rx_thread: Optional[threading.Thread] = None
        self._rx_running: bool = False

        self._streaming = threading.Event()

        self._latest_lock = threading.Lock()
        self._latest_sample: Optional[Tuple[int, int, Tuple[float, float, float, float, float, float]]] = None

    # ---------- connect/disconnect ----------

    def connect(self) -> bool:
        try:
            self.ser = serial.Serial(
                port=self.config["port"],
                baudrate=int(self.config.get("baudrate", 115200)),
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=float(self.config.get("timeout", 1.0)),
            )
            self.connected = True
            print(f"✅ 传感器连接成功: {self.config['port']}")
            return True
        except Exception as e:
            self.connected = False
            print(f"❌ 传感器连接失败: {e}")
            return False

    def disconnect(self) -> bool:
        try:
            if self.ser and self.ser.is_open:
                self.stop_stream()
                self.ser.close()
            self.connected = False
            print("✅ 传感器已断开连接")
            return True
        except Exception as e:
            print(f"❌ 传感器断开失败: {e}")
            return False

    # ---------- AT helpers ----------

    def _send_cmd(self, cmd: str) -> None:
        if not self.ser:
            raise RuntimeError("Serial not connected")
        if not cmd.endswith("\r\n"):
            cmd += "\r\n"
        self.ser.write(cmd.encode("ascii", errors="ignore"))

    def _read_ack(self, timeout: float = 1.2) -> str:
        if not self.ser:
            raise RuntimeError("Serial not connected")
        old_to = self.ser.timeout
        self.ser.timeout = timeout
        try:
            return self.ser.readline().decode(errors="ignore").strip()
        finally:
            self.ser.timeout = old_to

    # ---------- configure/stream ----------

    def configure(self) -> bool:
        try:
            if not self.connected or not self.ser:
                print("❌ 传感器未连接")
                return False

            check_mode = str(self.config.get("check_mode", "SUM")).upper()
            sample_freq = int(self.config.get("sample_freq", 200))
            dnpch_set = self.config.get("dnpch_set")

            with self.ser_lock:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self._send_cmd(f"AT+DCKMD={check_mode}")
                print("SET DCKMD:", self._read_ack())

                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self._send_cmd(f"AT+SMPF={sample_freq}")
                print("SET SMPF:", self._read_ack())

                if dnpch_set is not None:
                    self.ser.reset_input_buffer()
                    self.ser.reset_output_buffer()
                    self._send_cmd(f"AT+DNpCH={int(dnpch_set)}")
                    print("SET DNpCH:", self._read_ack())

            print("✅ 传感器配置完成")
            return True
        except Exception as e:
            print(f"❌ 传感器配置失败: {e}")
            return False

    def start_stream(self) -> bool:
        try:
            if not self.connected or not self.ser:
                print("❌ 传感器未连接")
                return False

            self._stop_rx_thread()

            with self.ser_lock:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self._send_cmd("AT+GSD")
                self._streaming.set()

            with self._rx_queue_lock:
                self._rx_queue.clear()
            with self._latest_lock:
                self._latest_sample = None

            self._start_rx_thread()
            print("✅ 数据流已开始")
            return True
        except Exception as e:
            print(f"❌ 开始数据流失败: {e}")
            return False

    def stop_stream(self) -> bool:
        try:
            if not self.connected or not self.ser:
                return True

            self._stop_rx_thread()

            with self.ser_lock:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self._send_cmd("AT+GSD=STOP")
                rep = self._read_ack(timeout=1.5)
                if rep:
                    print("STOP:", rep)
                self._streaming.clear()

            with self._rx_queue_lock:
                self._rx_queue.clear()
            return True
        except Exception as e:
            print(f"❌ 停止数据流失败: {e}")
            return False

    def zero_channels(self, channels: Optional[List[int]] = None) -> bool:
        try:
            if not self.connected or not self.ser:
                print("❌ 传感器未连接")
                return False

            if channels is None:
                channels = [1, 1, 1, 1, 1, 1]
            if len(channels) != 6:
                raise ValueError("channels 必须长度为6，例如 [1,1,1,1,1,1]")

            was_streaming = self._streaming.is_set()
            if was_streaming:
                self.stop_stream()

            cmd = "AT+ADJZF=" + ";".join(map(str, channels))
            with self.ser_lock:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self._send_cmd(cmd)
                rep = self._read_ack(timeout=1.5)
                if rep:
                    print("ZERO:", rep)

            time.sleep(float(self.config.get("zero_settle_s", 0.2)))

            if was_streaming:
                self.start_stream()
            return True
        except Exception as e:
            print(f"❌ 清零失败: {e}")
            return False

    # ---------- RX thread (blocking) ----------

    def _start_rx_thread(self) -> None:
        if self._rx_running:
            return
        self._rx_running = True
        self._rx_thread = threading.Thread(target=self._rx_worker, daemon=True)
        self._rx_thread.start()

    def _stop_rx_thread(self) -> None:
        self._rx_running = False
        t = self._rx_thread
        if t and t.is_alive():
            t.join(timeout=1.5)
        self._rx_thread = None

    def _find_frame_header(self) -> bool:
        assert self.ser is not None
        while self._rx_running:
            b = self.ser.read(1)
            if not b:
                continue
            if b == b"\xAA":
                b2 = self.ser.read(1)
                if not b2:
                    continue
                if b2 == b"\x55":
                    return True
        return False

    def _read_exact(self, n: int, deadline: float) -> bytes:
        assert self.ser is not None
        out = bytearray()
        while len(out) < n and self._rx_running and time.time() < deadline:
            chunk = self.ser.read(n - len(out))
            if chunk:
                out.extend(chunk)
        return bytes(out)

    def _read_one_frame_blocking(self, timeout: float) -> Tuple[Optional[bytes], Optional[int]]:
        assert self.ser is not None
        end_time = time.time() + timeout

        if not self._find_frame_header():
            return None, None

        ts_ns = perf_counter_ns()

        len_bytes = self._read_exact(2, deadline=end_time)
        if len(len_bytes) != 2:
            return None, None
        length = struct.unpack(">H", len_bytes)[0]

        payload = self._read_exact(length, deadline=end_time)
        if len(payload) != length:
            return None, None

        return self.HDR + len_bytes + payload, ts_ns

    def _rx_worker(self) -> None:
        assert self.ser is not None
        frame_timeout = float(self.config.get("frame_timeout", 0.5))

        while self._rx_running:
            try:
                with self.ser_lock:
                    frame, ts_ns = self._read_one_frame_blocking(timeout=frame_timeout)
                if not frame:
                    continue

                pkg_no, groups = self._parse_frame(frame)

                with self._rx_queue_lock:
                    self._rx_queue.append((int(pkg_no), int(ts_ns), groups))

                if groups:
                    with self._latest_lock:
                        self._latest_sample = (int(ts_ns), int(pkg_no), groups[-1])

            except Exception as e:
                print(f"[RX] 解析/接收异常: {e}")
                time.sleep(0.005)

    # ---------- parse ----------

    def _parse_frame(self, frame: bytes) -> Tuple[int, List[Tuple[float, float, float, float, float, float]]]:
        if len(frame) < 6:
            raise ValueError("帧长度过短")
        if frame[:2] != self.HDR:
            raise ValueError("帧头错误")

        length = struct.unpack(">H", frame[2:4])[0]
        if len(frame) < 4 + length:
            raise ValueError("帧长度不完整")

        payload = frame[4:4 + length]
        if len(payload) < 2:
            raise ValueError("payload太短")

        pkg_no = struct.unpack(">H", payload[:2])[0]
        check_mode = str(self.config.get("check_mode", "SUM")).upper()

        if check_mode == "CRC32":
            if len(payload) < 2 + 4:
                raise ValueError("CRC32 payload太短")
            body = payload[2:-4]
            recv_crc = struct.unpack("<I", payload[-4:])[0]
            calc_crc = zlib.crc32(body) & 0xFFFFFFFF
            if recv_crc != calc_crc:
                raise ValueError("CRC32校验失败")
            data_bytes = body
        else:
            if len(payload) < 2 + 1:
                raise ValueError("SUM payload太短")
            sum_byte = payload[-1]
            calc_sum = (sum(payload[2:-1]) & 0xFF)
            if sum_byte != calc_sum:
                raise ValueError("SUM校验失败")
            data_bytes = payload[2:-1]

        group_size = 6 * 4
        if len(data_bytes) % group_size != 0:
            raise ValueError("数据长度不是 6*4 的整数倍")

        groups: List[Tuple[float, float, float, float, float, float]] = []
        for i in range(0, len(data_bytes), group_size):
            fx, fy, fz, mx, my, mz = struct.unpack("<6f", data_bytes[i:i + group_size])
            groups.append((fx, fy, fz, mx, my, mz))

        return int(pkg_no), groups

    # ---------- public read ----------

    def read_data_with_timestamp(self) -> List[Tuple[int, int, List[Tuple[float, float, float, float, float, float]]]]:
        with self._rx_queue_lock:
            frames = list(self._rx_queue)
            self._rx_queue.clear()
        return frames

    def get_latest(self) -> Optional[Tuple[int, int, Tuple[float, float, float, float, float, float]]]:
        with self._latest_lock:
            return self._latest_sample
