"""
automation/__init__.py — Automation package for JARVIS
"""

from automation.task_automator import TaskAutomator
from automation.browser_control import BrowserControl

__all__ = ["TaskAutomator", "BrowserControl"]
