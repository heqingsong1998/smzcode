"""
粘附脚传感器调试程序
使用配置文件管理参数
"""
import sys
import os
import time
from dataclasses import asdict
from queue import Queue, Empty

import yaml

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from drivers.nianfujiao_song import NianFuJiaoDevice


def load_config():
    """加载配置文件"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "config",
        "default.yaml",
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def countdown(seconds, msg="等待"):
    """倒计时显示"""
    for i in range(seconds, 0, -1):
        print(f"\r{msg} {i}秒...", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * 50 + "\r", end="")  # 清除倒计时


def main():
    """主函数"""
    print("=== 粘附脚传感器调试程序 ===\n")

    device = None
    data_queue: Queue = Queue()

    def on_sensor_data(data_type, data):
        """处理解析后的传感器数据"""
        if data_type == "style0":
            data_queue.put(data)

    def drain_queue():
        """清空旧数据，确保下一帧为最新数据"""
        while True:
            try:
                data_queue.get_nowait()
            except Empty:
                break

    def print_latest_data(stage: str, timeout: float = 3.0):
        """等待并打印最新一帧解析数据"""
        try:
            data = data_queue.get(timeout=timeout)
        except Empty:
            print(f"[WARN] {stage}后在{timeout}秒内未收到新的传感器数据")
            return
        print(f"[DATA] {stage}: {asdict(data)}")

    try:
        # 加载配置
        config = load_config()
        sensor_config = config["sensor"]["nianfujiao"]
        debug_config = config["debug"]["nianfujiao"]

        print(f"[CONFIG] 串口: {sensor_config['port']}")
        print(f"[CONFIG] 波特率: {sensor_config['baud']}")
        print(f"[CONFIG] CSV记录: {sensor_config['enable_csv']}")
        print(f"[CONFIG] 数据打印: {sensor_config['print_data']}")
        print(f"[CONFIG] 标定计算: {sensor_config['enable_calibration']}")
        print(f"[CONFIG] 指令间隔: {debug_config['command_interval']}秒\n")

        # 创建设备实例（从配置读取参数）
        device = NianFuJiaoDevice(
            port=sensor_config["port"],
            baud=sensor_config["baud"],
            enable_csv=sensor_config["enable_csv"],
            print_data=sensor_config["print_data"],
            enable_calibration=sensor_config["enable_calibration"],
        )
        device.register_callback(on_sensor_data)

        # 打开设备
        device.open()

        # 列出所有可用指令
        device.list_available_commands()

        # 示例：按顺序发送控制指令
        interval = debug_config["command_interval"]

        def send_command_with_data(name: str, send_action, stage: str):
            print(f"\n[INFO] {interval}秒后发送{name}指令...")
            countdown(interval, "等待")
            drain_queue()
            if send_action():
                print_latest_data(stage)
            else:
                print(f"[WARN] {name}指令发送失败")

        send_command_with_data("回复", device.send_reply, "回复")
        send_command_with_data("吸合", device.send_engage, "吸合")
        send_command_with_data("清零", device.send_zero, "清零")

        print("\n[INFO] 正在继续接收数据，按 Ctrl+C 退出...")
        while True:
            time.sleep(0.2)

    except FileNotFoundError:
        print("[ERROR] 配置文件未找到: config/default.yaml")
        print("   请确保配置文件存在")

    except KeyError as e:
        print(f"[ERROR] 配置文件缺少必要字段: {e}")
        print("   请检查配置文件格式")

    except KeyboardInterrupt:
        print("\n[EXIT] 用户中断")

    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # 关闭设备
        if device:
            try:
                device.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
