"""
Desktop Agent Package for JARVIS Assistant

Provides full desktop automation capabilities including:
- Mouse control (move, click, double-click, right-click, drag)
- Keyboard control (type, press keys, hotkeys)
- Window management (open, close, focus, move, resize)
- File operations (search, open, list folders)
- Clipboard operations (copy, paste)
- Screen vision (screenshots, OCR, image detection)
- Browser automation
- Workflow execution
- Safety features (emergency stop, logging, timeouts)

Usage:
    from assistant.desktop_agent import DesktopAgent

    agent = DesktopAgent()
    agent.click(500, 300)
    agent.type_text("Hello world")
    agent.open_app("chrome")
"""

from .browser_auto import BrowserAutomation
from .core import DesktopAgent
from .safety import EmergencyStop, SafetyLayer
from .vision import ScreenVision
from .workflows import WorkflowEngine

__version__ = "1.0.0"

__all__ = [
    "DesktopAgent",
    "SafetyLayer",
    "EmergencyStop",
    "WorkflowEngine",
    "ScreenVision",
    "BrowserAutomation",
]


async def get_desktop_agent() -> DesktopAgent:
    """Get a shared DesktopAgent instance."""
    return DesktopAgent()
