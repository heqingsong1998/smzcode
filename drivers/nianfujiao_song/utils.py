"""
粘附脚传感器工具函数

协议更新（新版样式0）：
- 帧头由 5A 20 00 80 00 01 23 更新为 5A 30 00 80 00 01 23
- payload 由 16 个 int16 扩展为 24 个 int16
- 在原 16 个字段后新增：
  flag_fz / flag_fx / flag_d / reserved_1..reserved_5
"""
import csv
import time
from datetime import datetime
from typing import List, Optional

# ========== 帧格式定义：仅样式0 ==========

# 样式0（新版）：
# 5A 30 00 80 00 01 23 + 48字节 payload(24*int16 LE) + A5
STYLE0_HEADER = bytes.fromhex("5A 30 00 80 00 01 23")
STYLE0_TAIL = 0xA5
STYLE0_PAYLOAD_LEN = 48
STYLE0_TOTAL_LEN = len(STYLE0_HEADER) + STYLE0_PAYLOAD_LEN + 1


# ========== 初始化数据帧 ==========
INIT_FRAME_1 = bytes.fromhex(
    "49 3B 42 57 00 00 03 00 00 00 00 00 00 00 00 00 00 00 00 00 45 2E"
)
INIT_FRAME_2 = bytes.fromhex(
    "49 3B 44 57 01 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 45 2E"
)
INIT_GAP_SEC = 0.005


# ========== 控制指令数据帧 ==========
# 三条固定帧，直接原样发送
CTRL_REPLY  = bytes.fromhex("5A 08 04 00 00 FF FE A5 00 00 00 00 00 00 B7 A5")  # 回复
CTRL_ENGAGE = bytes.fromhex("5A 08 04 00 00 FF FE A4 01 00 00 00 00 00 B7 A5")  # 吸合
CTRL_ZERO   = bytes.fromhex("5A 08 04 00 00 FF FE A4 02 01 00 00 00 00 B7 A5")  # 清零

# 控制指令字典
CONTROL_COMMANDS = {
    "reply": CTRL_REPLY,    # 回复
    "engage": CTRL_ENGAGE,  # 吸合
    "zero": CTRL_ZERO,      # 清零
}


def send_control_command(serial_conn, command_name: str, delay: float = 0.01) -> bool:
    """
    发送控制指令

    Args:
        serial_conn: 串口连接对象
        command_name: 指令名称 ('reply', 'engage', 'zero')
        delay: 发送后延迟时间（秒）

    Returns:
        是否发送成功
    """
    if command_name not in CONTROL_COMMANDS:
        print(f"[ERROR] 未知的指令名称: {command_name}")
        print(f"[INFO] 可用指令: {list(CONTROL_COMMANDS.keys())}")
        return False

    try:
        command_frame = CONTROL_COMMANDS[command_name]
        serial_conn.write(command_frame)
        serial_conn.flush()
        time.sleep(delay)
        print(f"[CTRL] 已发送控制指令: {command_name}")
        return True
    except Exception as e:
        print(f"[ERROR] 发送控制指令失败: {e}")
        return False


def send_custom_command(serial_conn, command_bytes: bytes, delay: float = 0.01) -> bool:
    """
    发送自定义控制指令

    Args:
        serial_conn: 串口连接对象
        command_bytes: 自定义指令的完整帧数据
        delay: 发送后延迟时间（秒）

    Returns:
        是否发送成功
    """
    try:
        serial_conn.write(command_bytes)
        serial_conn.flush()
        time.sleep(delay)
        print(f"[CTRL] 已发送自定义指令: {command_bytes.hex()}")
        return True
    except Exception as e:
        print(f"[ERROR] 发送自定义指令失败: {e}")
        return False


def send_init_sequence(serial_conn, gap_sec: float = INIT_GAP_SEC):
    """
    发送初始化序列：INIT_FRAME_1 -> 延时 -> INIT_FRAME_2

    Args:
        serial_conn: 串口连接对象
        gap_sec: 两帧之间的间隔时间（秒）
    """
    try:
        serial_conn.write(INIT_FRAME_1)
        time.sleep(gap_sec)
        serial_conn.write(INIT_FRAME_2)
        print("[INFO] 初始化帧已发送")
    except Exception as e:
        print(f"[ERROR] 发送初始化帧失败: {e}")


