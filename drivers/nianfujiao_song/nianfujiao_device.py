"""
粘附脚传感器设备主类

当前支持两种上行数据帧：
- style0: 5A 30 00 80 00 01 23 + 24 * int16 + A5
- style24: 5A 30 00 80 00 01 24 + 16 * int16 + A5
"""
import struct
import time
import threading
from typing import Optional

import serial

from .base import NianFuJiaoBase, Style0Data, Style24Data
from .utils import (
    CsvWriter,
    get_style0_headers,
    get_style24_headers,
    send_init_sequence,
    send_control_command,
    send_custom_command,
    format_style0_data,
    format_style24_data,
    STYLE0_HEADER, STYLE0_TAIL, STYLE0_PAYLOAD_LEN, STYLE0_TOTAL_LEN,
    STYLE24_HEADER, STYLE24_PAYLOAD_LEN, STYLE24_TOTAL_LEN,
    CONTROL_COMMANDS,
    # 标定函数
    cal_Fx1, cal_Fy1, cal_Fz1_plus, cal_Mx1, cal_My1,
    cal_Fx2, cal_Fy2, cal_Fz2_plus, cal_Mx2, cal_My2,
    cal_FZ1_minus, cal_FZ2_minus,
)


class NianFuJiaoDevice(NianFuJiaoBase):
    """粘附脚传感器设备类"""

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        enable_csv: bool = True,
        print_data: bool = True,
        enable_calibration: bool = True,
    ):
        """
        初始化粘附脚设备

        Args:
            port: 串口号
            baud: 波特率
            enable_csv: 是否启用CSV记录
            print_data: 是否打印数据
            enable_calibration: 是否启用标定计算
        """
        super().__init__(port, baud)
        self.enable_csv = enable_csv
        self.print_data = print_data
        self.enable_calibration = enable_calibration

        # CSV 写入器
        self.csv0: Optional[CsvWriter] = None
        self.csv24: Optional[CsvWriter] = None

        # 接收缓冲区
        self.rx_buf = bytearray()

        # 读取线程
        self._read_thread: Optional[threading.Thread] = None
        self._stop_flag = False

    # ========= 串口控制 =========
    def open(self):
        """打开设备"""
        if self._is_open:
            print(f"[WARN] 设备已经打开: {self.port}")
            return

        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=0.1,
            )
            self._is_open = True
            print(f"[INFO] 串口已打开: {self.port} @ {self.baud}")

            # 初始化 CSV 写入器
            if self.enable_csv:
                self._init_csv_writers()

            # 发送初始化帧
            self.send_init_frames()

            # 启动读取线程
            self._start_read_thread()

        except Exception as e:
            print(f"[ERROR] 打开串口失败: {e}")
            self._is_open = False

    def close(self):
        """关闭设备"""
        self._stop_flag = True
        # 停止读取线程
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=1.0)
        self._read_thread = None

        # 关闭串口
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.serial_conn = None
        self._is_open = False

        # 关闭 CSV
        if self.csv0:
            self.csv0.close()
            self.csv0 = None
        if self.csv24:
            self.csv24.close()
            self.csv24 = None

        print("[INFO] 设备已关闭")

    def _init_csv_writers(self):
        """初始化 CSV 写入器"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.csv0 = CsvWriter(f"style0_{timestamp}.csv", get_style0_headers())
        self.csv24 = CsvWriter(f"style24_{timestamp}.csv", get_style24_headers())

    def _start_read_thread(self):
        """启动读取线程"""
        self._stop_flag = False
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()

    def _read_loop(self):
        """读取线程主循环：阻塞读，按设备发送节奏消费"""
        if not self.serial_conn:
            print("[ERROR] 串口未打开，无法读取数据")
            return

        # 允许较短的 style24 先被读取进缓冲区，style0 留待后续补齐。
        min_chunk = min(STYLE0_TOTAL_LEN, STYLE24_TOTAL_LEN)
        while not self._stop_flag:
            try:
                # 阻塞读取：若有缓存则多读，否则至少读一帧长度
                to_read = self.serial_conn.in_waiting or min_chunk
                chunk = self.serial_conn.read(to_read)
                if chunk:
                    self.rx_buf.extend(chunk)
                    self._consume_buffer()
            except Exception as e:
                print(f"[ERROR] 串口读取异常: {e}")
                time.sleep(0.1)


    def _consume_buffer(self):
        """消费缓冲区数据，解析 style0 / style24 两种帧"""
        header_len = len(STYLE0_HEADER)

        while len(self.rx_buf) >= header_len:
            if self.rx_buf.startswith(STYLE0_HEADER):
                if len(self.rx_buf) < STYLE0_TOTAL_LEN:
                    return
                if self._try_parse_style0():
                    continue
                del self.rx_buf[0]
                continue

            if self.rx_buf.startswith(STYLE24_HEADER):
                if len(self.rx_buf) < STYLE24_TOTAL_LEN:
                    return
                if self._try_parse_style24():
                    continue
                del self.rx_buf[0]
                continue

            # 不是任何已知帧头，丢弃1字节继续找齐。
            del self.rx_buf[0]

    def _try_parse_style0(self) -> bool:
        """尝试解析样式0数据帧"""
        buf = self.rx_buf
        if not buf.startswith(STYLE0_HEADER):
            return False
        if len(buf) < STYLE0_TOTAL_LEN:
            return False
        if buf[STYLE0_TOTAL_LEN - 1] != STYLE0_TAIL:
            return False

        payload = buf[len(STYLE0_HEADER) : len(STYLE0_HEADER) + STYLE0_PAYLOAD_LEN]
        fields = struct.unpack("<24h", payload)  # 24个int16小端

        # 映射到数据结构（24字段）
        data = Style0Data(
            Fx1=fields[0],
            Fy1=fields[1],
            Fz1_plus=fields[2],
            Mx1=fields[3],
            My1=fields[4],
            JJJ1_1=fields[5],
            JJJ1_2=fields[6],
            Fx2=fields[7],
            Fy2=fields[8],
            Fz2_plus=fields[9],
            Mx2=fields[10],
            My2=fields[11],
            flag1=fields[12],
            flag2=fields[13],
            FZ1_minus=fields[14],
            FZ2_minus=fields[15],
            flag_fz=fields[16],
            flag_fx=fields[17],
            flag_d=fields[18],
            reserved_1=fields[19],
            reserved_2=fields[20],
            reserved_3=fields[21],
            reserved_4=fields[22],
            reserved_5=fields[23],
        )

        # 计算标定值
        if self.enable_calibration:
            cal_values = [
                cal_Fx1(data.Fx1),
                cal_Fy1(data.Fy1),
                cal_Fz1_plus(data.Fz1_plus),
                cal_Mx1(data.Mx1),
                cal_My1(data.My1),
                data.JJJ1_1,
                data.JJJ1_2,
                cal_Fx2(data.Fx2),
                cal_Fy2(data.Fy2),
                cal_Fz2_plus(data.Fz2_plus),
                cal_Mx2(data.Mx2),
                cal_My2(data.My2),
                data.flag1,
                data.flag2,
                cal_FZ1_minus(data.FZ1_minus),
                cal_FZ2_minus(data.FZ2_minus),
                data.flag_fz,
                data.flag_fx,
                data.flag_d,
                data.reserved_1,
                data.reserved_2,
                data.reserved_3,
                data.reserved_4,
                data.reserved_5,
            ]
        else:
            cal_values = [0.0] * 24

        # 写入 CSV（原始值 + 标定值）
        if self.csv0:
            row_data = list(fields) + cal_values
            self.csv0.write_row(row_data)

        # 打印数据
        if self.print_data:
            # print(f"[STYLE0] {format_style0_data(data)}")
            if self.enable_calibration:
                # 需要的话，这里可以打印标定值
                pass

        # 通知回调
        self._notify_callbacks("style0", data)

        # 丢弃已解析的数据
        del self.rx_buf[:STYLE0_TOTAL_LEN]
        return True

    def _try_parse_style24(self) -> bool:
        """尝试解析样式24数据帧"""
        buf = self.rx_buf
        if not buf.startswith(STYLE24_HEADER):
            return False
        if len(buf) < STYLE24_TOTAL_LEN:
            return False
        if buf[STYLE24_TOTAL_LEN - 1] != STYLE0_TAIL:
            return False

        payload = buf[len(STYLE24_HEADER): len(STYLE24_HEADER) + STYLE24_PAYLOAD_LEN]
        fields = struct.unpack("<16h", payload)

        data = Style24Data(
            F11=fields[0],
            F12=fields[1],
            F13=fields[2],
            F14=fields[3],
            F21=fields[4],
            F22=fields[5],
            F23=fields[6],
            F24=fields[7],
            reserved_1=fields[8],
            reserved_2=fields[9],
            reserved_3=fields[10],
            reserved_4=fields[11],
            reserved_5=fields[12],
            reserved_6=fields[13],
            reserved_7=fields[14],
            reserved_8=fields[15],
        )

        if self.csv24:
            self.csv24.write_row(list(fields))

        if self.print_data:
            # print(f"[STYLE24] {format_style24_data(data)}")
            pass

        self._notify_callbacks("style24", data)

        del self.rx_buf[:STYLE24_TOTAL_LEN]
        return True

    # ========= 初始化与控制指令 =========
    def send_init_frames(self):
        """发送初始化帧"""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("[WARN] 串口未打开，无法发送初始化帧")
            return
        send_init_sequence(self.serial_conn)

    def send_reply(self) -> bool:
        """发送回复指令"""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("[WARN] 串口未打开，无法发送回复指令")
            return False
        return send_control_command(self.serial_conn, "reply")

    def send_engage(self) -> bool:
        """发送吸合指令"""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("[WARN] 串口未打开，无法发送吸合指令")
            return False
        return send_control_command(self.serial_conn, "engage")

    def send_zero(self) -> bool:
        """发送清零指令"""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("[WARN] 串口未打开，无法发送清零指令")
            return False
        return send_control_command(self.serial_conn, "zero")

    # ========= 其他辅助接口 =========
    def list_available_commands(self):
        """列出可用的控制指令名称"""
        return list(CONTROL_COMMANDS.keys())

    def send_command(self, name: str) -> bool:
        """按名称发送控制指令"""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("[WARN] 串口未打开，无法发送指令")
            return False
        return send_control_command(self.serial_conn, name)

    def send_custom(self, frame: bytes, delay: float = 0.01) -> bool:
        """发送自定义完整帧"""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("[WARN] 串口未打开，无法发送自定义指令")
            return False
        return send_custom_command(self.serial_conn, frame, delay)
