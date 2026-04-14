import serial
import struct
import csv
import time
import threading
from datetime import datetime
from queue import Queue, Empty

# ==== 自己改这里 ====
SERIAL_PORT = "COM3"   # 串口号
BAUDRATE = 115200      # 默认 115200
CSV_FILE = "force_log.csv"
SAMPLE_FREQ = 200      # Hz，对应 AT+SMPF
# ====================

# ===== flush 策略（减少写盘抖动）=====
FLUSH_EVERY_N_ROWS = 50   # 每50行flush一次（可改成100）
FLUSH_EVERY_SEC = 0.5     # 或每0.5秒至少flush一次
# ====================================

# 队列容量：防止写线程慢时内存无限涨
QUEUE_MAXSIZE = 5000

# 串口独占锁：读线程/主线程（清零、停流等）共享
SER_LOCK = threading.RLock()

# 当前是否处于 GSD 流模式
STREAMING = threading.Event()


def send_cmd(ser, cmd, wait_reply=True, timeout_s=0.8):
    """
    给 M8128 发送一条 ASCII 命令（自动加 \r\n）
    wait_reply=True 时读取并返回一行回应（ACK+...$OK）
    """
    if not cmd.endswith("\r\n"):
        cmd += "\r\n"
    full_cmd = cmd.encode("ascii", errors="ignore")
    ser.write(full_cmd)

    if wait_reply:
        old_to = ser.timeout
        ser.timeout = timeout_s
        try:
            reply = ser.readline().decode(errors="ignore").strip()
        finally:
            ser.timeout = old_to
        return reply
    return ""


def start_gsd_stream(ser):
    """启动连续上传（持锁）"""
    with SER_LOCK:
        ser.reset_output_buffer()
        ser.reset_input_buffer()
        send_cmd(ser, "AT+GSD", wait_reply=False)
        STREAMING.set()


def stop_gsd_stream(ser):
    """停止连续上传（持锁）"""
    with SER_LOCK:
        ser.reset_output_buffer()
        ser.reset_input_buffer()
        rep = send_cmd(ser, "AT+GSD=STOP", wait_reply=True, timeout_s=1.2)
        STREAMING.clear()
        return rep


def zero_channels(ser, channels=None):
    """
    清零指定通道（线程安全）：
    channels:
      - None -> 全通道 [1,1,1,1,1,1]
      - 或者传 [1,0,0,0,0,0] 等
    """
    if channels is None:
        channels = [1, 1, 1, 1, 1, 1]
    if len(channels) != 6:
        raise ValueError("channels 必须是长度为6的列表，例如 [1,1,1,1,1,1]")

    # 1) 停流，避免数据流挤占 ACK
    was_streaming = STREAMING.is_set()
    if was_streaming:
        stop_gsd_stream(ser)

    # 2) 发清零命令并等回应（持锁）
    cmd = "AT+ADJZF=" + ";".join(map(str, channels))
    with SER_LOCK:
        ser.reset_output_buffer()
        ser.reset_input_buffer()
        rep = send_cmd(ser, cmd, wait_reply=True, timeout_s=1.2)

    # 3) 给设备一点处理时间
    time.sleep(0.2)

    # 4) 恢复流
    if was_streaming:
        start_gsd_stream(ser)

    return rep


def find_frame_header(ser):
    """在串口流中寻找帧头 0xAA 0x55，找到后返回 True"""
    while True:
        b = ser.read(1)
        if not b:
            return False
        if b == b"\xAA":
            b2 = ser.read(1)
            if not b2:
                return False
            if b2 == b"\x55":
                return True


def read_one_frame_blocking(ser):
    """
    阻塞按帧读取：
    - 找帧头
    - 读长度（2字节大端）
    - 读 payload（length字节）
    返回： (human_ts_str, raw_ts_ns, pkg_no, (Fx..Mz)) 或 None
    """
    if not find_frame_header(ser):
        return None

    # “帧头刚被读到”的高精度时间（更接近到达PC）
    raw_ts_ns = time.perf_counter_ns()

    length_bytes = ser.read(2)
    if len(length_bytes) < 2:
        return None
    length = (length_bytes[0] << 8) | length_bytes[1]

    payload = ser.read(length)
    if len(payload) < length:
        return None

    # 人类可读时间戳（到微秒，避免同一毫秒看起来一样）
    now = datetime.now()
    human_ts_str = f"{now:%Y-%m-%d %H:%M:%S}.{now.microsecond:06d}"

    pkg_no = (payload[0] << 8) | payload[1]
    data_bytes = payload[2:2 + 6 * 4]
    forces = struct.unpack("<6f", data_bytes)
    return human_ts_str, raw_ts_ns, pkg_no, forces


