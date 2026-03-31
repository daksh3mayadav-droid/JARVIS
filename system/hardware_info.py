"""
system/hardware_info.py — Complete hardware specs for JARVIS

CPU, GPU, RAM, Storage, Battery, Display, Network, OS info.
Optimized for HP Pavilion Gaming 15 (Ryzen 5 5600H / GTX 1650).
"""

from __future__ import annotations

import platform
import socket
import subprocess
import time
from typing import Optional

import psutil

try:
    import GPUtil
    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False

from utils.helpers import format_file_size
from utils.logger import get_logger

log = get_logger("system.hardware_info")


class HardwareInfo:
    """
    Comprehensive hardware information provider.

    Returns specs and real-time metrics for CPU, GPU, RAM,
    Storage, Battery, Display, Network, and OS details.
    """

    def __init__(self) -> None:
        """Initialize hardware info collector."""
        self._os_info_cache: Optional[dict] = None
        log.info("HardwareInfo initialized.")

    # ─── CPU ──────────────────────────────────────────────────────────────

    def get_cpu_info(self) -> dict:
        """
        Return CPU specification and current usage.

        Returns:
            Dict with model, cores, threads, freq_mhz, usage_pct, per_core.
        """
        freq = psutil.cpu_freq()
        model = self._get_cpu_model()

        return {
            "model": model,
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "freq_current_mhz": round(freq.current, 1) if freq else 0,
            "freq_max_mhz": round(freq.max, 1) if freq else 0,
            "usage_pct": psutil.cpu_percent(interval=0.5),
            "per_core_pct": psutil.cpu_percent(interval=0.1, percpu=True),
        }

    def _get_cpu_model(self) -> str:
        """Return CPU model string from platform or WMI."""
        # Windows
        try:
            result = subprocess.run(
                ["wmic", "cpu", "get", "Name", "/value"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("Name="):
                    return line.split("=", 1)[-1].strip()
        except Exception:  # noqa: BLE001
            pass

        # Fallback
        return platform.processor() or "Unknown CPU"

    # ─── GPU ──────────────────────────────────────────────────────────────

    def get_gpu_info(self) -> list[dict]:
        """
        Return GPU specs and usage (via GPUtil and WMIC).

        Returns:
            List of GPU dicts with model, vram_mb, usage_pct, temp_c.
        """
        gpus = []

        # GPUtil (NVIDIA)
        if GPUTIL_AVAILABLE:
            try:
                for gpu in GPUtil.getGPUs():
                    gpus.append({
                        "id": gpu.id,
                        "name": gpu.name,
                        "vram_total_mb": round(gpu.memoryTotal, 1),
                        "vram_used_mb": round(gpu.memoryUsed, 1),
                        "vram_free_mb": round(gpu.memoryFree, 1),
                        "usage_pct": round(gpu.load * 100, 1),
                        "temperature_c": gpu.temperature,
                        "driver": gpu.driver,
                    })
                if gpus:
                    return gpus
            except Exception as exc:  # noqa: BLE001
                log.warning("GPUtil query failed: %s", exc)

        # WMIC fallback
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController",
                 "get", "Name,AdapterRAM", "/value"],
                capture_output=True, text=True, timeout=5,
            )
            name, vram = "", 0
            for line in result.stdout.splitlines():
                if line.startswith("Name="):
                    name = line.split("=", 1)[-1].strip()
                elif line.startswith("AdapterRAM=") and line.split("=", 1)[-1].strip():
                    vram = int(line.split("=", 1)[-1].strip()) // (1024 * 1024)
            if name:
                gpus.append({"name": name, "vram_total_mb": vram})
        except Exception:  # noqa: BLE001
            pass

        return gpus or [{"name": "No GPU detected", "vram_total_mb": 0}]

    # ─── RAM ──────────────────────────────────────────────────────────────

    def get_ram_info(self) -> dict:
        """
        Return RAM specs and current usage.

        Returns:
            Dict with total, used, available, percent.
        """
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "total": vm.total,
            "used": vm.used,
            "available": vm.available,
            "percent": vm.percent,
            "total_human": format_file_size(vm.total),
            "used_human": format_file_size(vm.used),
            "available_human": format_file_size(vm.available),
            "swap_total_human": format_file_size(swap.total),
            "swap_used_human": format_file_size(swap.used),
        }

    # ─── Storage ──────────────────────────────────────────────────────────

    def get_storage_info(self) -> list[dict]:
        """
        Return storage info for all drives.

        Returns:
            List of dicts per drive.
        """
        drives = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                drives.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_human": format_file_size(usage.total),
                    "used_human": format_file_size(usage.used),
                    "free_human": format_file_size(usage.free),
                    "percent_used": usage.percent,
                })
            except (PermissionError, OSError):
                pass
        return drives

    # ─── Battery ──────────────────────────────────────────────────────────

    def get_battery_info(self) -> Optional[dict]:
        """
        Return battery status.

        Returns:
            Dict or None if no battery.
        """
        battery = psutil.sensors_battery()
        if not battery:
            return None

        time_left = None
        if (
            battery.secsleft > 0
            and battery.secsleft != psutil.POWER_TIME_UNLIMITED
        ):
            mins = battery.secsleft // 60
            time_left = f"{mins // 60}h {mins % 60}m remaining"

        return {
            "percent": round(battery.percent, 1),
            "charging": battery.power_plugged,
            "time_left": time_left,
            "status": "Charging ⚡" if battery.power_plugged else "On Battery 🔋",
        }

    # ─── Display ──────────────────────────────────────────────────────────

    def get_display_info(self) -> list[dict]:
        """
        Return display resolution info.

        Returns:
            List of monitor dicts with width, height.
        """
        displays = []
        try:
            import ctypes
            user32 = ctypes.windll.user32
            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)
            displays.append({
                "index": 0,
                "width": width,
                "height": height,
                "resolution": f"{width}x{height}",
            })
        except Exception:  # noqa: BLE001
            # Fallback
            try:
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                w, h = root.winfo_screenwidth(), root.winfo_screenheight()
                root.destroy()
                displays.append({"index": 0, "width": w, "height": h, "resolution": f"{w}x{h}"})
            except Exception:  # noqa: BLE001
                displays.append({"index": 0, "resolution": "Unknown"})
        return displays

    # ─── Network ──────────────────────────────────────────────────────────

    def get_network_info(self) -> dict:
        """
        Return network adapter and connectivity info.

        Returns:
            Dict with hostname, local_ip, wifi_ssid, adapters.
        """
        info: dict = {
            "hostname": socket.gethostname(),
            "local_ip": self._get_local_ip(),
            "wifi_ssid": self._get_wifi_ssid(),
            "adapters": [],
        }

        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    info["adapters"].append({
                        "name": name,
                        "ip": addr.address,
                        "netmask": addr.netmask,
                    })

        return info

    def _get_local_ip(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:  # noqa: BLE001
            return "127.0.0.1"

    def _get_wifi_ssid(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    return line.split(":", 1)[-1].strip()
        except Exception:  # noqa: BLE001
            pass
        return None

    # ─── OS Info ──────────────────────────────────────────────────────────

    def get_os_info(self) -> dict:
        """
        Return Windows OS version and build info.

        Returns:
            Dict with system, version, build, architecture.
        """
        if self._os_info_cache:
            return self._os_info_cache

        info = {
            "system": platform.system(),
            "version": platform.version(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "uptime": self._get_uptime(),
        }

        # Windows build number
        try:
            result = subprocess.run(
                ["wmic", "os", "get", "Caption,BuildNumber,Version", "/value"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("Caption="):
                    info["windows_edition"] = line.split("=", 1)[-1].strip()
                elif line.startswith("BuildNumber="):
                    info["build_number"] = line.split("=", 1)[-1].strip()
        except Exception:  # noqa: BLE001
            pass

        self._os_info_cache = info
        return info

    def _get_uptime(self) -> str:
        from utils.helpers import format_uptime
        return format_uptime(time.time() - psutil.boot_time())

    # ─── Complete Report ──────────────────────────────────────────────────

    def full_report(self) -> dict:
        """
        Return a complete hardware + system report.

        Returns:
            Nested dict with all subsystem info.
        """
        return {
            "cpu": self.get_cpu_info(),
            "gpu": self.get_gpu_info(),
            "ram": self.get_ram_info(),
            "storage": self.get_storage_info(),
            "battery": self.get_battery_info(),
            "display": self.get_display_info(),
            "network": self.get_network_info(),
            "os": self.get_os_info(),
        }

    def summary(self) -> str:
        """
        Return a compact human-readable system summary.

        Returns:
            Multi-line string suitable for display.
        """
        cpu = self.get_cpu_info()
        ram = self.get_ram_info()
        gpus = self.get_gpu_info()
        battery = self.get_battery_info()
        net = self.get_network_info()
        os_info = self.get_os_info()

        gpu_str = ", ".join(g.get("name", "?") for g in gpus)
        bat_str = f"{battery['percent']}% ({battery['status']})" if battery else "N/A"

        lines = [
            "═══ SYSTEM SUMMARY ═══",
            f"OS:      {os_info.get('windows_edition', os_info.get('system', '?'))}",
            f"CPU:     {cpu['model']}",
            f"         {cpu['cores_physical']}P/{cpu['cores_logical']}L cores"
            f" @ {cpu['freq_current_mhz']} MHz | Usage: {cpu['usage_pct']}%",
            f"RAM:     {ram['used_human']} / {ram['total_human']} ({ram['percent']}%)",
            f"GPU:     {gpu_str}",
            f"Battery: {bat_str}",
            f"IP:      {net['local_ip']}",
            f"WiFi:    {net.get('wifi_ssid', 'Not connected')}",
            f"Uptime:  {os_info.get('uptime', '?')}",
            "═══════════════════════",
        ]
        return "\n".join(lines)
