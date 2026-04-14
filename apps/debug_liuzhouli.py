"""应用层测试：apps/testliuzhouli.py

采用“方案2”：用 raw_timestamp_ns 推算可读时间戳（让 timestamp 间隔更像 5ms）
"""

from __future__ import annotations

import csv
import os
import sys
import time
import threading
from datetime import datetime, timedelta

import yaml

# 让 python 能找到项目根目录
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from drivers.sensors.utils import create_sensor, initialize_sensor


def format_dt_us(dt: datetime) -> str:
    return f"{dt:%Y-%m-%d %H:%M:%S}.{dt.microsecond:06d}"


def load_config():
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "config",
        "default.yaml"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    cfg = load_config()
    sensor_cfg = cfg["sensor"]["m8128b1"]

    out_dir = cfg.get("logging", {}).get("out_dir", "data")
    flush_every_n = int(cfg.get("logging", {}).get("flush_every_n_rows", 50))
    flush_every_sec = float(cfg.get("logging", {}).get("flush_every_sec", 0.5))

    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(out_dir, f"m8128_frame_by_frame_{ts}.csv")

    # Windows 键盘
    try:
        import msvcrt
        has_kbd = True
    except ImportError:
        msvcrt = None
        has_kbd = False
        print("⚠️ 非Windows系统：不支持 Z/Q 键盘控制（可用 Ctrl+C 退出）")

    sensor = create_sensor(sensor_cfg["type"], sensor_cfg)

    if not initialize_sensor(sensor, auto_config=True):
        return

    if not sensor.start_stream():
        sensor.disconnect()
        return

    stop_evt = threading.Event()

    def writer_loop():
        rows_since_flush = 0
        last_flush_t = time.perf_counter()

        # 基准：wall_clock_t0 对应 raw_ns_t0
        t0_wall = None
        t0_ns = None

        with open(csv_path, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
            w = csv.writer(f)
            w.writerow([
                "timestamp",          # 推算的可读时间
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

                for pkg_no, raw_ns, groups in frames:
                    raw_ns = int(raw_ns)

                    if t0_wall is None:
                        t0_wall = datetime.now()
                        t0_ns = raw_ns

                    dt_ns = raw_ns - t0_ns
                    ts_wall = t0_wall + timedelta(microseconds=dt_ns / 1000.0)

                    for gi, (Fx, Fy, Fz, Mx, My, Mz) in enumerate(groups):
                        w.writerow([
                            format_dt_us(ts_wall),
                            raw_ns,
                            int(pkg_no),
                            int(gi),
                            float(Fx), float(Fy), float(Fz),
                            float(Mx), float(My), float(Mz),
                        ])
                        rows_since_flush += 1

                now = time.perf_counter()
                if rows_since_flush >= flush_every_n or (now - last_flush_t) >= flush_every_sec:
                    f.flush()
                    rows_since_flush = 0
                    last_flush_t = now

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