def reader_thread_fn(ser, q: Queue, stop_evt: threading.Event):
    """
    读线程：只负责读帧、打时间戳、入队
    同时打印 raw_ts_ns 的间隔，方便观察是否出现 >10ms 的“读间隔”
    """
    last_ns = None
    report_every = 50
    cnt = 0
    long_gap_cnt = 0

    while not stop_evt.is_set():
        # 串口访问必须持锁，保证清零/停流时不会竞争
        with SER_LOCK:
            frame = read_one_frame_blocking(ser)

        if frame is None:
            continue

        human_ts_str, raw_ts_ns, pkg_no, forces = frame

        # 统计读线程“帧间隔”（高精度）
        if last_ns is not None:
            dt_ms = (raw_ts_ns - last_ns) / 1e6
            if dt_ms > 10.0:
                long_gap_cnt += 1
        last_ns = raw_ts_ns
        cnt += 1

        # 入队（队列满了就阻塞等待，避免丢数据）
        q.put((human_ts_str, raw_ts_ns, pkg_no, forces))

        if cnt % report_every == 0:
            print(f"[READER] frames={cnt}, long_gap(>10ms)={long_gap_cnt}")

    print("[READER] stopped")


def writer_thread_fn(csv_path: str, q: Queue, stop_evt: threading.Event):
    """
    写线程：只负责从队列取数据写CSV
    flush 改成分批/定时，避免写盘拖慢读线程
    """
    rows_since_flush = 0
    last_flush_t = time.perf_counter()

    with open(csv_path, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "raw_timestamp_ns", "pkg_no", "Fx", "Fy", "Fz", "Mx", "My", "Mz"])
        f.flush()

        while True:
            # 若已请求停止：把队列剩余数据写完再退出
            if stop_evt.is_set():
                try:
                    item = q.get_nowait()
                except Empty:
                    break
            else:
                try:
                    item = q.get(timeout=0.2)
                except Empty:
                    # 定时flush一下
                    now = time.perf_counter()
                    if rows_since_flush > 0 and (now - last_flush_t) >= FLUSH_EVERY_SEC:
                        f.flush()
                        rows_since_flush = 0
                        last_flush_t = now
                    continue

            human_ts_str, raw_ts_ns, pkg_no, forces = item
            Fx, Fy, Fz, Mx, My, Mz = forces

            writer.writerow([human_ts_str, int(raw_ts_ns), int(pkg_no), Fx, Fy, Fz, Mx, My, Mz])
            rows_since_flush += 1

            now = time.perf_counter()
            if rows_since_flush >= FLUSH_EVERY_N_ROWS or (now - last_flush_t) >= FLUSH_EVERY_SEC:
                f.flush()
                rows_since_flush = 0
                last_flush_t = now

        f.flush()

    print("[WRITER] stopped")


def main():
    # Windows 键盘支持（Z清零 / Q退出）
    try:
        import msvcrt
        has_kbd = True
    except ImportError:
        msvcrt = None
        has_kbd = False
        print("⚠️ 非Windows系统：不支持 Z/Q 键盘控制（可用 Ctrl+C 退出）")

    q = Queue(maxsize=QUEUE_MAXSIZE)
    stop_evt = threading.Event()

    with serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1.0,
    ) as ser:

        print("配置采样率与校验方式...")
        with SER_LOCK:
            rep = send_cmd(ser, f"AT+SMPF={SAMPLE_FREQ}", wait_reply=True)
        if rep:
            print("RECV:", rep)

        with SER_LOCK:
            rep = send_cmd(ser, "AT+DCKMD=SUM", wait_reply=True)
        if rep:
            print("RECV:", rep)

        print("启动连续上传 AT+GSD ...")
        start_gsd_stream(ser)

        # 启动写线程
        wt = threading.Thread(target=writer_thread_fn, args=(CSV_FILE, q, stop_evt), daemon=True)
        wt.start()

        # 启动读线程
        rt = threading.Thread(target=reader_thread_fn, args=(ser, q, stop_evt), daemon=True)
        rt.start()

        print("开始接收数据（读写两线程）")
        if has_kbd:
            print("按 Z 清零（全通道），按 Q 退出；或 Ctrl+C 停止")
        else:
            print("按 Ctrl+C 停止")

        try:
            while True:
                if has_kbd and msvcrt.kbhit():
                    ch = msvcrt.getch()
                    if ch:
                        c = ch.decode(errors="ignore").lower()
                        if c == "z":
                            print("\n[ZERO] 清零中...")
                            rep = zero_channels(ser, channels=None)
                            if rep:
                                print("[ZERO] RECV:", rep)
                            print("[ZERO] 完成\n")
                        elif c == "q":
                            print("收到退出指令(Q)，准备退出程序")
                            break
                time.sleep(0.05)

        except KeyboardInterrupt:
            print("\n用户 Ctrl+C 中断，准备停止...")

        finally:
            stop_evt.set()

            print("停止数据流 AT+GSD=STOP ...")
            rep = stop_gsd_stream(ser)
            if rep:
                print("RECV:", rep)

            # 等线程把队列写完
            rt.join(timeout=2.0)
            wt.join(timeout=5.0)

    print("已保存到:", CSV_FILE)


if __name__ == "__main__":
    main()
