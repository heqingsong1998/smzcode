"""
数据记录器 - 统一管理四个传感器的 CSV 写入
"""
import os
import csv
import time
from datetime import datetime
from typing import Dict, Any, Optional
from threading import Lock, Thread
import queue


class DataRecorder:
    """统一的数据记录器"""

    def __init__(self, base_dir: str = "data/sessions"):
        """初始化数据记录器"""
        self.base_dir = base_dir
        self.session_dir: Optional[str] = None
        self.is_recording = False

        self.csv_files: Dict[str, Any] = {}
        self.csv_writers: Dict[str, Any] = {}

        # 数据队列（异步写入）
        self.data_queues = {
            'nianfujiao_style0': queue.Queue(maxsize=5000),
            'liuzhouli': queue.Queue(maxsize=10000),
        }

        # 写入线程
        self.write_thread = None
        self.write_thread_running = False

        # 线程锁（当前没用到，但保留以防之后扩展）
        self.lock = Lock()

        self.data_counts = {
            'nianfujiao': 0,
            'liuzhouli': 0,
        }

        self.start_time: Optional[float] = None

    def _current_timestamp(self) -> str:
        """返回带毫秒和单位的时间戳字符串，避免被表格软件自动格式化"""
        now = datetime.now()
        return f"{now:%Y-%m-%d %H:%M:%S}.{now.microsecond // 1000:03d} ms"

    def _timestamp_ms_to_str(self, timestamp_ms: Any) -> str:
        """将 timestamp_ms（毫秒）转换为人类可读时间戳字符串。"""
        try:
            ts_ms_int = int(timestamp_ms)
        except Exception:
            return self._current_timestamp()

        dt = datetime.fromtimestamp(ts_ms_int / 1000.0)
        dt = dt.replace(microsecond=(ts_ms_int % 1000) * 1000)
        return f"{dt:%Y-%m-%d %H:%M:%S}.{ts_ms_int % 1000:03d} ms"

    # ==================== 启停 ====================

    def start_recording(self) -> bool:
        """开始记录"""
        if self.is_recording:
            print("[WARN] 已经在记录中")
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(self.base_dir, f"session_{timestamp}")
        os.makedirs(self.session_dir, exist_ok=True)

        try:
            self._create_nianfujiao_csv()
            self._create_liuzhouli_csv()

            self.is_recording = True
            self.start_time = time.time()

            # 启动异步写入线程
            self.write_thread_running = True
            self.write_thread = Thread(target=self._write_loop, daemon=True)
            self.write_thread.start()

            print(f"[INFO] 开始记录数据到: {self.session_dir}")
            print(f"[INFO] 异步写入模式，队列最大 1000")
            return True

        except Exception as e:
            print(f"[ERROR] 启动记录失败: {e}")
            import traceback
            traceback.print_exc()
            self._close_all_files()
            return False

    def stop_recording(self) -> bool:
        """停止记录"""
        if not self.is_recording:
            print("[WARN] 未在记录中")
            return False

        self.is_recording = False

        # 停止写入线程
        print("[INFO] 正在停止写入线程...")
        self.write_thread_running = False
        if self.write_thread:
            self.write_thread.join(timeout=3.0)

        # 写完队列中剩余数据
        self._flush_all_queues()

        self._close_all_files()

        duration = 0.0
        if self.start_time is not None:
            duration = time.time() - self.start_time

        print(f"[INFO] 记录已停止，时长: {duration:.2f}秒")
        print(f"[INFO] 数据统计: {self.data_counts}")

        # ✅ 不再做离线对齐，简单结束
        return True

    # ==================== 异步写入线程 ====================

    def _write_loop(self):
        """异步写入循环（后台线程）"""
        print("[INFO] 数据写入线程已启动")

        while self.write_thread_running or any(not q.empty() for q in self.data_queues.values()):
            try:
                # 从每个队列取数据并写入
                for sensor_id, q in self.data_queues.items():
                    batch_count = 0
                    while not q.empty() and batch_count < 10:  # 每次最多写10条
                        try:
                            row = q.get_nowait()
                            if sensor_id in self.csv_writers:
                                self.csv_writers[sensor_id].writerow(row)
                                batch_count += 1
                        except queue.Empty:
                            break

                # 定期刷新文件
                for file in self.csv_files.values():
                    file.flush()

                time.sleep(0.01)  # 10ms

            except Exception as e:
                print(f"[ERROR] 写入循环异常: {e}")
                time.sleep(0.1)

        print("[INFO] 数据写入线程已停止")

    def _flush_all_queues(self):
        """清空所有队列"""
        print("[INFO] 正在写入剩余数据...")
        for sensor_id, q in self.data_queues.items():
            count = 0
            while not q.empty():
                try:
                    row = q.get_nowait()
                    if sensor_id in self.csv_writers:
                        self.csv_writers[sensor_id].writerow(row)
                        count += 1
                except queue.Empty:
                    break
            if count > 0:
                print(f"[INFO] {sensor_id} 写入剩余 {count} 条数据")

        for file in self.csv_files.values():
            file.flush()

    # ==================== 写入接口（给 SensorManager 调） ====================

    def write_hwt606_data(self, sensor_id: str, data: Dict[str, Any]):
        """
        写入 HWT606 传感器数据（放入队列）

        约定：
        - data['timestamp_ms'] 由 SensorManager 统一线程给出（统一时间轴）
        - 这里额外生成一个人类可读的 timestamp 字符串
        """
        if not self.is_recording:
            return

        try:
            ts_ms = data.get('timestamp_ms', '')
            timestamp_str = self._timestamp_ms_to_str(ts_ms)

            row = [
                timestamp_str,     # 人类可读时间
                ts_ms,             # 统一帧时间戳（ms）
                data.get('acc_x', 0.0),
                data.get('acc_y', 0.0),
                data.get('acc_z', 0.0),
                data.get('gyro_x', 0.0),
                data.get('gyro_y', 0.0),
                data.get('gyro_z', 0.0),
                data.get('angle_x', 0.0),
                data.get('angle_y', 0.0),
                data.get('angle_z', 0.0),
                data.get('temperature', 0.0),
                data.get('vel_x', 0.0),   # ★ 新增：速度
                data.get('vel_y', 0.0),
                data.get('vel_z', 0.0),
            ]
            self.data_queues[sensor_id].put_nowait(row)
            self.data_counts[sensor_id] += 1
        except queue.Full:
            print(f"[WARN] {sensor_id} 数据队列已满，丢弃数据")
        except Exception as e:
            print(f"[ERROR] 写入{sensor_id}数据失败: {e}")

    def write_nianfujiao_data(self, style: int, data: Dict[str, Any]):
        """
        写入粘附脚传感器数据（仅 Style0，放入队列）

        约定：
        - data['timestamp_ms'] 为统一帧时间戳（由统一线程写入）
        - data['sensor_ts_ms'] 为粘附脚原始回调时间（在 SensorManager 中设置，可选）
        """
        if not self.is_recording:
            return
        if style != 0:
            # print(f"[WARN] 当前协议仅支持 style0，忽略 style{style} 的数据")
            return

        try:
            ts_ms = data.get('timestamp_ms', '')
            timestamp_str = self._timestamp_ms_to_str(ts_ms)
            raw_values = data.get('raw', [])
            calibrated_values = data.get('calibrated', [])

            # ★ 从 data 字典中取出两个和值（如果没有就默认 0.0）
            fz1_total_cal = float(data.get('fz1_total_cal', 0.0))
            fz2_total_cal = float(data.get('fz2_total_cal', 0.0))

            # timestamp_str + timestamp_ms + raw + calibrated + two totals
            row = [timestamp_str, ts_ms] + raw_values + calibrated_values + [fz1_total_cal, fz2_total_cal]

            queue_key = 'nianfujiao_style0'
            self.data_queues[queue_key].put_nowait(row)
            self.data_counts['nianfujiao'] += 1
        except queue.Full:
            print("[WARN] nianfujiao_style0 数据队列已满，丢弃数据")
        except Exception as e:
            print(f"[ERROR] 写入粘附脚数据失败: {e}")

    def write_liuzhouli_data(self, data: Dict[str, Any]):
        """
        写入六轴力传感器数据（放入队列）

        约定：
        - data['timestamp_ms']：统一帧时间戳（ms）
        - data['raw_timestamp_ns']：设备自身的高精度时间戳（如果有）
        """
        if not self.is_recording:
            return

        try:
            ts_ms = data.get('timestamp_ms', '')
            timestamp_str = self._timestamp_ms_to_str(ts_ms)
            raw_ns = data.get('raw_timestamp_ns')

            row = [
                timestamp_str,                     # 人类可读
                ts_ms,                             # 统一帧时间
                raw_ns if raw_ns is not None else '',
                float(data.get('Fx', 0.0)),
                float(data.get('Fy', 0.0)),
                float(data.get('Fz', 0.0)),
                float(data.get('Mx', 0.0)),
                float(data.get('My', 0.0)),
                float(data.get('Mz', 0.0)),
            ]
            self.data_queues['liuzhouli'].put_nowait(row)
            self.data_counts['liuzhouli'] += 1
        except queue.Full:
            print(f"[WARN] liuzhouli 数据队列已满，丢弃数据")
        except Exception as e:
            print(f"[ERROR] 写入六轴力数据失败: {e}")

    # ==================== CSV 创建 ====================

    def _create_hwt606_csv(self, sensor_id: str):
        """创建 HWT606 传感器 CSV 文件"""
        filepath = os.path.join(self.session_dir, f"{sensor_id}.csv")
        file = open(filepath, 'w', newline='', encoding='utf-8')
        writer = csv.writer(file)

        # 表头：增加 timestamp_ms 列（统一时间轴）
        writer.writerow([
            'timestamp',        # 人类可读
            'timestamp_ms',     # 统一帧时间戳（ms）
            'acc_x', 'acc_y', 'acc_z',
            'gyro_x', 'gyro_y', 'gyro_z',
            'angle_x', 'angle_y', 'angle_z',
            'temperature',
            'vel_x', 'vel_y', 'vel_z',   # ★ 新增：速度
        ])

        self.csv_files[sensor_id] = file
        self.csv_writers[sensor_id] = writer

    def _create_nianfujiao_csv(self):
        """创建粘附脚传感器（Style0）CSV 文件"""
        filepath0 = os.path.join(self.session_dir, "nianfujiao_style0.csv")
        file0 = open(filepath0, 'w', newline='', encoding='utf-8')
        writer0 = csv.writer(file0)

        writer0.writerow([
            'timestamp',        # 人类可读
            'timestamp_ms',     # 统一帧时间戳（ms）
            # 原始数据
            'Fx1_raw', 'Fy1_raw', 'Fz1+_raw', 'Mx1_raw', 'My1_raw',
            'JJJ1_1_raw', 'JJJ1_2_raw',
            'Fx2_raw', 'Fy2_raw', 'Fz2+_raw', 'Mx2_raw', 'My2_raw',
            'flag1_raw', 'flag2_raw',
            'FZ1-_raw', 'FZ2-_raw',
            'flag_fz_raw', 'flag_fx_raw', 'flag_d_raw',
            'reserved_1_raw', 'reserved_2_raw', 'reserved_3_raw', 'reserved_4_raw', 'reserved_5_raw',
            # 标定数据
            'Fx1_cal', 'Fy1_cal', 'Fz1+_cal', 'Mx1_cal', 'My1_cal',
            'JJJ1_1_cal', 'JJJ1_2_cal',
            'Fx2_cal', 'Fy2_cal', 'Fz2+_cal', 'Mx2_cal', 'My2_cal',
            'flag1_cal', 'flag2_cal',
            'FZ1-_cal', 'FZ2-_cal',
            'flag_fz_cal', 'flag_fx_cal', 'flag_d_cal',
            'reserved_1_cal', 'reserved_2_cal', 'reserved_3_cal', 'reserved_4_cal', 'reserved_5_cal',
             # ★ 新增：两个 Fz 合力（标定）
            'Fz1_total_cal',    # = Fz1+_cal + FZ1-_cal
            'Fz2_total_cal',    # = Fz2+_cal + FZ2-_cal
        ])

        self.csv_files['nianfujiao_style0'] = file0
        self.csv_writers['nianfujiao_style0'] = writer0

    def _create_liuzhouli_csv(self):
        """创建六轴力传感器 CSV 文件"""
        filepath = os.path.join(self.session_dir, "liuzhouli.csv")
        file = open(filepath, 'w', newline='', encoding='utf-8')
        writer = csv.writer(file)

        writer.writerow([
            'timestamp',        # 人类可读
            'timestamp_ms',     # 统一帧时间戳（ms）
            'raw_timestamp_ns',  # 设备高精度采集时刻（纳秒，可选）
            'Fx', 'Fy', 'Fz',
            'Mx', 'My', 'Mz',
        ])

        self.csv_files['liuzhouli'] = file
        self.csv_writers['liuzhouli'] = writer

    # ==================== 收尾 & 状态 ====================

    def _close_all_files(self):
        """关闭所有 CSV 文件"""
        for file in self.csv_files.values():
            try:
                file.close()
            except Exception:
                pass

        self.csv_files.clear()
        self.csv_writers.clear()

    def get_recording_duration(self) -> float:
        """获取记录时长（秒）"""
        if not self.is_recording or self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    def get_session_path(self) -> Optional[str]:
        """获取当前会话目录路径"""
        return self.session_dir
