"""
interface/text_interface.py — Rich terminal UI for JARVIS

Boot splash, color-coded I/O, status bar, command history,
progress bars, dashboard view.
"""

from __future__ import annotations

import sys
import time
from typing import Callable, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.layout import Layout
    from rich.live import Live
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from utils.logger import get_logger
from utils.helpers import get_config

log = get_logger("interface.text")

# ─── ASCII Art ────────────────────────────────────────────────────────────────

JARVIS_ASCII = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
"""

TAGLINE = "Just A Rather Very Intelligent System — TARS Edition"


class TextInterface:
    """
    Rich-based terminal interface for JARVIS.

    Provides:
    - Animated boot splash
    - Color-coded output (user=cyan, jarvis=green, system=yellow, error=red)
    - Live status bar with CPU/RAM/GPU/Battery
    - Command history with ↑/↓ navigation
    - Progress indicators for long tasks
    """

    # Color scheme
    COLORS = {
        "user": "bold cyan",
        "jarvis": "bold green",
        "system": "yellow",
        "error": "bold red",
        "dim": "dim white",
        "highlight": "bold white",
        "warning": "bold yellow",
    }

    def __init__(self) -> None:
        """Initialize the text interface."""
        if RICH_AVAILABLE:
            self._console = Console()
        else:
            self._console = None

        self._history: list[str] = []
        self._history_idx = 0
        config = get_config()
        self._jarvis_name = config.get("jarvis", {}).get("name", "JARVIS")
        log.info("TextInterface initialized.")

    # ─── Boot ─────────────────────────────────────────────────────────────

    def show_boot_screen(self) -> None:
        """Display the JARVIS boot splash screen."""
        if not RICH_AVAILABLE:
            print(JARVIS_ASCII)
            print(TAGLINE)
            return

        self._console.clear()
        self._console.print(
            Panel(
                Text(JARVIS_ASCII, style="bold blue") + Text(f"\n  {TAGLINE}", style="italic cyan"),
                border_style="bold blue",
                padding=(1, 4),
            )
        )

        # Boot sequence animation
        boot_steps = [
            ("Initializing core systems", 0.3),
            ("Loading memory database", 0.2),
            ("Starting voice subsystem", 0.3),
            ("Connecting to LLM engine", 0.4),
            ("Activating vision layer", 0.2),
            ("All systems nominal", 0.1),
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold green]{task.description}"),
            BarColumn(),
            console=self._console,
        ) as progress:
            task = progress.add_task("Booting…", total=len(boot_steps))
            for step_name, delay in boot_steps:
                progress.update(task, description=step_name)
                time.sleep(delay)
                progress.advance(task)

        self.system_message(f"✅ {self._jarvis_name} online. Say 'Jarvis' or type below.")

    # ─── Output Methods ───────────────────────────────────────────────────

    def print_user(self, text: str) -> None:
        """Display user input."""
        if RICH_AVAILABLE:
            self._console.print(
                Text(f"  You  » ", style=self.COLORS["user"]) +
                Text(text, style="white"),
            )
        else:
            print(f"You: {text}")

    def print_jarvis(self, text: str) -> None:
        """Display JARVIS response."""
        if RICH_AVAILABLE:
            self._console.print(
                Text(f"JARVIS » ", style=self.COLORS["jarvis"]) +
                Text(text, style="white"),
            )
        else:
            print(f"JARVIS: {text}")

    def system_message(self, text: str) -> None:
        """Display a system/status message."""
        if RICH_AVAILABLE:
            self._console.print(Text(f"  ⚡ {text}", style=self.COLORS["system"]))
        else:
            print(f"[SYSTEM] {text}")

    def error_message(self, text: str) -> None:
        """Display an error message."""
        if RICH_AVAILABLE:
            self._console.print(Text(f"  ✗ {text}", style=self.COLORS["error"]))
        else:
            print(f"[ERROR] {text}")

    def warning_message(self, text: str) -> None:
        """Display a warning message."""
        if RICH_AVAILABLE:
            self._console.print(Text(f"  ⚠ {text}", style=self.COLORS["warning"]))
        else:
            print(f"[WARNING] {text}")

    def print_plan(self, plan_text: str) -> None:
        """Display an execution plan in a bordered panel."""
        if RICH_AVAILABLE:
            self._console.print(
                Panel(
                    Text(plan_text, style="dim white"),
                    title="[bold yellow]📋 Execution Plan[/]",
                    border_style="yellow",
                )
            )
        else:
            print(plan_text)

    def print_table(self, title: str, headers: list[str], rows: list[list]) -> None:
        """
        Display a formatted table.

        Args:
            title: Table title.
            headers: Column header names.
            rows: List of row lists.
        """
        if RICH_AVAILABLE:
            table = Table(title=title, box=box.ROUNDED, border_style="dim blue")
            for h in headers:
                table.add_column(h, style="white")
            for row in rows:
                table.add_row(*[str(c) for c in row])
            self._console.print(table)
        else:
            print(title)
            print("\t".join(headers))
            for row in rows:
                print("\t".join(str(c) for c in row))

    # ─── Dashboard ────────────────────────────────────────────────────────

    def show_dashboard(self, stats: dict) -> None:
        """
        Display a system dashboard panel.

        Args:
            stats: Dict with cpu_pct, ram_pct, gpu_pct, battery_pct, uptime.
        """
        if not RICH_AVAILABLE:
            print(f"CPU: {stats.get('cpu_pct', 0):.0f}%  "
                  f"RAM: {stats.get('ram_pct', 0):.0f}%  "
                  f"Battery: {stats.get('battery_pct', '?')}%")
            return

        cpu = stats.get("cpu_pct", 0)
        ram = stats.get("ram_pct", 0)
        gpu = stats.get("gpu_pct", 0)
        bat = stats.get("battery_pct", "?")
        uptime = stats.get("uptime", "?")

        def _bar(pct: float, width: int = 20) -> str:
            filled = int(pct / 100 * width)
            return "█" * filled + "░" * (width - filled)

        text = (
            f"[bold]CPU[/]  {_bar(cpu)} {cpu:5.1f}%\n"
            f"[bold]RAM[/]  {_bar(ram)} {ram:5.1f}%\n"
            f"[bold]GPU[/]  {_bar(gpu)} {gpu:5.1f}%\n"
            f"[bold]BAT[/]  {bat}%  |  Uptime: {uptime}"
        )

        self._console.print(
            Panel(
                Text.from_markup(text),
                title="[bold blue]⚡ System Status[/]",
                border_style="dim blue",
            )
        )

    # ─── Progress ─────────────────────────────────────────────────────────

    def progress_context(self, description: str = "Working…"):
        """
        Return a Rich Progress context manager for long tasks.

        Usage:
            with ui.progress_context("Scanning…") as prog:
                task = prog.add_task("Files", total=100)
                prog.update(task, advance=10)
        """
        if RICH_AVAILABLE:
            return Progress(
                SpinnerColumn(),
                TextColumn("[bold green]{task.description}"),
                BarColumn(),
                console=self._console,
            )
        return _DummyProgress()

    # ─── Input ────────────────────────────────────────────────────────────

    def get_input(self, prompt: str = ">> ") -> str:
        """
        Read user input with optional prompt.

        Args:
            prompt: Input prompt string.

        Returns:
            Stripped input text.
        """
        try:
            if RICH_AVAILABLE:
                self._console.print(Text(prompt, style=self.COLORS["user"]), end="")
            text = input("" if RICH_AVAILABLE else prompt).strip()
            if text:
                self._history.append(text)
                self._history_idx = len(self._history)
            return text
        except (EOFError, KeyboardInterrupt):
            return ""

    # ─── Help ─────────────────────────────────────────────────────────────

    def show_help(self) -> None:
        """Display the help panel with all available commands."""
        commands = [
            ("Voice", "Say 'Jarvis [command]'", "Wake word activates full listening"),
            ("Text", "Type anything and press Enter", "Direct text input"),
            ("screenshot", "Take a screenshot", "Saves to data/screenshots/"),
            ("status", "Show system stats", "CPU, RAM, GPU, Battery"),
            ("help", "Show this panel", ""),
            ("clear", "Clear terminal", ""),
            ("quit / exit", "Shutdown JARVIS", ""),
            ("open [app]", "Launch an application", "e.g. 'open chrome'"),
            ("find [name]", "Search for a file", "e.g. 'find report.pdf'"),
            ("settings [page]", "Open Windows settings", "e.g. 'settings wifi'"),
            ("plan [goal]", "Create and execute a plan", "Multi-step autonomous task"),
        ]
        if RICH_AVAILABLE:
            table = Table(
                title="JARVIS Command Reference",
                box=box.ROUNDED,
                border_style="blue",
            )
            table.add_column("Command", style="bold cyan", no_wrap=True)
            table.add_column("Description", style="white")
            table.add_column("Notes", style="dim white")
            for cmd, desc, note in commands:
                table.add_row(cmd, desc, note)
            self._console.print(table)
        else:
            print("\nCommands:")
            for cmd, desc, _ in commands:
                print(f"  {cmd:<20} {desc}")

    def clear(self) -> None:
        """Clear the terminal screen."""
        if RICH_AVAILABLE:
            self._console.clear()
        else:
            print("\033[2J\033[H", end="")


# ─── Fallback Dummy Progress ──────────────────────────────────────────────────

class _DummyProgress:
    """No-op progress context when Rich is unavailable."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def add_task(self, description: str, total: int = 100) -> int:  # noqa: ARG002
        return 0

    def update(self, task_id: int, **kwargs) -> None:
        pass

    def advance(self, task_id: int, advance: float = 1) -> None:
        pass
