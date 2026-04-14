"""M8128B1 six-axis force sensor driver.

Key design goals (based on your verified 'minimal correct script'):
- RX thread uses *blocking, frame-by-frame* reading (AA55 + LEN + payload).
- Serial access is protected by a single re-entrant lock shared by RX and control commands.
- A frame timestamp (perf_counter_ns) is captured *right after reading the header*,
  approximating 'frame arrival on PC' in a stable way.
- Write-to-disk is not part of this driver; the application layer should consume
  read_data_with_timestamp() and do logging in its own thread.
"""

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
    perf_counter_ns = time.perf_counter_ns  # py3.7+
except AttributeError:  # pragma: no cover
    def perf_counter_ns() -> int:
        return int(time.perf_counter() * 1e9)


class M8128B1Sensor(SensorBase):
    HDR = b"\xAA\x55"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.ser: Optional[serial.Serial] = None

        # One lock to rule them all: RX reading + control commands
        self.ser_lock = threading.RLock()

        # RX thread + queue
        max_queue_len = int(config.get("max_queue_len", 2000))
        self._rx_queue = deque(maxlen=max_queue_len)  # (pkg_no, frame_ts_ns, groups)
        self._rx_queue_lock = threading.Lock()
        self._rx_thread: Optional[threading.Thread] = None
        self._rx_running: bool = False

        # latest sample cache: (frame_ts_ns, pkg_no, (Fx..Mz))
        self._latest_lock = threading.Lock()
        self._latest_sample: Optional[Tuple[int, int, Tuple[float, float, float, float, float, float]]] = None

        # streaming flag
        self._streaming = threading.Event()

    # -------------------- Connection --------------------

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
            print(f"❌ 传感器连接失败: {e}")
            self.connected = False
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

    # -------------------- AT command helpers --------------------

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

    # -------------------- Configure / Stream control --------------------

    def configure(self) -> bool:
        """Configure checksum mode + sampling frequency (and optional DNpCH)."""
        try:
            if not self.connected or not self.ser:
                print("❌ 传感器未连接")
                return False

            check_mode = str(self.config.get("check_mode", "SUM")).upper()  # SUM or CRC32
            sample_freq = int(self.config.get("sample_freq", 200))
            dnpch_set = self.config.get("dnpch_set")  # optional

            with self.ser_lock:
                # checksum mode
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self._send_cmd(f"AT+DCKMD={check_mode}")
                print("SET DCKMD:", self._read_ack())

                # sampling frequency
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
        """Send AT+GSD and start RX thread (blocking frame read)."""
        try:
            if not self.connected or not self.ser:
                print("❌ 传感器未连接")
                return False

            # stop old thread if any
            self._stop_rx_thread()

            with self.ser_lock:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self._send_cmd("AT+GSD")
                # not waiting ACK; device may stream immediately
                self._streaming.set()

            # clear queues
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
        """Stop RX thread then send AT+GSD=STOP (lock protected)."""
        try:
            if not self.connected or not self.ser:
                return True

            # Stop thread first to avoid serial contention
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
        """Thread-safe zeroing.

        Implementation mirrors the verified 'minimal correct script':
        - Stop stream (so ACK won't be drowned by binary frames)
        - Send AT+ADJZF=... and wait reply
        - Sleep a bit
        - Restart stream
        """
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

    # -------------------- RX thread (blocking frame read) --------------------

    def _start_rx_thread(self) -> None:
        if self._rx_running:
            return
        self._rx_running = True
        self._rx_thread = threading.Thread(target=self._rx_worker, daemon=True)
        self._rx_thread.start()
        # print("✅ RX线程已启动")

    def _stop_rx_thread(self) -> None:
        self._rx_running = False
        t = self._rx_thread
        if t and t.is_alive():
            t.join(timeout=1.5)
        self._rx_thread = None

    def _find_frame_header(self) -> bool:
        """Blocking search for HDR (AA55). Must be called under ser_lock."""
        assert self.ser is not None
        while self._rx_running:
            b = self.ser.read(1)
            if not b:
                # timeout; allow loop to check _rx_running
                continue
            if b == b"\xAA":
                b2 = self.ser.read(1)
                if not b2:
                    continue
                if b2 == b"\x55":
                    return True
        return False

    def _read_exact(self, n: int, deadline: float) -> bytes:
        """Read exactly n bytes before deadline (time.time seconds). Under ser_lock."""
        assert self.ser is not None
        out = bytearray()
        while len(out) < n and self._rx_running and time.time() < deadline:
            chunk = self.ser.read(n - len(out))
            if chunk:
                out.extend(chunk)
        return bytes(out)

    def _read_one_frame_blocking(self, timeout: float) -> Tuple[Optional[bytes], Optional[int]]:
        """Read one frame: HDR + LEN(2) + PAYLOAD(length). Returns (frame_bytes, ts_ns)."""
        assert self.ser is not None
        end_time = time.time() + timeout

        if not self._find_frame_header():
            return None, None

        # Timestamp at header time
        ts_ns = perf_counter_ns()

        # LEN (big-endian)
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
                    self._rx_queue.append((pkg_no, int(ts_ns), groups))

                # update latest sample (last group)
                if groups:
                    with self._latest_lock:
                        self._latest_sample = (int(ts_ns), int(pkg_no), groups[-1])

            except Exception as e:
                # If parsing fails, just continue to re-sync to next header
                print(f"[RX] 解析/接收异常: {e}")
                time.sleep(0.005)

        # print("✅ RX线程已退出")

    # -------------------- Frame parsing --------------------

    def _parse_frame(self, frame: bytes) -> Tuple[int, List[Tuple[float, float, float, float, float, float]]]:
        """Parse one full frame (HDR+LEN+PAYLOAD).

        Frame format (per manual):
          HDR(2) + LEN(2, big-endian) + PAYLOAD(length)
        PAYLOAD:
          pkg_no(2, big-endian) + data_bytes + check(SUM=1 byte / CRC32=4 bytes)
        data_bytes:
          groups of 6 float32 little-endian
        """
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
            # SUM
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

    # -------------------- Public data access --------------------

    def read_data_with_timestamp(self) -> List[Tuple[int, int, List[Tuple[float, float, float, float, float, float]]]]:
        with self._rx_queue_lock:
            frames = list(self._rx_queue)
            self._rx_queue.clear()
        return frames

    def get_latest(self) -> Optional[Tuple[int, int, Tuple[float, float, float, float, float, float]]]:
        with self._latest_lock:
            return self._latest_sample
