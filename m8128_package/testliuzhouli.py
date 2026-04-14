"""Application layer test: use M8128B1 driver to log data.

- One thread consumes sensor frames and writes CSV (batch flush).
- Main thread handles keyboard: Z to zero, Q to quit (Windows), Ctrl+C to quit.
"""
from __future__ import annotations

import csv
import os
import time
import threading
from datetime import datetime
from queue import Queue, Empty

from utils import create_sensor, initialize_sensor

# ================== USER CONFIG ==================
SENSOR_CONFIG = {
    "type": "m8128b1",
    "port": "COM3",
    "baudrate": 115200,
    "timeout": 1.0,
    "check_mode": "SUM",     # SUM or CRC32 (must match device setting)
    "sample_freq": 200,      # Hz
    # "dnpch_set": 1,         # optional
    "frame_timeout": 0.5,
    "max_queue_len": 2000,
    "zero_settle_s": 0.2,
}

OUT_DIR = "data"
FLUSH_EVERY_N_ROWS = 50
FLUSH_EVERY_SEC = 0.5
# ================================================


def make_timestamp_str_us() -> str:
    now = datetime.now()
    return f"{now:%Y-%m-%d %H:%M:%S}.{now.microsecond:06d}"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(OUT_DIR, f"m8128_frame_by_frame_{ts}.csv")

    # keyboard (Windows)
    try:
        import msvcrt
        has_kbd = True
    except ImportError:
        msvcrt = None
        has_kbd = False
        print("⚠️ 非Windows系统：不支持 Z/Q 键盘控制（可用 Ctrl+C 退出）")

    sensor = create_sensor(SENSOR_CONFIG["type"], SENSOR_CONFIG)

    if not initialize_sensor(sensor, auto_config=True):
        return

    if not sensor.start_stream():
        sensor.disconnect()
        return

    stop_evt = threading.Event()

    def writer_loop():
        rows_since_flush = 0
        last_flush_t = time.perf_counter()

        with open(csv_path, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
            w = csv.writer(f)
            w.writerow([
                "timestamp",
                "raw_timestamp_ns",
                "pkg_no",
                "group_index",
                "Fx", "Fy", "Fz",
                "Mx", "My", "Mz"
            ])
            f.flush()

            while not stop_evt.is_set():
                frames = sensor.read_data_with_timestamp()
                if not frames:
                    time.sleep(0.001)
                    continue

                for pkg_no, ts_ns, groups in frames:
                    for gi, (Fx, Fy, Fz, Mx, My, Mz) in enumerate(groups):
                        w.writerow([
                            make_timestamp_str_us(),
                            int(ts_ns),
                            int(pkg_no),
                            int(gi),
                            float(Fx), float(Fy), float(Fz),
                            float(Mx), float(My), float(Mz),
                        ])
                        rows_since_flush += 1

                now = time.perf_counter()
                if rows_since_flush >= FLUSH_EVERY_N_ROWS or (now - last_flush_t) >= FLUSH_EVERY_SEC:
                    f.flush()
                    rows_since_flush = 0
                    last_flush_t = now

            # final flush
            f.flush()

    wt = threading.Thread(target=writer_loop, daemon=True)
    wt.start()

    print(f"✅ Logging to: {csv_path}")
    print("运行中... 按 Z 清零，按 Q 退出（仅 Windows 有效），或 Ctrl+C 退出")

    try:
        while True:
            if has_kbd and msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch:
                    c = ch.decode(errors="ignore").lower()
                    if c == "z":
                        print("\n[ZERO] 清零中...")
                        sensor.zero_channels()
                        print("[ZERO] 完成\n")
                    elif c == "q":
                        print("收到退出指令(Q)，准备退出程序")
                        break
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n用户 Ctrl+C 中断，准备退出...")
    finally:
        stop_evt.set()
        wt.join(timeout=2.0)
        try:
            sensor.stop_stream()
        except Exception:
            pass
        sensor.disconnect()

    print("=== 程序结束 ===")


if __name__ == "__main__":
    main()
