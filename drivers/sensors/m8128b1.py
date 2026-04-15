"""M8128B1 六轴力传感器驱动（支持 serial / ethernet 两种通信）"""

from __future__ import annotations

import socket
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


SixAxisSample = Tuple[float, float, float, float, float, float]
FrameRecord = Tuple[int, int, List[SixAxisSample]]  # (pkg_no, ts_ns, groups)


class M8128B1Sensor(SensorBase):
    HDR = b"\xAA\x55"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        self.transport = str(config.get("transport", "serial")).strip().lower()

        self.ser: Optional[serial.Serial] = None
        self.sock: Optional[socket.socket] = None

        self.io_lock = threading.RLock()

        max_queue_len = int(config.get("max_queue_len", 2000))
        self._rx_queue: deque[FrameRecord] = deque(maxlen=max_queue_len)
        self._rx_queue_lock = threading.Lock()

        self._rx_thread: Optional[threading.Thread] = None
        self._rx_running = False

        self._streaming = threading.Event()

        self._latest_lock = threading.Lock()
        self._latest_sample: Optional[Tuple[int, int, SixAxisSample]] = None

    # ------------------------------------------------------------------
    # 基础状态
    # ------------------------------------------------------------------

    def _is_open(self) -> bool:
        if self.transport == "serial":
            return self.ser is not None and self.ser.is_open
        return self.sock is not None

    def _target_desc(self) -> str:
        if self.transport == "serial":
            return str(self.config.get("port", "UNKNOWN"))
        ip = self.config.get("ip", "UNKNOWN")
        tcp_port = self.config.get("tcp_port", 4008)
        return f"{ip}:{tcp_port}"

    # ------------------------------------------------------------------
    # connect / disconnect
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            timeout = float(self.config.get("timeout", 1.0))

            if self.transport == "serial":
                self.ser = serial.Serial(
                    port=self.config["port"],
                    baudrate=int(self.config.get("baudrate", 115200)),
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=timeout,
                )
                print(f"✅ 传感器串口连接成功: {self.config['port']}")

            elif self.transport in ("ethernet", "tcp", "eth"):
                ip = str(self.config["ip"])
                tcp_port = int(self.config.get("tcp_port", 4008))
                self.sock = socket.create_connection((ip, tcp_port), timeout=timeout)
                self.sock.settimeout(timeout)
                print(f"✅ 传感器以太网连接成功: {ip}:{tcp_port}")

            else:
                raise ValueError(
                    f"不支持的 transport={self.transport!r}，只能是 serial 或 ethernet"
                )

            self.connected = True
            return True

        except Exception as e:
            self.connected = False
            print(f"❌ 传感器连接失败: {e}")
            return False

    def disconnect(self) -> bool:
        try:
            if self._is_open():
                try:
                    self.stop_stream()
                except Exception:
                    pass

            if self.ser is not None:
                try:
                    if self.ser.is_open:
                        self.ser.close()
                finally:
                    self.ser = None

            if self.sock is not None:
                try:
                    try:
                        self.sock.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                    self.sock.close()
                finally:
                    self.sock = None

            self.connected = False
            print("✅ 传感器已断开连接")
            return True

        except Exception as e:
            print(f"❌ 传感器断开失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 底层 IO
    # ------------------------------------------------------------------

    def _write_bytes(self, data: bytes) -> None:
        if self.transport == "serial":
            if not self.ser:
                raise RuntimeError("Serial not connected")
            self.ser.write(data)
            return

        if not self.sock:
            raise RuntimeError("Socket not connected")
        self.sock.sendall(data)

    def _read_bytes(self, n: int) -> bytes:
        if n <= 0:
            return b""

        if self.transport == "serial":
            if not self.ser:
                raise RuntimeError("Serial not connected")
            return self.ser.read(n)

        if not self.sock:
            raise RuntimeError("Socket not connected")

        try:
            return self.sock.recv(n)
        except socket.timeout:
            return b""

    def _readline_bytes(self, timeout: float = 1.2) -> bytes:
        if self.transport == "serial":
            if not self.ser:
                raise RuntimeError("Serial not connected")
            old_to = self.ser.timeout
            self.ser.timeout = timeout
            try:
                return self.ser.readline()
            finally:
                self.ser.timeout = old_to

        if not self.sock:
            raise RuntimeError("Socket not connected")

        old_to = self.sock.gettimeout()
        self.sock.settimeout(timeout)
        try:
            buf = bytearray()
            while True:
                try:
                    ch = self.sock.recv(1)
                except socket.timeout:
                    break
                if not ch:
                    break
                buf.extend(ch)
                if ch == b"\n":
                    break
            return bytes(buf)
        finally:
            self.sock.settimeout(old_to)

    def _drain_input(self) -> None:
        """尽量清空已有输入缓存。"""
        if self.transport == "serial":
            if self.ser:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            return

        if not self.sock:
            return

        old_to = self.sock.gettimeout()
        try:
            self.sock.settimeout(0.01)
            while True:
                try:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        break
                except socket.timeout:
                    break
                except BlockingIOError:
                    break
        finally:
            self.sock.settimeout(old_to)

    # ------------------------------------------------------------------
    # AT helpers
    # ------------------------------------------------------------------

    def _send_cmd(self, cmd: str) -> None:
        if not cmd.endswith("\r\n"):
            cmd += "\r\n"
        self._write_bytes(cmd.encode("ascii", errors="ignore"))

    def _read_ack(self, timeout: float = 1.2) -> str:
        return self._readline_bytes(timeout=timeout).decode(errors="ignore").strip()

    def _send_expect_ok(
        self,
        cmd: str,
        timeout: float = 1.2,
        *,
        allow_empty: bool = False,
    ) -> str:
        self._send_cmd(cmd)
        rep = self._read_ack(timeout=timeout)

        if rep:
            print(f"{cmd} -> {rep}")

        if not rep and not allow_empty:
            raise RuntimeError(f"{cmd} 无响应")

        if rep and "ERROR" in rep.upper():
            raise RuntimeError(f"{cmd} 返回 ERROR: {rep}")

        return rep

    # ------------------------------------------------------------------
    # configure / stream / zero
    # ------------------------------------------------------------------

    def configure(self) -> bool:
        try:
            if not self.connected or not self._is_open():
                print("❌ 传感器未连接")
                return False

            check_mode = str(self.config.get("check_mode", "SUM")).upper()
            sample_freq = int(self.config.get("sample_freq", 200))
            dnpch_set = self.config.get("dnpch_set")

            with self.io_lock:
                self._drain_input()
                self._send_expect_ok(f"AT+DCKMD={check_mode}", timeout=1.5)

                self._drain_input()
                self._send_expect_ok(f"AT+SMPF={sample_freq}", timeout=1.5)

                # 这条命令在手册公开指令表中没有单独列出，因此仅做可选尝试，不作为失败条件
                if dnpch_set is not None:
                    self._drain_input()
                    try:
                        self._send_expect_ok(f"AT+DNpCH={int(dnpch_set)}", timeout=1.5)
                    except Exception as e:
                        print(f"⚠️ DNpCH 设置未成功，已忽略: {e}")

            print("✅ 传感器配置完成")
            return True

        except Exception as e:
            print(f"❌ 传感器配置失败: {e}")
            return False

    def start_stream(self) -> bool:
        try:
            if not self.connected or not self._is_open():
                print("❌ 传感器未连接")
                return False

            self._stop_rx_thread()

            with self.io_lock:
                self._drain_input()
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
            if not self.connected or not self._is_open():
                return True

            self._stop_rx_thread()

            with self.io_lock:
                self._drain_input()
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
            if not self.connected or not self._is_open():
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
            with self.io_lock:
                self._drain_input()
                rep = self._send_expect_ok(cmd, timeout=1.5)
                if rep:
                    print("ZERO:", rep)

            # 手册要求至少等待 2 秒
            time.sleep(float(self.config.get("zero_settle_s", 2.0)))

            if was_streaming:
                self.start_stream()

            return True

        except Exception as e:
            print(f"❌ 清零失败: {e}")
            return False

    # ------------------------------------------------------------------
    # RX thread
    # ------------------------------------------------------------------

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
        while self._rx_running:
            b = self._read_bytes(1)
            if not b:
                continue
            if b == b"\xAA":
                b2 = self._read_bytes(1)
                if not b2:
                    continue
                if b2 == b"\x55":
                    return True
        return False

    def _read_exact(self, n: int, deadline: float) -> bytes:
        out = bytearray()
        while len(out) < n and self._rx_running and time.time() < deadline:
            chunk = self._read_bytes(n - len(out))
            if chunk:
                out.extend(chunk)
        return bytes(out)

    def _read_one_frame_blocking(self, timeout: float) -> Tuple[Optional[bytes], Optional[int]]:
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
        frame_timeout = float(self.config.get("frame_timeout", 0.5))

        while self._rx_running:
            try:
                with self.io_lock:
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

    # ------------------------------------------------------------------
    # frame parse
    # ------------------------------------------------------------------

    def _parse_frame(self, frame: bytes) -> Tuple[int, List[SixAxisSample]]:
        if len(frame) < 6:
            raise ValueError("帧长度过短")
        if frame[:2] != self.HDR:
            raise ValueError("帧头错误")

        length = struct.unpack(">H", frame[2:4])[0]
        if len(frame) < 4 + length:
            raise ValueError("帧长度不完整")

        payload = frame[4:4 + length]
        if len(payload) < 2:
            raise ValueError("payload 太短")

        pkg_no = struct.unpack(">H", payload[:2])[0]
        check_mode = str(self.config.get("check_mode", "SUM")).upper()

        if check_mode == "CRC32":
            if len(payload) < 2 + 4:
                raise ValueError("CRC32 payload 太短")
            body = payload[2:-4]
            recv_crc = struct.unpack("<I", payload[-4:])[0]
            calc_crc = zlib.crc32(body) & 0xFFFFFFFF
            if recv_crc != calc_crc:
                raise ValueError("CRC32 校验失败")
            data_bytes = body
        else:
            if len(payload) < 2 + 1:
                raise ValueError("SUM payload 太短")
            sum_byte = payload[-1]
            calc_sum = sum(payload[2:-1]) & 0xFF
            if sum_byte != calc_sum:
                raise ValueError("SUM 校验失败")
            data_bytes = payload[2:-1]

        group_size = 6 * 4
        if len(data_bytes) % group_size != 0:
            raise ValueError("数据长度不是 6*4 的整数倍")

        groups: List[SixAxisSample] = []
        for i in range(0, len(data_bytes), group_size):
            fx, fy, fz, mx, my, mz = struct.unpack("<6f", data_bytes[i:i + group_size])
            groups.append((fx, fy, fz, mx, my, mz))

        return int(pkg_no), groups

    # ------------------------------------------------------------------
    # public read
    # ------------------------------------------------------------------

    def read_data_with_timestamp(self) -> List[FrameRecord]:
        with self._rx_queue_lock:
            frames = list(self._rx_queue)
            self._rx_queue.clear()
        return frames

    def get_latest(self) -> Optional[Tuple[int, int, SixAxisSample]]:
        with self._latest_lock:
            return self._latest_sample