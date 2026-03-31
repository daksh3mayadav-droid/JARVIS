"""
system/windows_navigator.py — Windows 11 settings navigator for JARVIS

Opens any Windows Settings page via ms-settings: URIs.
Controls WiFi, Bluetooth, volume, brightness, night light, etc.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Optional

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

from utils.logger import get_logger

log = get_logger("system.windows_navigator")

# ─── ms-settings: URI Map ─────────────────────────────────────────────────────

SETTINGS_MAP: dict[str, str] = {
    # System
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "notifications": "ms-settings:notifications",
    "focus": "ms-settings:quiethours",
    "power": "ms-settings:powersleep",
    "battery": "ms-settings:batterysaver",
    "storage": "ms-settings:storagesense",
    "multitasking": "ms-settings:multitasking",
    "clipboard": "ms-settings:clipboard",
    "about": "ms-settings:about",
    # Devices
    "bluetooth": "ms-settings:bluetooth",
    "printers": "ms-settings:printers",
    "mouse": "ms-settings:mousetouchpad",
    "touchpad": "ms-settings:devices-touchpad",
    "typing": "ms-settings:typing",
    "autoplay": "ms-settings:autoplay",
    "usb": "ms-settings:usb",
    # Network
    "wifi": "ms-settings:network-wifi",
    "ethernet": "ms-settings:network-ethernet",
    "vpn": "ms-settings:network-vpn",
    "airplane mode": "ms-settings:network-airplanemode",
    "mobile hotspot": "ms-settings:network-mobilehotspot",
    "proxy": "ms-settings:network-proxy",
    "network": "ms-settings:network",
    # Personalization
    "background": "ms-settings:personalization-background",
    "colors": "ms-settings:colors",
    "lock screen": "ms-settings:lockscreen",
    "themes": "ms-settings:themes",
    "fonts": "ms-settings:fonts",
    "taskbar": "ms-settings:taskbar",
    "start menu": "ms-settings:startmenu",
    # Apps
    "apps": "ms-settings:appsfeatures",
    "default apps": "ms-settings:defaultapps",
    "optional features": "ms-settings:optionalfeatures",
    # Accounts
    "accounts": "ms-settings:yourinfo",
    "email": "ms-settings:emailandaccounts",
    "sign-in": "ms-settings:signinoptions",
    "family": "ms-settings:family-group",
    # Time
    "time": "ms-settings:dateandtime",
    "region": "ms-settings:regionformatting",
    "language": "ms-settings:regionlanguage",
    # Accessibility
    "accessibility": "ms-settings:easeofaccess",
    "narrator": "ms-settings:easeofaccess-narrator",
    "magnifier": "ms-settings:easeofaccess-magnifier",
    "color filters": "ms-settings:easeofaccess-colorfilter",
    # Privacy
    "privacy": "ms-settings:privacy",
    "camera privacy": "ms-settings:privacy-webcam",
    "microphone privacy": "ms-settings:privacy-microphone",
    "location": "ms-settings:privacy-location",
    # Update & Security
    "update": "ms-settings:windowsupdate",
    "windows update": "ms-settings:windowsupdate",
    "defender": "ms-settings:windowsdefender",
    "firewall": "ms-settings:windowsdefender",
    "backup": "ms-settings:backup",
    "recovery": "ms-settings:recovery",
    "developer": "ms-settings:developers",
    # Gaming
    "game mode": "ms-settings:gaming-gamemode",
    "xbox": "ms-settings:gaming-xboxnetworking",
}


class WindowsNavigator:
    """
    Navigate Windows 11 settings and quick-action controls.

    Uses ms-settings: URI scheme for direct settings page access,
    and system commands / PowerShell for hardware controls.
    """

    def __init__(self) -> None:
        """Initialize the Windows navigator."""
        log.info("WindowsNavigator initialized.")

    # ─── Settings Navigation ──────────────────────────────────────────────

    def open_settings(self, page: str) -> bool:
        """
        Open a Windows Settings page.

        Args:
            page: Setting name (e.g. 'wifi', 'display', 'bluetooth').
                  Case-insensitive. Falls back to fuzzy search.

        Returns:
            True if the URI was launched.
        """
        page_lower = page.lower().strip()

        # Exact match
        uri = SETTINGS_MAP.get(page_lower)

        # Substring search
        if not uri:
            for key, val in SETTINGS_MAP.items():
                if page_lower in key:
                    uri = val
                    break

        if not uri:
            log.warning("Unknown settings page: %s", page)
            # Open generic settings as fallback
            uri = "ms-settings:"

        return self._launch_uri(uri)

    def open_settings_uri(self, uri: str) -> bool:
        """
        Launch a raw ms-settings: URI.

        Args:
            uri: Full URI string (e.g. 'ms-settings:display').

        Returns:
            True on success.
        """
        return self._launch_uri(uri)

    def list_settings_pages(self) -> list[str]:
        """Return all known settings page names."""
        return sorted(SETTINGS_MAP.keys())

    # ─── Quick Actions ────────────────────────────────────────────────────

    def set_volume(self, level: int) -> bool:
        """
        Set system volume (0-100).

        Args:
            level: Volume level 0-100.

        Returns:
            True on success.
        """
        level = max(0, min(100, level))
        try:
            # PowerShell: set volume via COM
            ps_cmd = (
                f"$obj = New-Object -ComObject WScript.Shell; "
                f"1..50 | % {{ $obj.SendKeys([char]174) }}; "
                f"1..{level // 2} | % {{ $obj.SendKeys([char]175) }}"
            )
            subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True,
                timeout=5,
            )
            log.info("Volume set to %d%%", level)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Set volume failed: %s", exc)
            return False

    def get_volume(self) -> Optional[int]:
        """
        Get current system volume level.

        Returns:
            Volume 0-100 or None on failure.
        """
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-AudioDevice -Playback).Volume * 100"],
                capture_output=True, text=True, timeout=5,
            )
            return int(float(result.stdout.strip()))
        except Exception:  # noqa: BLE001
            return None

    def mute_volume(self) -> bool:
        """Toggle mute."""
        try:
            ps_cmd = (
                "$obj = New-Object -ComObject WScript.Shell; "
                "$obj.SendKeys([char]173)"
            )
            subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, timeout=5,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Mute failed: %s", exc)
            return False

    def set_brightness(self, level: int) -> bool:
        """
        Set display brightness (0-100). Requires admin on some systems.

        Args:
            level: Brightness 0-100.

        Returns:
            True on success.
        """
        level = max(0, min(100, level))
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                 f".WmiSetBrightness(1,{level})"],
                capture_output=True, timeout=5,
            )
            log.info("Brightness set to %d%%", level)
            return result.returncode == 0
        except Exception as exc:  # noqa: BLE001
            log.error("Set brightness failed: %s", exc)
            return False

    def toggle_wifi(self) -> bool:
        """Toggle WiFi adapter."""
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-NetAdapter | Where-Object {$_.Name -like '*Wi-Fi*' -or $_.Name -like '*Wireless*'} | "
                 "% { if ($_.Status -eq 'Up') { Disable-NetAdapter -Name $_.Name -Confirm:$false } "
                 "else { Enable-NetAdapter -Name $_.Name } }"],
                capture_output=True, timeout=10,
            )
            log.info("WiFi toggled.")
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Toggle WiFi failed: %s", exc)
            return False

    def toggle_bluetooth(self) -> bool:
        """Toggle Bluetooth."""
        try:
            ps_cmd = (
                "If ((Get-PnpDevice -FriendlyName 'Bluetooth*' | Select -First 1).Status -eq 'OK') "
                "{ Get-PnpDevice -FriendlyName 'Bluetooth*' | Disable-PnpDevice -Confirm:$false } "
                "Else { Get-PnpDevice -FriendlyName 'Bluetooth*' | Enable-PnpDevice -Confirm:$false }"
            )
            subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, timeout=10,
            )
            log.info("Bluetooth toggled.")
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Toggle Bluetooth failed: %s", exc)
            return False

    def toggle_night_light(self) -> bool:
        """Toggle Windows Night Light."""
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "Add-Type -AssemblyName System.Windows.Forms; "
                 "[System.Windows.Forms.SendKeys]::SendWait('')"],
                capture_output=True, timeout=5,
            )
            # Alternative: toggle via registry
            log.info("Night light toggle attempted.")
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Night light toggle failed: %s", exc)
            return False

    def open_task_manager(self) -> bool:
        """Open Windows Task Manager."""
        return self._launch_uri("taskmgr.exe")

    def open_control_panel(self, panel: Optional[str] = None) -> bool:
        """
        Open Control Panel or a specific panel.

        Args:
            panel: Optional CPL filename (e.g. 'appwiz.cpl').

        Returns:
            True on success.
        """
        if panel:
            return self._run_command(f"control {panel}")
        return self._run_command("control")

    def shutdown(self, delay_seconds: int = 0) -> bool:
        """Schedule system shutdown."""
        return self._run_command(f"shutdown /s /t {delay_seconds}")

    def restart(self, delay_seconds: int = 0) -> bool:
        """Schedule system restart."""
        return self._run_command(f"shutdown /r /t {delay_seconds}")

    def sleep(self) -> bool:
        """Put system to sleep."""
        return self._run_command("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

    def lock_screen(self) -> bool:
        """Lock the Windows session."""
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Lock screen failed: %s", exc)
            return self._run_command("rundll32.exe user32.dll,LockWorkStation")

    def open_search(self, query: str = "") -> bool:
        """Open Windows Search with an optional query."""
        if PYAUTOGUI_AVAILABLE and query:
            import pyautogui
            pyautogui.hotkey("win", "s")
            time.sleep(0.5)
            pyautogui.typewrite(query, interval=0.05)
            return True
        return self._run_command("start ms-search:")

    def get_wifi_ssid(self) -> Optional[str]:
        """Return the currently connected WiFi SSID."""
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    return line.split(":", 1)[-1].strip()
        except Exception as exc:  # noqa: BLE001
            log.error("Get WiFi SSID failed: %s", exc)
        return None

    # ─── Internal ─────────────────────────────────────────────────────────

    def _launch_uri(self, uri: str) -> bool:
        """Launch a URI via os.startfile or subprocess."""
        try:
            if hasattr(os, "startfile"):
                os.startfile(uri)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["start", uri], shell=True)
            log.info("Launched URI: %s", uri)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("URI launch failed: %s — %s", uri, exc)
            return False

    def _run_command(self, cmd: str) -> bool:
        """Run a shell command."""
        try:
            subprocess.Popen(cmd, shell=True)
            log.info("Ran command: %s", cmd)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Command failed: %s — %s", cmd, exc)
            return False
