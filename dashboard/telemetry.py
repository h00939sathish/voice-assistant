"""
Real system telemetry — CPU, RAM, GPU, Disk, Network via psutil + nvidia-smi.
Used by app.py SSE endpoint to push live metrics to the dashboard.
"""

import os
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from threading import Lock

import psutil


@dataclass
class SystemMetrics:
    cpu: float = 0.0
    ram: float = 0.0
    gpu: float = 0.0
    vram: float = 0.0
    vram_used: float = 0.0
    vram_total: float = 0.0
    disk: float = 0.0
    network: float = 0.0
    gpu_temp: float = 0.0
    gpu_power: float = 0.0
    gpu_fan: float = 0.0
    gpu_name: str = ""
    cpu_temp: float = 0.0
    uptime: str = ""
    processes: int = 0
    boot_time: str = ""
    timestamp: str = ""


@dataclass
class SystemInfo:
    os: str = ""
    kernel: str = ""
    hostname: str = ""
    cpu_model: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    ram_total: float = 0.0
    python_version: str = ""


class TelemetryService:
    """Collects real system metrics at configurable intervals."""

    def __init__(self, history_size: int = 60):
        self._lock = Lock()
        self._history: deque = deque(maxlen=history_size)
        self._latest = SystemMetrics()
        self._info = self._collect_system_info()
        self._last_net = psutil.net_io_counters()
        self._last_net_time = time.time()
        self._gpu_available = self._check_gpu()

    def _check_gpu(self) -> bool:
        try:
            subprocess.run(
                ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            return True
        except Exception:
            return False

    def _collect_system_info(self) -> SystemInfo:
        import platform
        info = SystemInfo()
        info.os = f"{platform.system()} {platform.release()}"
        info.kernel = platform.version()
        info.hostname = platform.node()
        info.python_version = platform.python_version()
        try:
            info.cpu_model = self._read_cpu_model()
        except Exception:
            info.cpu_model = platform.processor() or "Unknown"
        info.cpu_cores = psutil.cpu_count(logical=False) or 0
        info.cpu_threads = psutil.cpu_count(logical=True) or 0
        info.ram_total = round(psutil.virtual_memory().total / (1024**3), 1)
        return info

    def _read_cpu_model(self) -> str:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except FileNotFoundError:
            pass
        try:
            result = subprocess.run(
                ["wmic", "cpu", "get", "name"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if len(lines) > 1:
                return lines[1]
        except Exception:
            pass
        return "Unknown"

    def _parse_gpu_float(self, val: str) -> float:
        try:
            return float(val.strip())
        except (ValueError, TypeError):
            return 0.0

    def _get_gpu_metrics(self) -> dict:
        if not self._gpu_available:
            return {"gpu": 0, "vram": 0, "vram_used": 0, "vram_total": 4.0,
                    "temp": 0, "power": 0, "fan": 0, "name": "N/A"}
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total,"
                    "temperature.gpu,power.draw,fan.speed,name",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True, text=True, timeout=5,
            )
            parts = [p.strip() for p in result.stdout.strip().split(", ")]
            if len(parts) >= 7:
                vram_total = self._parse_gpu_float(parts[2])
                vram_used = self._parse_gpu_float(parts[1])
                return {
                    "gpu": self._parse_gpu_float(parts[0]),
                    "vram_used": vram_used,
                    "vram_total": vram_total,
                    "vram": round(vram_used / vram_total * 100, 1) if vram_total > 0 else 0,
                    "temp": self._parse_gpu_float(parts[3]),
                    "power": self._parse_gpu_float(parts[4]),
                    "fan": self._parse_gpu_float(parts[5]),
                    "name": parts[6],
                }
        except Exception:
            pass
        return {"gpu": 0, "vram": 0, "vram_used": 0, "vram_total": 4.0,
                "temp": 0, "power": 0, "fan": 0, "name": "N/A"}

    def _get_cpu_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            if "coretemp" in temps:
                return temps["coretemp"][0].current
            if "cpu_thermal" in temps:
                return temps["cpu_thermal"][0].current
        except Exception:
            pass
        return 0.0

    def collect(self) -> SystemMetrics:
        m = SystemMetrics()
        m.timestamp = datetime.now().isoformat()

        # CPU
        m.cpu = psutil.cpu_percent(interval=None)
        m.processes = len(psutil.pids())

        # RAM
        mem = psutil.virtual_memory()
        m.ram = round(mem.percent, 1)

        # Disk
        disk = psutil.disk_usage("/")
        m.disk = round(disk.percent, 1)

        # Network
        now = time.time()
        net = psutil.net_io_counters()
        elapsed = now - self._last_net_time
        if elapsed > 0:
            bytes_sent = net.bytes_sent - self._last_net.bytes_sent
            bytes_recv = net.bytes_recv - self._last_net.bytes_recv
            m.network = round((bytes_sent + bytes_recv) / elapsed / 1024, 1)
        self._last_net = net
        self._last_net_time = now

        # GPU
        gpu = self._get_gpu_metrics()
        m.gpu = gpu["gpu"]
        m.vram = gpu["vram"]
        m.vram_used = gpu["vram_used"]
        m.vram_total = gpu["vram_total"]
        m.gpu_temp = gpu["temp"]
        m.gpu_power = gpu["power"]
        m.gpu_fan = gpu["fan"]
        m.gpu_name = gpu["name"]

        # CPU temp
        m.cpu_temp = self._get_cpu_temp()

        # Uptime
        boot = psutil.boot_time()
        m.boot_time = datetime.fromtimestamp(boot).isoformat()
        uptime_secs = time.time() - boot
        days = int(uptime_secs // 86400)
        hours = int((uptime_secs % 86400) // 3600)
        mins = int((uptime_secs % 3600) // 60)
        parts = []
        if days > 0: parts.append(f"{days}d")
        if hours > 0: parts.append(f"{hours}h")
        parts.append(f"{mins}m")
        m.uptime = " ".join(parts)

        with self._lock:
            self._latest = m
            self._history.append(m)
        return m

    @property
    def latest(self) -> SystemMetrics:
        with self._lock:
            return self._latest

    @property
    def history(self) -> list:
        with self._lock:
            return list(self._history)

    def get_system_info(self) -> dict:
        return asdict(self._info)

    def to_dict(self) -> dict:
        m = self.latest
        return {
            "cpu": m.cpu,
            "ram": m.ram,
            "gpu": m.gpu,
            "vram": m.vram,
            "gpu_temp": m.gpu_temp,
            "gpu_power": m.gpu_power,
            "gpu_fan": m.gpu_fan,
            "gpu_name": m.gpu_name,
            "disk": m.disk,
            "network": m.network,
            "cpu_temp": m.cpu_temp,
            "uptime": m.uptime,
            "processes": m.processes,
            "timestamp": m.timestamp,
        }


# Singleton
_telemetry = TelemetryService()


def get_telemetry() -> TelemetryService:
    return _telemetry
