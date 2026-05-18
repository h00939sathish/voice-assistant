import platform
import socket
from typing import Any

import psutil

from skills.base_skill import BaseSkill, skill


@skill(
    name="system_monitor",
    keywords=[
        "cpu usage",
        "memory usage",
        "ram usage",
        "battery level",
        "battery status",
        "system stats",
        "computer health",
        "disk space",
        "storage space",
        "internet connection",
        "ip address",
    ],
    description="Monitor system health: CPU, RAM, Battery, Disk, Network",
)
class SystemMonitorSkill(BaseSkill):
    """
    Skill for monitoring system resources and health.
    """

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        text_lower = text.lower()

        # Route to specific checks
        if "cpu" in text_lower or "processor" in text_lower:
            return self._check_cpu()

        if "memory" in text_lower or "ram" in text_lower:
            return self._check_memory()

        if "battery" in text_lower or "power" in text_lower:
            return self._check_battery()

        if "disk" in text_lower or "storage" in text_lower or "space" in text_lower:
            return self._check_disk()

        if "internet" in text_lower or "connection" in text_lower or "ip" in text_lower:
            return self._check_network()

        # Default: Full Report
        return self._full_report()

    def _check_cpu(self) -> str:
        percent = psutil.cpu_percent(interval=0.5)
        freq = psutil.cpu_freq()

        msg = f"CPU usage is at {percent}%."
        if freq:
            msg += f" Current frequency is {freq.current:.0f}MHz."

        if percent > 80:
            msg += " Your computer is working quite hard right now."
        return msg

    def _check_memory(self) -> str:
        mem = psutil.virtual_memory()

        used_gb = mem.used / (1024**3)
        total_gb = mem.total / (1024**3)
        percent = mem.percent

        return f"RAM usage is at {percent}%. You are using {used_gb:.1f}GB out of {total_gb:.1f}GB."

    def _check_battery(self) -> str:
        if not hasattr(psutil, "sensors_battery"):
            return "I cannot access battery information on this device."

        battery = psutil.sensors_battery()
        if not battery:
            return "No battery detected. You are likely on AC power."

        plugged = battery.power_plugged
        percent = battery.percent

        status = "charging" if plugged else "discharging"
        msg = f"Battery is at {percent}% and {status}."

        if not plugged:
            # Estimate time left
            left_mins = battery.secsleft / 60
            if left_mins > 0 and left_mins < 600:  # reasonable limits
                hours = int(left_mins // 60)
                mins = int(left_mins % 60)
                msg += f" You have about {hours}h {mins}m remaining."

        return msg

    def _check_disk(self) -> str:
        # Check primary disk (C: on Windows, / on Unix)
        path = "C:\\" if platform.system() == "Windows" else "/"
        try:
            usage = psutil.disk_usage(path)
            free_gb = usage.free / (1024**3)
            total_gb = usage.total / (1024**3)
            percent = usage.percent

            return f"You have {free_gb:.1f}GB free out of {total_gb:.1f}GB on your main drive ({percent}% used)."
        except Exception:
            return "I couldn't check the disk space."

    def _check_network(self) -> str:
        # Check connectivity
        try:
            # Simple ping check logic (or just IP check)
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)

            # Use external check for internet?
            # For now, just local IP
            return f"Your local IP address is {ip_address}."
        except Exception:
            return "I'm having trouble retrieving network details."

    def _full_report(self) -> str:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent

        battery_msg = ""
        if hasattr(psutil, "sensors_battery"):
            battery = psutil.sensors_battery()
            if battery:
                battery_msg = f", Battery: {battery.percent}%"

        return f"System Status: CPU {cpu}%, RAM {mem}%{battery_msg}."
