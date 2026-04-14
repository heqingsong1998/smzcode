"""
传感器管理器 - 统一管理四个传感器的连接和数据流
"""
import yaml
import os
from typing import Dict, Optional

from collections import deque

from PyQt5.QtCore import QObject, pyqtSignal, QTimer

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# 🔧 使用两个独立的库文件夹，避免类变量共享问题
from drivers.HWT606_song_1.chs.jy901s_device import JY901SDevice as JY901SDevice1
from drivers.HWT606_song_2.chs.jy901s_device import JY901SDevice as JY901SDevice2

print(f"[VERIFY] JY901SDevice1 来自: {JY901SDevice1.__module__}")
print(f"[VERIFY] JY901SDevice2 来自: {JY901SDevice2.__module__}")
print(f"[VERIFY] 两个类是否相同? {JY901SDevice1 is JY901SDevice2}")

from drivers.nianfujiao_song import NianFuJiaoDevice
from drivers.sensors.utils import create_sensor, initialize_sensor


from drivers.HWT606_song_1.chs.utils import write_device_config as write_cfg_1
from drivers.HWT606_song_2.chs.utils import write_device_config as write_cfg_2

class SensorManager(QObject):
    """传感器管理器"""

    # 信号定义（用于 GUI 显示）
    hwt606_1_data_updated = pyqtSignal(dict)
    hwt606_2_data_updated = pyqtSignal(dict)
    nianfujiao_data_updated = pyqtSignal(int, dict)  # (style, data)
    liuzhouli_data_updated = pyqtSignal(dict)

    # 数据记录信号（目前设计是通过回调直接写 CSV，此处可不用）
    hwt606_1_data_record = pyqtSignal(dict)
    hwt606_2_data_record = pyqtSignal(dict)
    nianfujiao_data_record = pyqtSignal(int, dict)
    liuzhouli_data_record = pyqtSignal(dict)

    connection_status_changed = pyqtSignal(str, bool)
    error_occurred = pyqtSignal(str, str)

    def __init__(self, config_path: str = "config/default.yaml"):
        super().__init__()

        # 加载配置
        self.config = self._load_config(config_path)

        # 传感器实例
        self.hwt606_1: Optional[JY901SDevice1] = None
        self.hwt606_2: Optional[JY901SDevice2] = None
        self.nianfujiao: Optional[NianFuJiaoDevice] = None
        self.liuzhouli = None

        # （可选）六轴力最近一条样本缓存
        self._liuzhouli_last_sample = None

        self._liuzhouli_sample_queue = deque(maxlen=1000)
        self._liuzhouli_last_sample = None

        # 连接状态
        self.connection_status: Dict[str, bool] = {
            'hwt606_1': False,
            'hwt606_2': False,
            'nianfujiao': False,
            'liuzhouli': False,
        }

        # 显示刷新定时器（10Hz）
        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self._update_display)
        self.display_timer.setInterval(100)

        # 采集线程记录
        self.acquisition_threads: Dict[str, object] = {}

        # 统一采集线程相关
        self._unified_thread = None
        self._unified_running = False
        self._unified_loop_hz = 200  # 统一采集频率（100Hz）

        # 统一时间轴：帧计数 & 起始时间戳（ms）
        self._frame_index = 0
        self._record_start_ts_ms: Optional[int] = None

        # 最新数据缓存（用于 GUI 10Hz 显示）
        self.latest_data = {
            'hwt606_1': None,
            'hwt606_2': None,
            'nianfujiao': {0: None, 1: None, 2: None},
            'liuzhouli': None,
        }
        # 六轴力最新原始样本（来自驱动 drain_samples）
        self._liuzhouli_last_sample = None

        self.record_callback_hwt606_1 = None
        self.record_callback_hwt606_2 = None
        self.record_callback_nianfujiao = None
        self.record_callback_liuzhouli = None

        # 调试计数
        self._debug_print_counts = {
            'hwt606_1': 0,
            'hwt606_2': 0,
            'liuzhouli': 0,
        }
        self._hwt606_1_debug_count = 0
        self._hwt606_2_debug_count = 0

        # HWT606 速度积分缓存
        self._hwt606_last_ts_ms = {
            'hwt606_1': None,
            'hwt606_2': None,
        }
        self._hwt606_velocity = {
            'hwt606_1': {'vx': 0.0, 'vy': 0.0, 'vz': 0.0},
            'hwt606_2': {'vx': 0.0, 'vy': 0.0, 'vz': 0.0},
        }

                # HWT606 滑动偏置估计（单位：g），慢慢逼近“偏置 + 重力”
        self._hwt606_bias_g = {
            'hwt606_1': {'ax': 0.0, 'ay': 0.0, 'az': 1.0},
            'hwt606_2': {'ax': 0.0, 'ay': 0.0, 'az': 1.0},
        }

        # 上一帧净加速度（单位：m/s^2），用于梯形积分
        self._hwt606_last_acc = {
            'hwt606_1': {'ax': 0.0, 'ay': 0.0, 'az': 0.0},
            'hwt606_2': {'ax': 0.0, 'ay': 0.0, 'az': 0.0},
        }

        # 滑动估计偏置的参数
        # alpha 越小，偏置变化越慢（更平稳），可以根据效果调 0.005~0.02
        self._hwt606_bias_alpha = 0.01

        # “接近静止”的阈值（单位：g），偏离慢平均小于这个值时才更新偏置
        self._hwt606_quiet_threshold_g = 0.05

    # ==================== 配置 ====================

    def _load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        full_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            config_path
        )
        with open(full_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    # ================ 统一采集线程相关 ================

    def _ensure_unified_thread_started(self):
        """若有需要采集的传感器且统一线程未启动，则启动统一采集线程"""
        from threading import Thread
        if self._unified_thread and self._unified_thread.is_alive():
            return

        # 没有任何需要统一采集的传感器则不启动
        if not (self.connection_status['hwt606_1'] or
                self.connection_status['hwt606_2'] or
                self.connection_status['liuzhouli'] or
                self.connection_status['nianfujiao']):
            return

        self._unified_running = True
        self._frame_index = 0
        self._record_start_ts_ms = None

        self._unified_thread = Thread(
            target=self._unified_acquisition_loop,
            daemon=True,
        )
        self._unified_thread.start()
        self.acquisition_threads['unified'] = self._unified_thread
        print(f"[INFO] 统一采集线程已启动，频率={self._unified_loop_hz} Hz")

    def _maybe_stop_unified_thread(self):
        """当所有需要统一采集的传感器都断开时，停止统一采集线程"""
        if (self.connection_status['hwt606_1'] or
                self.connection_status['hwt606_2'] or
                self.connection_status['liuzhouli'] or
                self.connection_status['nianfujiao']):
            return

        self._unified_running = False
        t = self._unified_thread
        if t and t.is_alive():
            try:
                t.join(timeout=1.0)
            except Exception:
                pass
        self._unified_thread = None
        self.acquisition_threads.pop('unified', None)
        print("[INFO] 统一采集线程已停止")

    def _unified_acquisition_loop(self):
        """
        统一采集循环（以六轴力为主时钟）：
        - 以六轴力传感器的数据帧为“主时钟事件”
        - 每拿到一条六轴样本，就在同一个对齐时间戳下抓取其他传感器的最新值并写记录
        - 六轴力：使用 drain_samples() 或 read_data_with_timestamp() 拉取所有新样本
        - timestamp_ms 使用“raw_timestamp_ns 对齐到一次 wall-clock”后的推算时间轴（与 apps/debug_liuzhouli.py 一致）
        """
        import time
        import traceback
        last_cycle_end = time.perf_counter_ns()
        log_file = open("cycle_log.txt", "a", encoding="utf-8")

        # 以第一条六轴力样本对齐一次 wall-clock，后续用 raw_timestamp_ns 推算时间轴
        t0_wall_ms = None
        t0_ns = None
        while self._unified_running:

            cycle_start = time.perf_counter_ns()

            try:
                samples = []

                # -------- 六轴力：作为主时钟源，先尝试拉取所有新样本 --------
                try:
                    if self.liuzhouli and self.connection_status['liuzhouli']:
                        device = self.liuzhouli

                        if hasattr(device, "drain_samples"):
                            # 推荐接口：返回列表，每个元素：
                            # (frame_ts_ns, pkg_no, group_index, Fx, Fy, Fz, Mx, My, Mz)
                            samples = device.drain_samples() or []
                        elif hasattr(device, "read_data_with_timestamp"):
                            # 兼容旧接口：frames 结构为 (pkg_no, frame_ts_ns, groups)
                            frames = device.read_data_with_timestamp() or []
                            for pkg_no, t_ns, groups in frames:
                                for idx, (Fx, Fy, Fz, Mx, My, Mz) in enumerate(groups):
                                    samples.append(
                                        (t_ns, pkg_no, idx, Fx, Fy, Fz, Mx, My, Mz)
                                    )
                except Exception as e:
                    print(f"[ERROR] 统一线程 六轴力采集失败: {e}")
                    traceback.print_exc()
                    samples = []

                # 若当前没有任何六轴新样本，稍作休眠再继续，避免空转占用过高 CPU
                if not samples:
                    time.sleep(0.001)
                    continue

                # 对每条六轴样本执行一次“对齐写入”
                for sample in samples:
                    (t_ns, pkg_no, group_idx,
                     Fx, Fy, Fz, Mx, My, Mz) = sample

                    # 当前对齐时间（主机毫秒）：与 raw_timestamp_ns 同轴，仅做整体平移
                    try:
                        t_ns_int = int(t_ns)
                    except Exception:
                        t_ns_int = int(time.perf_counter_ns())

                    if t0_wall_ms is None:
                        t0_wall_ms = int(time.time() * 1000)
                        t0_ns = t_ns_int
                        if self._record_start_ts_ms is None:
                            self._record_start_ts_ms = t0_wall_ms

                    now_ms = int(t0_wall_ms + (t_ns_int - int(t0_ns)) / 1_000_000.0)

                    # -------- 六轴力：构造数据并写记录 --------
                    try:
                        force_data = {
                            'Fx': float(Fx),
                            'Fy': float(Fy),
                            'Fz': float(Fz),
                            'Mx': float(Mx),
                            'My': float(My),
                            'Mz': float(Mz),
                            # 设备原始采集时间戳（纳秒）
                            'raw_timestamp_ns': t_ns_int,
                            'pkg_no': int(pkg_no),
                            'group_index': int(group_idx),
                            # 对齐时间（主机毫秒）
                            'timestamp_ms': now_ms,
                        }

                        # GUI 显示用“最新一条”
                        self.latest_data['liuzhouli'] = force_data
                        self._liuzhouli_last_sample = force_data

                        if self.record_callback_liuzhouli:
                            self.record_callback_liuzhouli(force_data)
                    except Exception as e:
                        print(f"[ERROR] 统一线程 六轴力写入失败: {e}")
                        traceback.print_exc()

                    # -------- HWT606-1：在同一 now_ms 下抓取一次 --------
                    try:
                        if self.hwt606_1 and self.connection_status['hwt606_1']:
                            data1 = self._get_hwt606_data(self.hwt606_1)
                            data1['timestamp_ms'] = now_ms
                            # ★ 计算速度并写回 data1
                            self._update_hwt606_velocity('hwt606_1', data1)
                            self.latest_data['hwt606_1'] = data1

                            if self.record_callback_hwt606_1:
                                self.record_callback_hwt606_1('hwt606_1', data1)
                    except Exception as e:
                        print(f"[ERROR] 统一线程 HWT606-1 采集失败: {e}")
                        traceback.print_exc()

                    # -------- HWT606-2：在同一 now_ms 下抓取一次 --------
                    try:
                        if self.hwt606_2 and self.connection_status['hwt606_2']:
                            data2 = self._get_hwt606_data(self.hwt606_2)
                            data2['timestamp_ms'] = now_ms

                            # ★ 计算速度并写回 data2
                            self._update_hwt606_velocity('hwt606_2', data2)
                            self.latest_data['hwt606_2'] = data2

                            if self.record_callback_hwt606_2:
                                self.record_callback_hwt606_2('hwt606_2', data2)
                    except Exception as e:
                        print(f"[ERROR] 统一线程 HWT606-2 采集失败: {e}")
                        traceback.print_exc()

                    # -------- 粘附脚：用缓存 + 对齐时间写入 --------
                    try:
                        if self.nianfujiao and self.connection_status['nianfujiao']:
                            for style, last_data in self.latest_data['nianfujiao'].items():
                                if last_data is None:
                                    continue

                                data_nf = dict(last_data)
                                data_nf['timestamp_ms'] = now_ms

                                if self.record_callback_nianfujiao:
                                    self.record_callback_nianfujiao(style, data_nf)
                    except Exception as e:
                        print(f"[ERROR] 统一线程 粘附脚处理失败: {e}")
                        traceback.print_exc()
                    
                    
                    cycle_end = time.perf_counter_ns()

                    # 计算时间（ms）
                    cost_ms = (cycle_end - cycle_start) / 1_000_000
                    interval_ms = (cycle_end - last_cycle_end) / 1_000_000

                    # 写入文件（避免频繁 flush）
                    log_file.write(f"{cost_ms:.3f},{interval_ms:.3f}\n")

            

                    last_cycle_end = cycle_end

            except Exception as e:
                print(f"[ERROR] 统一采集循环异常: {e}")
                traceback.print_exc()




    # ==================== 连接管理 ====================

    # -------- HWT606-1 --------

    def connect_hwt606_1(self) -> bool:
        """连接 HWT606-1 传感器"""
        try:
            config = self.config['sensor']['hwt606_1']
            print("[DEBUG] 创建 HWT606-1 实例，使用库1 (JY901SDevice1)")
            self.hwt606_1 = JY901SDevice1(
                name=config.get('name', 'HWT606-1'),
                port=config['port'],
                baud=config['baud'],
            )
            print(f"[DEBUG] HWT606-1 实例创建成功: device={id(self.hwt606_1.device)}, "
                  f"deviceData={id(self.hwt606_1.device.deviceData)}")
            
            self.hwt606_1.open()
            cfg = config.get("write_config1", {})
            try:
                write_cfg_1(self.hwt606_1.device,
                rate=cfg.get('rate', 11),
                direction_h_v=cfg.get('direction_h_v', 0),
                direction_axis=cfg.get('direction_axis', 0))
            except Exception as e:
                print(f"[WARN] HWT606-1 写配置失败: {e}")
            
            self.connection_status['hwt606_1'] = True
            self.connection_status_changed.emit('hwt606_1', True)

            self._ensure_unified_thread_started()

            if not self.display_timer.isActive():
                self.display_timer.start()

            print(f"[INFO] HWT606-1 已连接: {config['port']}，由统一采集线程接管采集")
            return True

        except Exception as e:
            error_msg = f"连接失败: {str(e)}"
            print(f"[ERROR] HWT606-1 {error_msg}")
            self.connection_status['hwt606_1'] = False
            self.connection_status_changed.emit('hwt606_1', False)
            self.error_occurred.emit('hwt606_1', error_msg)
            return False

    def disconnect_hwt606_1(self):
        """断开 HWT606-1 连接"""
        if not self.hwt606_1:
            return

        self.connection_status['hwt606_1'] = False

        try:
            self.hwt606_1.close()
        except Exception as e:
            print(f"[WARN] HWT606-1 关闭失败: {e}")

        self.hwt606_1 = None
        self.connection_status_changed.emit('hwt606_1', False)
        print("[INFO] HWT606-1 已断开")

        self._maybe_stop_unified_thread()

    # -------- HWT606-2 --------

    def connect_hwt606_2(self) -> bool:
        """连接 HWT606-2 传感器"""
        try:
            config = self.config['sensor']['hwt606_2']
            print("[DEBUG] 创建 HWT606-2 实例，使用库2 (JY901SDevice2)")
            self.hwt606_2 = JY901SDevice2(
                name=config.get('name', 'HWT606-2'),
                port=config['port'],
                baud=config['baud'],
            )
            print(f"[DEBUG] HWT606-2 实例创建成功: device={id(self.hwt606_2.device)}, "
                  f"deviceData={id(self.hwt606_2.device.deviceData)}")
            self.hwt606_2.open()


            cfg = config.get("write_config2", {})   
            try:
                write_cfg_2(self.hwt606_2.device,
                rate=cfg.get('rate', 11),
                direction_h_v=cfg.get('direction_h_v', 0),
                direction_axis=cfg.get('direction_axis', 0))
            except Exception as e:
                print(f"[WARN] HWT606-2 写配置失败: {e}")

            self.connection_status['hwt606_2'] = True
            self.connection_status_changed.emit('hwt606_2', True)

            self._ensure_unified_thread_started()

            if not self.display_timer.isActive():
                self.display_timer.start()

            print(f"[INFO] HWT606-2 已连接: {config['port']}，由统一采集线程接管采集")
            return True

        except Exception as e:
            error_msg = f"连接失败: {str(e)}"
            print(f"[ERROR] HWT606-2 {error_msg}")
            self.connection_status['hwt606_2'] = False
            self.connection_status_changed.emit('hwt606_2', False)
            self.error_occurred.emit('hwt606_2', error_msg)
            return False

    def disconnect_hwt606_2(self):
        """断开 HWT606-2 连接"""
        if not self.hwt606_2:
            return

        self.connection_status['hwt606_2'] = False

        try:
            self.hwt606_2.close()
        except Exception as e:
            print(f"[WARN] HWT606-2 关闭失败: {e}")

        self.hwt606_2 = None
        self.connection_status_changed.emit('hwt606_2', False)
        print("[INFO] HWT606-2 已断开")

        self._maybe_stop_unified_thread()

    # -------- 粘附脚（回调采集） --------

    def connect_nianfujiao(self) -> bool:
        """连接粘附脚传感器"""
        try:
            config = self.config['sensor']['nianfujiao']
            self.nianfujiao = NianFuJiaoDevice(
                port=config['port'],
                baud=config['baud'],
                enable_csv=False,
                print_data=False,
                enable_calibration=config.get('enable_calibration', True),
            )
            self.nianfujiao.open()

            # 注册回调：只更新缓存，不直接写盘
            self.nianfujiao.register_callback(self._on_nianfujiao_callback)

            self.connection_status['nianfujiao'] = True
            self.connection_status_changed.emit('nianfujiao', True)

            self._ensure_unified_thread_started()

            if not self.display_timer.isActive():
                self.display_timer.start()

            print(f"[INFO] 粘附脚传感器已连接: {config['port']}，回调采集模式已启动")
            return True

        except Exception as e:
            error_msg = f"连接失败: {str(e)}"
            print(f"[ERROR] 粘附脚 {error_msg}")
            self.connection_status['nianfujiao'] = False
            self.connection_status_changed.emit('nianfujiao', False)
            self.error_occurred.emit('nianfujiao', error_msg)
            return False

    def _on_nianfujiao_callback(self, data_type: str, data):
        """
        粘附脚数据回调：
        - 处理 style0 数据
        - 只更新 latest_data，由统一采集线程在每帧写入 CSV
        """
        import traceback
        import time
        try:
            if data_type != 'style0':
                return

            style = 0
            data_dict = self._convert_style0_data(data)
            data_dict['sensor_ts_ms'] = int(time.time() * 1000)  # 原始到达时间

            self.latest_data['nianfujiao'][style] = data_dict

        except Exception as e:
            print(f"[ERROR] 粘附脚回调处理失败: {e}")
            traceback.print_exc()

    # -------- 六轴力 --------

    def connect_liuzhouli(self) -> bool:
        """连接六轴力传感器"""
        try:
            config = self.config['sensor']['m8128b1']
            self.liuzhouli = create_sensor(config['type'], config)

            if not initialize_sensor(self.liuzhouli):
                raise Exception("传感器初始化失败")

            # 启动数据流
            if hasattr(self.liuzhouli, 'start_stream'):
                started = False
                try:
                    started = self.liuzhouli.start_stream()
                except Exception as e:
                    print(f"[WARN] 启动六轴力数据流时报错: {e}")
                if not started:
                    raise Exception("启动六轴力数据流失败")

            self.connection_status['liuzhouli'] = True
            self.connection_status_changed.emit('liuzhouli', True)

            self._liuzhouli_last_sample = None

            self._liuzhouli_sample_queue.clear()
            self._liuzhouli_last_sample = None


            self._ensure_unified_thread_started()

            if not self.display_timer.isActive():
                self.display_timer.start()

            print(f"[INFO] 六轴力传感器已连接: {config['port']}，由统一采集线程接管采集")
            return True

        except Exception as e:
            error_msg = f"连接失败: {str(e)}"
            print(f"[ERROR] 六轴力 {error_msg}")
            # 清理已创建的六轴力对象（避免串口句柄泄漏）
            try:
                if self.liuzhouli:
                    try:
                        if hasattr(self.liuzhouli, 'stop_stream'):
                            self.liuzhouli.stop_stream()
                    except Exception:
                        pass
                    try:
                        if hasattr(self.liuzhouli, 'disconnect'):
                            self.liuzhouli.disconnect()
                        elif hasattr(self.liuzhouli, 'close'):
                            self.liuzhouli.close()
                    except Exception:
                        pass
            finally:
                self.liuzhouli = None

            self.connection_status['liuzhouli'] = False
            self.connection_status_changed.emit('liuzhouli', False)
            self.error_occurred.emit('liuzhouli', error_msg)
            return False

    # -------- 断开连接 --------

    def disconnect_nianfujiao(self):
        """断开粘附脚传感器"""
        if self.nianfujiao:
            try:
                self.nianfujiao.close()
            except Exception:
                pass
            self.nianfujiao = None
            self.connection_status['nianfujiao'] = False
            self.connection_status_changed.emit('nianfujiao', False)
            print("[INFO] 粘附脚传感器已断开")

        self._maybe_stop_unified_thread()

    def disconnect_liuzhouli(self):
        """断开六轴力传感器"""
        if self.liuzhouli:
            try:
                if hasattr(self.liuzhouli, 'stop_stream'):
                    self.liuzhouli.stop_stream()
                if hasattr(self.liuzhouli, 'disconnect'):
                    self.liuzhouli.disconnect()
                elif hasattr(self.liuzhouli, 'close'):
                    self.liuzhouli.close()
            except Exception:
                pass
            self.liuzhouli = None
            self.connection_status['liuzhouli'] = False
            self.connection_status_changed.emit('liuzhouli', False)
            print("[INFO] 六轴力传感器已断开")

            self._liuzhouli_last_sample = None
            self._liuzhouli_sample_queue.clear()
            self._liuzhouli_last_sample = None


        self._maybe_stop_unified_thread()

    def disconnect_all(self):
        """断开所有传感器"""
        self.disconnect_hwt606_1()
        self.disconnect_hwt606_2()
        self.disconnect_nianfujiao()
        self.disconnect_liuzhouli()

        if self.display_timer.isActive():
            self.display_timer.stop()

        print("[INFO] 所有传感器已断开")

    # ==================== 显示更新（10Hz） ====================

    def _update_display(self):
        """更新显示（10Hz，在主线程中执行）"""
        if self.latest_data['hwt606_1']:
            self.hwt606_1_data_updated.emit(self.latest_data['hwt606_1'])

        if self.latest_data['hwt606_2']:
            self.hwt606_2_data_updated.emit(self.latest_data['hwt606_2'])

        for style, data in self.latest_data['nianfujiao'].items():
            if data:
                self.nianfujiao_data_updated.emit(style, data)

        if self.latest_data['liuzhouli']:
            self.liuzhouli_data_updated.emit(self.latest_data['liuzhouli'])

    # ==================== 数据转换与工具 ====================

    def _convert_style0_data(self, data) -> dict:
        """
        转换粘附脚 Style0Data 为字典格式：
        - raw: 原始 24 个字段
        - calibrated: 如启用标定，则为标定后的 24 个值，否则全 0
        """
        from drivers.nianfujiao_song.utils import (
            cal_Fx1, cal_Fy1, cal_Fz1_plus, cal_Mx1, cal_My1,
            cal_Fx2, cal_Fy2, cal_Fz2_plus, cal_Mx2, cal_My2,
            cal_FZ1_minus, cal_FZ2_minus,
        )

        raw_values = [
            data.Fx1, data.Fy1, data.Fz1_plus, data.Mx1, data.My1,
            data.JJJ1_1, data.JJJ1_2,
            data.Fx2, data.Fy2, data.Fz2_plus, data.Mx2, data.My2,
            data.flag1, data.flag2,
            data.FZ1_minus, data.FZ2_minus,
            data.flag_fz, data.flag_fx, data.flag_d,
            data.reserved_1, data.reserved_2, data.reserved_3, data.reserved_4, data.reserved_5,
        ]

        device = self.nianfujiao
        enable_cal = getattr(device, "enable_calibration", False)

        if enable_cal:
            calibrated_values = [
                cal_Fx1(data.Fx1),
                cal_Fy1(data.Fy1),
                cal_Fz1_plus(data.Fz1_plus),
                cal_Mx1(data.Mx1),
                cal_My1(data.My1),
                data.JJJ1_1,  # JJJ1_1 无标定函数
                data.JJJ1_2,  # JJJ1_2 无标定函数
                cal_Fx2(data.Fx2),
                cal_Fy2(data.Fy2),
                cal_Fz2_plus(data.Fz2_plus),
                cal_Mx2(data.Mx2),
                cal_My2(data.My2),
                data.flag1,  # flag1 无标定函数
                data.flag2,  # flag2 无标定函数
                cal_FZ1_minus(data.FZ1_minus),
                cal_FZ2_minus(data.FZ2_minus),
                data.flag_fz,  # 新增 flag 字段无标定函数
                data.flag_fx,
                data.flag_d,
                data.reserved_1,  # 保留字段无标定函数
                data.reserved_2,
                data.reserved_3,
                data.reserved_4,
                data.reserved_5,
            ]
        else:
            calibrated_values = [0.0] * 24
        # ★ 计算两个 Fz 合力（标定值）
        # 索引含义见上面的说明
        fz1_total_cal = calibrated_values[2] + calibrated_values[14]
        fz2_total_cal = calibrated_values[9] + calibrated_values[15]

        return {
            'raw': raw_values,
            'calibrated': calibrated_values,
            'fz1_total_cal': fz1_total_cal,  # Fz1+_cal + FZ1-_cal
            'fz2_total_cal': fz2_total_cal,  # Fz2+_cal + FZ2-_cal
        }

    def _get_hwt606_data(self, sensor) -> dict:
        """获取 HWT606 传感器数据（支持 JY901SDevice1 和 JY901SDevice2）"""
        # 如果启用角度基准，优先使用校准角度
        if getattr(sensor, "angle_baseline", None) is not None:
            angle_x, angle_y, angle_z = sensor.get_calibrated_angles()
        else:
            angle_x = sensor.device.getDeviceData('angleX') or 0.0
            angle_y = sensor.device.getDeviceData('angleY') or 0.0
            angle_z = sensor.device.getDeviceData('angleZ') or 0.0

        # 如角度全 0，尝试打一个快照用于调试
        try:
            if (angle_x == 0.0 and angle_y == 0.0 and angle_z == 0.0) \
                    and self._debug_print_counts.get('hwt606_1', 0) < 5:
                self._debug_print_counts['hwt606_1'] += 1
                print(f"[DEBUG] HWT606 raw snapshot "
                      f"({self._debug_print_counts['hwt606_1']}) -> ")
                try:
                    keys = [
                        'accX', 'accY', 'accZ',
                        'gyroX', 'gyroY', 'gyroZ',
                        'angleX', 'angleY', 'angleZ',
                        'temperature',
                    ]
                    snapshot = {k: sensor.device.getDeviceData(k) for k in keys}
                    print(snapshot)
                except Exception as e:
                    print(f"[DEBUG] 无法读取 device 数据: {e}")
        except Exception:
            pass

        return {
            'acc_x': sensor.device.getDeviceData('accX') or 0.0,
            'acc_y': sensor.device.getDeviceData('accY') or 0.0,
            'acc_z': sensor.device.getDeviceData('accZ') or 0.0,
            'gyro_x': sensor.device.getDeviceData('gyroX') or 0.0,
            'gyro_y': sensor.device.getDeviceData('gyroY') or 0.0,
            'gyro_z': sensor.device.getDeviceData('gyroZ') or 0.0,
            'angle_x': angle_x,
            'angle_y': angle_y,
            'angle_z': angle_z,
            'temperature': sensor.device.getDeviceData('temperature') or 0.0,
        }

    # def _update_hwt606_velocity(self, sensor_id: str, data: dict):
    #     """
    #     根据当前加速度和 timestamp_ms 对 HWT606 做简单速度积分：
    #     v(t) = v(t-1) + a * dt

    #     注意：
    #     - 这是最简单的积分方式，会有明显漂移，仅用于大致速度估计
    #     """
    #     ts_ms = data.get('timestamp_ms')
    #     if ts_ms is None:
    #         # 没有统一时间戳就不积分
    #         return

    #     last_ts = self._hwt606_last_ts_ms.get(sensor_id)
    #     if last_ts is None:
    #         # 第一帧，只记录时间，不积分
    #         self._hwt606_last_ts_ms[sensor_id] = ts_ms
    #         data['vel_x'] = 0.0
    #         data['vel_y'] = 0.0
    #         data['vel_z'] = 0.0
    #         return

    #     dt = (ts_ms - last_ts) / 1000.0  # 秒
    #     if dt <= 0:
    #         # 时间非正，直接跳过
    #         data['vel_x'] = self._hwt606_velocity[sensor_id]['vx']
    #         data['vel_y'] = self._hwt606_velocity[sensor_id]['vy']
    #         data['vel_z'] = self._hwt606_velocity[sensor_id]['vz']
    #         return

    #     self._hwt606_last_ts_ms[sensor_id] = ts_ms

    #     # 读取加速度
    #     ax = float(data.get('acc_x', 0.0))
    #     ay = float(data.get('acc_y', 0.0))
    #     az = float(data.get('acc_z', 0.0))
    #     az -=1.0  # 去除重力影响
    #     # 如果 acc 单位是 g，在这里乘 9.8
    #     ax *= 9.8
    #     ay *= 9.8
    #     az *= 9.8

    #     v_state = self._hwt606_velocity[sensor_id]
    #     v_state['vx'] += ax * dt
    #     v_state['vy'] += ay * dt
    #     v_state['vz'] += az * dt

    #     # 写回到当前 data，后面会被写入 CSV
    #     data['vel_x'] = v_state['vx']
    #     data['vel_y'] = v_state['vy']
    #     data['vel_z'] = v_state['vz']

    def _update_hwt606_velocity(self, sensor_id: str, data: dict):
        """
        实时速度积分（滑动偏置估计 + 梯形积分）

        - 不需要等待标定阶段；
        - 用低通的“慢平均”估计三轴偏置（含重力），只在加速度变化不大时更新；
        - 每帧：净加速度 = 当前加速度 - 慢平均，加到速度里；
        - 使用梯形积分：v_k = v_{k-1} + (a_{k-1}+a_k)/2 * dt。
        """

        ts_ms = data.get('timestamp_ms')
        if ts_ms is None:
            # 没有统一时间戳就不积分
            return

        # ---------- 取出该传感器当前状态 ----------
        last_ts = self._hwt606_last_ts_ms.get(sensor_id)
        v_state = self._hwt606_velocity.get(sensor_id)
        bias = self._hwt606_bias_g.get(sensor_id)
        last_acc = self._hwt606_last_acc.get(sensor_id)

        if v_state is None or bias is None or last_acc is None:
            # 意外情况：这个 id 没初始化，直接跳过
            return

        # 第一次有时间戳：只更新时间，不积分
        if last_ts is None:
            self._hwt606_last_ts_ms[sensor_id] = ts_ms
            data['vel_x'] = v_state['vx']
            data['vel_y'] = v_state['vy']
            data['vel_z'] = v_state['vz']
            return

        dt = (ts_ms - last_ts) / 1000.0  # 秒
        if dt <= 0:
            # 时间非正，直接沿用上一次速度
            data['vel_x'] = v_state['vx']
            data['vel_y'] = v_state['vy']
            data['vel_z'] = v_state['vz']
            return

        # 更新时间
        self._hwt606_last_ts_ms[sensor_id] = ts_ms

        # ---------- 当前原始加速度（单位：g） ----------
        ax_g = float(data.get('acc_x', 0.0))
        ay_g = float(data.get('acc_y', 0.0))
        az_g = float(data.get('acc_z', 0.0))

        # ---------- 滑动估计偏置（含重力） ----------
        alpha = self._hwt606_bias_alpha

        dev_x = ax_g - bias['ax']
        dev_y = ay_g - bias['ay']
        dev_z = az_g - bias['az']
        dev_mag = (dev_x**2 + dev_y**2 + dev_z**2) ** 0.5

        # 只有在“偏离不大”（近似静止/匀速）时，才更新偏置，避免剧烈运动污染
        if dev_mag < self._hwt606_quiet_threshold_g:
            bias['ax'] = (1.0 - alpha) * bias['ax'] + alpha * ax_g
            bias['ay'] = (1.0 - alpha) * bias['ay'] + alpha * ay_g
            bias['az'] = (1.0 - alpha) * bias['az'] + alpha * az_g
            self._hwt606_bias_g[sensor_id] = bias

        # ---------- 去偏置，得到净加速度（单位：g） ----------
        ax_g_net = ax_g - bias['ax']
        ay_g_net = ay_g - bias['ay']
        az_g_net = az_g - bias['az']
        # 注意：这里已经把重力的慢平均值也减掉了，不需要再 az -= 1.0

        # ---------- 转为 m/s^2 ----------
        g0 = 9.8
        ax = ax_g_net * g0
        ay = ay_g_net * g0
        az = az_g_net * g0

        # ---------- 梯形积分 ----------
        # v_k = v_{k-1} + (a_{k-1} + a_k)/2 * dt
        v_state['vx'] += 0.5 * (last_acc['ax'] + ax) * dt
        v_state['vy'] += 0.5 * (last_acc['ay'] + ay) * dt
        v_state['vz'] += 0.5 * (last_acc['az'] + az) * dt

        # 更新状态存回去
        self._hwt606_velocity[sensor_id] = v_state
        self._hwt606_last_acc[sensor_id] = {'ax': ax, 'ay': ay, 'az': az}

        # 把当前速度写回 data，用于 CSV / GUI
        data['vel_x'] = v_state['vx']
        data['vel_y'] = v_state['vy']
        data['vel_z'] = v_state['vz']



    # ==================== 传感器控制 ====================

    def hwt606_1_accel_calibration(self) -> bool:
        """HWT606-1 加速度校准"""
        if self.hwt606_1 and self.connection_status['hwt606_1']:
            try:
                from drivers.HWT606_song_1.chs.utils import acceleration_calibration
                acceleration_calibration(self.hwt606_1.device)
                print("[INFO] HWT606-1 加速度校准完成")
                return True
            except Exception as e:
                error_msg = f"加速度校准失败: {str(e)}"
                print(f"[ERROR] HWT606-1 {error_msg}")
                self.error_occurred.emit('hwt606_1', error_msg)
                return False
        return False

    def hwt606_1_angle_zero(self) -> bool:
        """HWT606-1 角度清零"""
        if self.hwt606_1 and self.connection_status['hwt606_1']:
            success = self.hwt606_1.angle_zero()
            if success:
                print("[INFO] HWT606-1 角度清零完成")
            else:
                self.error_occurred.emit('hwt606_1', "角度清零失败")
            return success
        return False

    def hwt606_1_reset_baseline(self) -> bool:
        """HWT606-1 重置角度基准"""
        if self.hwt606_1 and self.connection_status['hwt606_1']:
            self.hwt606_1.reset_angle_baseline()
            print("[INFO] HWT606-1 角度基准已重置")
            return True
        return False

    def hwt606_2_accel_calibration(self) -> bool:
        """HWT606-2 加速度校准"""
        if self.hwt606_2 and self.connection_status['hwt606_2']:
            try:
                from drivers.HWT606_song_2.chs.utils import acceleration_calibration
                acceleration_calibration(self.hwt606_2.device)
                print("[INFO] HWT606-2 加速度校准完成")
                return True
            except Exception as e:
                error_msg = f"加速度校准失败: {str(e)}"
                print(f"[ERROR] HWT606-2 {error_msg}")
                self.error_occurred.emit('hwt606_2', error_msg)
                return False
        return False

    def hwt606_2_angle_zero(self) -> bool:
        """HWT606-2 角度清零"""
        if self.hwt606_2 and self.connection_status['hwt606_2']:
            success = self.hwt606_2.angle_zero()
            if success:
                print("[INFO] HWT606-2 角度清零完成")
            else:
                self.error_occurred.emit('hwt606_2', "角度清零失败")
            return success
        return False

    def hwt606_2_reset_baseline(self) -> bool:
        """HWT606-2 重置角度基准"""
        if self.hwt606_2 and self.connection_status['hwt606_2']:
            self.hwt606_2.reset_angle_baseline()
            print("[INFO] HWT606-2 角度基准已重置")
            return True
        return False

    def nianfujiao_reply(self) -> bool:
        """粘附脚回复指令（恢复默认状态）"""
        if self.nianfujiao and self.connection_status['nianfujiao']:
            success = self.nianfujiao.send_reply()
            if success:
                print("[INFO] 粘附脚回复指令已发送")
            else:
                self.error_occurred.emit('nianfujiao', "回复指令发送失败")
            return success
        return False

    def nianfujiao_engage(self) -> bool:
        """粘附脚吸合指令"""
        if self.nianfujiao and self.connection_status['nianfujiao']:
            success = self.nianfujiao.send_engage()
            if success:
                print("[INFO] 粘附脚吸合指令已发送")
            else:
                self.error_occurred.emit('nianfujiao', "吸合指令发送失败")
            return success
        return False

    def nianfujiao_zero(self) -> bool:
        """粘附脚清零指令"""
        if self.nianfujiao and self.connection_status['nianfujiao']:
            success = self.nianfujiao.send_zero()
            if success:
                print("[INFO] 粘附脚清零指令已发送")
            else:
                self.error_occurred.emit('nianfujiao', "清零指令发送失败")
            return success
        return False

    def liuzhouli_zero(self) -> bool:
        """六轴力清零指令"""
        if self.liuzhouli and self.connection_status['liuzhouli']:
            try:
                self.liuzhouli.zero_channels()
                print("[INFO] 六轴力传感器清零完成")
                return True
            except Exception as e:
                error_msg = f"清零失败: {str(e)}"
                print(f"[ERROR] 六轴力 {error_msg}")
                self.error_occurred.emit('liuzhouli', error_msg)
                return False
        return False

    # ==================== 状态查询 ====================

    def is_connected(self, sensor_id: str) -> bool:
        """检查某个传感器是否已连接"""
        return self.connection_status.get(sensor_id, False)

    def get_all_status(self) -> Dict[str, bool]:
        """获取所有传感器连接状态"""
        return self.connection_status.copy()

    def get_hwt606_1_baseline(self) -> Optional[dict]:
        """获取 HWT606-1 角度基准"""
        if self.hwt606_1:
            return self.hwt606_1.angle_baseline
        return None

    def get_hwt606_2_baseline(self) -> Optional[dict]:
        """获取 HWT606-2 角度基准"""
        if self.hwt606_2:
            return self.hwt606_2.angle_baseline
        return None
