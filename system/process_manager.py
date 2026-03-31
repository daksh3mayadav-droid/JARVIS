"""
system/process_manager.py — Process and resource monitor for JARVIS

List, kill, start processes. Real-time CPU, RAM, GPU, Disk,
Network, Battery monitoring. Performance alerts.
"""

from __future__ import annotations

import subprocess
import time
from typing import Optional

import psutil

try:
    import GPUtil
    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False

from utils.helpers import format_file_size, format_uptime
from utils.logger import get_logger

log = get_logger("system.process_manager")


class ProcessManager:
    """
    Process manager and system resource monitor.

    Provides real-time monitoring of CPU, RAM, GPU, Disk,
    Network, and Battery. Can list, start, and terminate processes.
    """

    def __init__(self) -> None:
        """Initialize the process manager."""
        self._net_io_prev = psutil.net_io_counters()
        self._net_time_prev = time.time()
        log.info("ProcessManager initialized.")

    # ─── Process Operations ───────────────────────────────────────────────

    def list_processes(self, sort_by: str = "cpu", limit: int = 30) -> list[dict]:
        """
        List running processes.

        Args:
            sort_by: Sort field: 'cpu', 'memory', 'name', 'pid'.
            limit: Maximum number of results.

        Returns:
            List of process dicts with: pid, name, cpu_pct, mem_pct, status.
        """
        processes = []
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status"]
        ):
            try:
                info = proc.info
                processes.append({
                    "pid": info["pid"],
                    "name": info["name"] or "",
                    "cpu_pct": round(info["cpu_percent"] or 0, 1),
                    "mem_pct": round(info["memory_percent"] or 0, 1),
                    "status": info["status"] or "",
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        sort_map = {
            "cpu": lambda p: p["cpu_pct"],
            "memory": lambda p: p["mem_pct"],
            "name": lambda p: p["name"].lower(),
            "pid": lambda p: p["pid"],
        }
        key = sort_map.get(sort_by, sort_map["cpu"])
        processes.sort(key=key, reverse=(sort_by not in ("name",)))
        return processes[:limit]

    def find_process(self, name: str) -> list[dict]:
        """
        Find processes by name (case-insensitive substring match).

        Args:
            name: Process name to search.

        Returns:
            List of matching process dicts.
        """
        name_lower = name.lower()
        results = []
        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                if name_lower in (proc.info["name"] or "").lower():
                    results.append({
                        "pid": proc.info["pid"],
                        "name": proc.info["name"],
                        "status": proc.info["status"],
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return results

    def kill_process(self, identifier: "str | int") -> bool:
        """
        Kill a process by name or PID.

        Args:
            identifier: Process name (kills first match) or PID integer.

        Returns:
            True if process was killed.
        """
        try:
            if isinstance(identifier, int) or str(identifier).isdigit():
                pid = int(identifier)
                proc = psutil.Process(pid)
                proc.kill()
                log.info("Killed process PID %d", pid)
                return True
            else:
                # Kill by name
                killed = 0
                for proc in psutil.process_iter(["pid", "name"]):
                    try:
                        if identifier.lower() in (proc.info["name"] or "").lower():
                            proc.kill()
                            killed += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                log.info("Killed %d process(es) named '%s'", killed, identifier)
                return killed > 0
        except Exception as exc:  # noqa: BLE001
            log.error("Kill process failed: %s", exc)
            return False

    def start_process(self, command: str, shell: bool = True) -> Optional[int]:
        """
        Start a new process.

        Args:
            command: Command string or executable path.
            shell: If True, use shell=True.

        Returns:
            PID of started process or None on failure.
        """
        try:
            proc = subprocess.Popen(
                command,
                shell=shell,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, "DETACHED_PROCESS") else 0,
            )
            log.info("Started process: %s (PID %d)", command[:50], proc.pid)
            return proc.pid
        except Exception as exc:  # noqa: BLE001
            log.error("Start process failed: %s", exc)
            return None

    # ─── Resource Monitoring ──────────────────────────────────────────────

    def get_cpu(self) -> dict:
        """
        Return current CPU metrics.

        Returns:
            Dict with percent, count (logical), freq_mhz, per_core.
        """
        freq = psutil.cpu_freq()
        return {
            "percent": psutil.cpu_percent(interval=0.5),
            "count_logical": psutil.cpu_count(logical=True),
            "count_physical": psutil.cpu_count(logical=False),
            "freq_mhz": round(freq.current, 1) if freq else 0,
            "per_core": psutil.cpu_percent(interval=0.1, percpu=True),
        }

    def get_ram(self) -> dict:
        """
        Return current RAM metrics.

        Returns:
            Dict with total, used, available, percent.
        """
        vm = psutil.virtual_memory()
        return {
            "total": vm.total,
            "used": vm.used,
            "available": vm.available,
            "percent": vm.percent,
            "total_human": format_file_size(vm.total),
            "used_human": format_file_size(vm.used),
            "available_human": format_file_size(vm.available),
        }

    def get_gpu(self) -> list[dict]:
        """
        Return GPU metrics (GTX 1650 via GPUtil).

        Returns:
            List of GPU dicts with name, load_pct, memory_used_mb,
            memory_total_mb, temperature_c.
        """
        if not GPUTIL_AVAILABLE:
            return [{"error": "GPUtil not available"}]
        try:
            gpus = GPUtil.getGPUs()
            result = []
            for gpu in gpus:
                result.append({
                    "id": gpu.id,
                    "name": gpu.name,
                    "load_pct": round(gpu.load * 100, 1),
                    "memory_used_mb": round(gpu.memoryUsed, 1),
                    "memory_total_mb": round(gpu.memoryTotal, 1),
                    "memory_free_mb": round(gpu.memoryFree, 1),
                    "temperature_c": gpu.temperature,
                    "driver": gpu.driver,
                })
            return result
        except Exception as exc:  # noqa: BLE001
            log.warning("GPU query failed: %s", exc)
            return [{"error": str(exc)}]

    def get_disk(self) -> list[dict]:
        """
        Return disk usage for all mounted partitions.

        Returns:
            List of partition dicts.
        """
        partitions = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                    "total_human": format_file_size(usage.total),
                    "used_human": format_file_size(usage.used),
                    "free_human": format_file_size(usage.free),
                })
            except (PermissionError, OSError):
                pass
        return partitions

    def get_network(self) -> dict:
        """
        Return network I/O and connection info.

        Returns:
            Dict with bytes_sent, bytes_recv, upload_speed, download_speed.
        """
        current_io = psutil.net_io_counters()
        now = time.time()
        elapsed = now - self._net_time_prev

        if elapsed > 0:
            upload_speed = (current_io.bytes_sent - self._net_io_prev.bytes_sent) / elapsed
            download_speed = (current_io.bytes_recv - self._net_io_prev.bytes_recv) / elapsed
        else:
            upload_speed = download_speed = 0

        self._net_io_prev = current_io
        self._net_time_prev = now

        return {
            "bytes_sent": current_io.bytes_sent,
            "bytes_recv": current_io.bytes_recv,
            "upload_speed": format_file_size(int(upload_speed)) + "/s",
            "download_speed": format_file_size(int(download_speed)) + "/s",
            "connections": len(psutil.net_connections()),
        }

    def get_battery(self) -> Optional[dict]:
        """
        Return battery status.

        Returns:
            Dict with percent, charging, time_left or None if no battery.
        """
        battery = psutil.sensors_battery()
        if not battery:
            return None

        time_left = None
        if battery.secsleft > 0 and battery.secsleft != psutil.POWER_TIME_UNLIMITED:
            mins = battery.secsleft // 60
            time_left = f"{mins // 60}h {mins % 60}m"

        return {
            "percent": battery.percent,
            "charging": battery.power_plugged,
            "time_left": time_left,
            "status": "Charging" if battery.power_plugged else "Discharging",
        }

    def get_system_info(self) -> dict:
        """
        Return a comprehensive system snapshot.

        Returns:
            Dict combining CPU, RAM, GPU, disk, network, battery, uptime.
        """
        boot_time = psutil.boot_time()
        uptime_secs = time.time() - boot_time

        return {
            "cpu": self.get_cpu(),
            "ram": self.get_ram(),
            "gpu": self.get_gpu(),
            "disk": self.get_disk(),
            "network": self.get_network(),
            "battery": self.get_battery(),
            "uptime": format_uptime(uptime_secs),
            "process_count": len(list(psutil.process_iter())),
        }

    def check_alerts(self) -> list[str]:
        """
        Check for performance alert conditions.

        Returns:
            List of alert strings (empty if all OK).
        """
        alerts = []
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent

        if cpu > 90:
            alerts.append(f"⚠️  High CPU usage: {cpu:.0f}%")
        if ram > 90:
            alerts.append(f"⚠️  High RAM usage: {ram:.0f}%")

        battery = psutil.sensors_battery()
        if battery and not battery.power_plugged and battery.percent < 15:
            alerts.append(f"⚠️  Low battery: {battery.percent:.0f}% — plug in!")

        if GPUTIL_AVAILABLE:
            for gpu in GPUtil.getGPUs():
                if gpu.temperature > 85:
                    alerts.append(f"🔥 GPU temp high: {gpu.temperature}°C")

        return alerts

    def get_uptime(self) -> str:
        """Return system uptime as a human-readable string."""
        return format_uptime(time.time() - psutil.boot_time())
