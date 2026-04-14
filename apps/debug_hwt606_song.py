"""
HWT606姿态传感器调试程序
使用配置文件管理参数
"""
import sys
import os
import time
import yaml
import csv
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# 🔧 调试程序使用库1
from drivers.HWT606_song_1.chs.jy901s_device import JY901SDevice
from drivers.HWT606_song_1.chs.utils import acceleration_calibration


def load_config():
    """加载配置文件"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        "config", 
        "default.yaml"
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
    print("=== HWT606姿态传感器调试程序 ===\n")
    sensor = None  # 在异常情况下也能安全关闭
    csv_file = None
    csv_writer = None
    try:
        # 加载配置
        config = load_config()
        sensor_config = config["sensor"]["hwt606_1"]  # 使用传感器1的配置
        debug_config = config["debug"]["hwt606"]
        
        print(f"[CONFIG] 传感器名称: {sensor_config['name']}")
        print(f"[CONFIG] 串口: {sensor_config['port']}")
        print(f"[CONFIG] 波特率: {sensor_config['baud']}")
        print(f"[CONFIG] 初始化等待: {debug_config['init_wait']}秒")
        print(f"[CONFIG] 步骤等待: {debug_config['step_wait']}秒\n")
        
        # 创建设备实例（从配置读取参数）
        sensor = JY901SDevice(
            name=sensor_config['name'],
            port=sensor_config['port'],
            baud=sensor_config['baud']
        )
        
        # 打开设备
        sensor.open()

        # ==== CSV 日志准备 ====
        log_name = f"hwt606_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), log_name)
        csv_file = open(csv_path, "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([
            "timestamp",
            "elapsed_ms",
            "angleX",
            "angleY",
            "angleZ",
            "accX",
            "accY",
            "accZ",
            "gyroX",
            "gyroY",
            "gyroZ",
            "temperature",
        ])
        start_time = time.time()
        print(f"[LOG] CSV logging to {csv_path}")

        def on_data(device_model):
            """数据回调：写入一行带时间戳的数据到 CSV。"""
            now = datetime.now()
            elapsed_ms = (time.time() - start_time) * 1000.0
            row = [
                "'" + now.strftime("%Y-%m-%d %H:%M:%S.%f"),
                f"{elapsed_ms:.3f}",
                device_model.getDeviceData("angleX") or 0.0,
                device_model.getDeviceData("angleY") or 0.0,
                device_model.getDeviceData("angleZ") or 0.0,
                device_model.getDeviceData("accX") or 0.0,
                device_model.getDeviceData("accY") or 0.0,
                device_model.getDeviceData("accZ") or 0.0,
                device_model.getDeviceData("gyroX") or 0.0,
                device_model.getDeviceData("gyroY") or 0.0,
                device_model.getDeviceData("gyroZ") or 0.0,
                device_model.getDeviceData("temperature") or 0.0,
            ]
            csv_writer.writerow(row)
            csv_file.flush()

        # 注册回调，持续写入 CSV
        sensor.register_callback(on_data)
        
        print("[INFO] 等待设备初始化和数据稳定...")
        countdown(debug_config['init_wait'], "初始化")

        # ========== 步骤1: 读取传感器配置 ==========
        print("\n" + "="*60)
        print("[STEP 1] 读取传感器配置")
        print("="*60)
        try:
            device_config = sensor.read_config()
            if device_config:
                for key, value in device_config.items():
                    print(f"{key}: {value}")
            else:
                print("[INFO] 设备返回空配置或不支持读取配置")
        except Exception as e:
            print(f"[WARN] 读取配置失败: {e}")

        # ========== 步骤2: 加速度校准 ==========
        print("\n" + "="*60)
        print("[STEP 2] 执行加速度校准")
        print("="*60)
        acceleration_calibration(sensor.device)

        # ========== 步骤3: 等待并打印原始角度 ==========
        countdown(debug_config['step_wait'], "等待数据稳定")

        print("\n" + "="*60)
        print("[STEP 3] 打印当前角度值（清零前）")
        print("="*60)
        angle_x = sensor.device.getDeviceData("angleX")
        angle_y = sensor.device.getDeviceData("angleY")
        angle_z = sensor.device.getDeviceData("angleZ")
        
        if angle_x is not None and angle_y is not None and angle_z is not None:
            print(f"当前角度: Roll={angle_x:.2f}°, Pitch={angle_y:.2f}°, Yaw={angle_z:.2f}°")
        else:
            print("[WARN] 角度数据无效")
        
        # ========== 步骤4: 执行角度清零 ==========
        print("\n" + "="*60)
        print("[STEP 4] 执行角度清零")
        print("="*60)
        success = sensor.angle_zero()
        
        if not success:
            print("\n[ERROR] 角度清零失败，请检查设备连接")
            input("\n按回车键退出...")
            sensor.close()
            sys.exit(1)
        
        # ========== 步骤5: 打印清零后的角度 ==========
        countdown(debug_config['step_wait'], "等待清零后数据")

        print("\n" + "="*60)
        print("[STEP 5] 打印清零后的角度值")
        print("="*60)
        roll, pitch, yaw = sensor.get_calibrated_angles()
        print(f"清零后角度: Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°")
        
        # ========== 步骤6: 移动传感器后再次打印 ==========
        print("\n[INFO] 现在可以移动传感器...")
        countdown(debug_config['step_wait'], "观察角度变化")

        print("\n" + "="*60)
        print("[STEP 6] 再次打印当前角度值（校准后）")
        print("="*60)
        roll, pitch, yaw = sensor.get_calibrated_angles()
        print(f"当前校准角度: Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°")
        
        # 同时显示原始值
        angle_x_raw = sensor.device.getDeviceData("angleX")
        angle_y_raw = sensor.device.getDeviceData("angleY")
        angle_z_raw = sensor.device.getDeviceData("angleZ")
        if angle_x_raw is not None:
            print(f"原始角度值:   Roll={angle_x_raw:.2f}°, Pitch={angle_y_raw:.2f}°, Yaw={angle_z_raw:.2f}°")
        
        # ========== 完成 ==========
        print("\n" + "="*60)
        input("\n✅ 测试完成！按回车键退出...")
        
    except FileNotFoundError:
        print("❌ 配置文件未找到: config/default.yaml")
        print("   请确保配置文件存在")
    
    except KeyError as e:
        print(f"❌ 配置文件缺少必要字段: {e}")
        print("   请检查配置文件格式")
    
    except KeyboardInterrupt:
        print("\n[EXIT] 用户中断")
    
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if sensor is not None:
            try:
                sensor.close()
            except Exception:
                pass
        if csv_file is not None:
            try:
                csv_file.close()
                print(f"[LOG] CSV saved to {csv_path}")
            except Exception:
                pass


if __name__ == '__main__':
    main()
