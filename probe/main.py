import psutil
import json
import configparser
import os
import platform
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime


class Config:

    def __init__(self):
        self.config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'probe.config')
        self.config.read(config_path, encoding='utf-8')

        self.host = self.config.get('server', 'host', fallback='0.0.0.0')
        self.port = self.config.getint('server', 'port', fallback=8080)
        self.token = self.config.get('auth', 'token', fallback='default_token')


def get_cpu_info():
    # cpu信息
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count_logical = psutil.cpu_count(logical=True)
    cpu_count_physical = psutil.cpu_count(logical=False)

    # 获取CPU型号
    cpu_model = None
    if os.name == 'nt':
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_model = winreg.QueryValueEx(key, "ProcessorNameString")[0]
            winreg.CloseKey(key)
        except Exception:
            cpu_model = platform.processor()
    else:  # Linux/macOS
        try:
            if os.path.exists('/proc/cpuinfo'):
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if line.startswith('model name'):
                            cpu_model = line.split(':')[1].strip()
                            break
            else:
                import subprocess
                result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    cpu_model = result.stdout.strip()
        except Exception:
            cpu_model = platform.processor()

    return {
        'model': cpu_model or 'Unknown',
        'percent': cpu_percent,
        'logical_cores': cpu_count_logical,
        'physical_cores': cpu_count_physical
    }


def get_disk_info():
    # 获取磁盘分区信息
    disks = []

    partitions = psutil.disk_partitions(all=False)

    for partition in partitions:
        try:
            if os.name == 'nt' and partition.fstype == '':
                continue

            usage = psutil.disk_usage(partition.mountpoint)

            disk_info = {
                'device': partition.device,
                'mountpoint': partition.mountpoint,
                'fstype': partition.fstype,
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': usage.percent
            }

            disks.append(disk_info)
        except PermissionError:
            continue
        except OSError:
            continue

    return disks


def get_system_info():
    # 获取系统基本信息
    try:
        cpu_info = get_cpu_info()

        memory = psutil.virtual_memory()

        disk_info = get_disk_info()

        net_io = psutil.net_io_counters()

        boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime('%Y-%m-%d %H:%M:%S')

        info = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'platform': platform.system(),
            'platform_detail': os.name,
            'cpu': cpu_info,
            'memory': {
                'total': memory.total,
                'available': memory.available,
                'used': memory.used,
                'percent': memory.percent
            },
            'disks': disk_info,
            'network': {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            },
            'boot_time': boot_time
        }

        return info
    except Exception as e:
        return {'error': str(e)}


class MonitorHandler(BaseHTTPRequestHandler):

    config = Config()

    def do_GET(self):

        token = self.headers.get('Authorization', '').replace('Bearer ', '')

        if not token or token != self.config.token:
            self.send_error_response(401, 'Unauthorized: Invalid or missing token')
            return

        system_info = get_system_info()

        if 'error' in system_info:
            self.send_error_response(500, f'Internal Server Error: {system_info["error"]}')
            return

        self.send_success_response(system_info)

    def send_success_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_error_response(self, code, message):
        self.send_response(code)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        error_data = {'error': message}
        self.wfile.write(json.dumps(error_data, ensure_ascii=False).encode('utf-8'))

    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {args[0]}")


def run_server():
    config = Config()

    server_address = (config.host, config.port)
    httpd = HTTPServer(server_address, MonitorHandler)

    print(f"服务器监控服务已启动")
    print(f"监听地址: {config.host}:{config.port}")
    print(f"访问方式: GET http://<IP>:{config.port}/")
    print(f"认证方式: Header Authorization: Bearer <token>")
    print(f"按 Ctrl+C 停止服务\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        httpd.server_close()


if __name__ == '__main__':
    run_server()