# ========== CSV 写入工具 ==========
class CsvWriter:
    """CSV 文件写入器"""

    def __init__(self, filename: str, headers: List[str]):
        self.filename = filename
        self.file = open(filename, "w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)
        self.writer.writerow(["timestamp"] + headers)
        print(f"[INFO] CSV 文件已创建: {filename}")

    def write_row(self, data: List):
        """写入一行数据，自动添加时间戳"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.writer.writerow([timestamp] + data)
        self.file.flush()

    def close(self):
        """关闭文件"""
        if self.file:
            self.file.close()
            print(f"[INFO] CSV 文件已关闭: {self.filename}")


# ========== CSV 表头 & 打印格式 ==========
def get_style0_headers() -> List[str]:
    """获取样式0的CSV表头（原始 + 标定值，24字段版）"""
    return [
        # 原始值
        "Fx1_raw", "Fy1_raw", "Fz1p_raw", "Mx1_raw", "My1_raw",
        "JJJ1_1_raw", "JJJ1_2_raw",
        "Fx2_raw", "Fy2_raw", "Fz2p_raw", "Mx2_raw", "My2_raw",
        "flag1_raw", "flag2_raw",
        "FZ1m_raw", "FZ2m_raw",
        "flag_fz_raw", "flag_fx_raw", "flag_d_raw",
        "reserved_1_raw", "reserved_2_raw", "reserved_3_raw", "reserved_4_raw", "reserved_5_raw",
        # 标定值
        "Fx1_cal", "Fy1_cal", "Fz1p_cal", "Mx1_cal", "My1_cal",
        "JJJ1_1_cal", "JJJ1_2_cal",
        "Fx2_cal", "Fy2_cal", "Fz2p_cal", "Mx2_cal", "My2_cal",
        "flag1_cal", "flag2_cal",
        "FZ1m_cal", "FZ2m_cal",
        "flag_fz_cal", "flag_fx_cal", "flag_d_cal",
        "reserved_1_cal", "reserved_2_cal", "reserved_3_cal", "reserved_4_cal", "reserved_5_cal",
    ]


def format_style0_data(data) -> str:
    """格式化样式0数据为字符串，便于调试打印"""
    return (
        f"Fx1={data.Fx1}, Fy1={data.Fy1}, Fz1+={data.Fz1_plus}, "
        f"Mx1={data.Mx1}, My1={data.My1}, "
        f"JJJ1_1={data.JJJ1_1}, JJJ1_2={data.JJJ1_2}, "
        f"Fx2={data.Fx2}, Fy2={data.Fy2}, Fz2+={data.Fz2_plus}, "
        f"Mx2={data.Mx2}, My2={data.My2}, "
        f"flag1={data.flag1}, flag2={data.flag2}, "
        f"Fz1-={data.FZ1_minus}, Fz2-={data.FZ2_minus}, "
        f"flag_fz={data.flag_fz}, flag_fx={data.flag_fx}, flag_d={data.flag_d}, "
        f"reserved=[{data.reserved_1}, {data.reserved_2}, {data.reserved_3}, {data.reserved_4}, {data.reserved_5}]"
    )


# ========== 标定计算函数 ==========
G = 9.8


def _poly(x: float, a: float, b: float, c: float) -> float:
    """多项式计算"""
    return a * x * x + b * x + c


def cal_Fx1(x: int) -> float:
    return round(_poly(x, 0.0000001464, 0.05789041, 1.7991) / 1000 * G*1.6, 4)


def cal_Fy1(x: int) -> float:
    return round(_poly(x, -0.0000015747, 0.08609779, 2.8957) / 1000 * G*1.6, 4)


def cal_Fz1_plus(x: int) -> float:
    if x >= 0:
        val = _poly(x, -0.000000096, 0.08767915, -0.0009) / 1000 * G*1.6
        return round(val, 4)
    return 0.0


def cal_Mx1(x: int) -> float:
    return round(_poly(x, 0.0000001160, 0.03678694, 0.2097) / 1000 * G / 20, 6)


def cal_My1(x: int) -> float:
    return round(_poly(x, 0.0000000466, 0.03477110, 1.2000) / 1000 * G / 20, 6)


def cal_Fx2(x: int) -> float:
    return round(_poly(x, 0.0000001918, 0.05750523, 1.6368) / 1000 * G*1.6, 4)


def cal_Fy2(x: int) -> float:
    return round(_poly(x, 0.0000001744, 0.07878799, 1.6326) / 1000 * G*1.6, 4)


def cal_Fz2_plus(x: int) -> float:
    if x >= 0:
        val = _poly(x, -0.0000001056, 0.08153554, 1.2464) / 1000 * G*1.6
        return round(val, 4)
    return 0.0


def cal_Mx2(x: int) -> float:
    return round(_poly(x, 0.0000001160, 0.03678694, 0.2097) / 1000 * G / 20, 6)


def cal_My2(x: int) -> float:
    return round(_poly(x, 0.0000000466, 0.03477110, 1.2000) / 1000 * G / 20, 6)




def cal_FZ1_minus(x: int) -> float:
    if x >= 0:
        return 0.0
    val = _poly(x, -0.000000999, 0.093632, 1.4201) / 1000 * G*1.6
    return round(val, 4)


def cal_FZ2_minus(x: int) -> float:
    if x >= 0:
        return 0.0
    val = _poly(x, 0.0000002093, 0.07912105, 0.7914) / 1000 * G*1.6
    return round(val, 4)
