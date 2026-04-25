"""
Waifu Skill - Launch Desktop Waifu visual avatar interface

ARCHIVED: Not part of core skill set. Can be re-enabled for fun features.
"""
import logging
import os
import subprocess
import sys
from typing import Any

# Temporarily disable - skill not part of core
_enabled = False

from skills.base_skill import BaseSkill, skill

logger = logging.getLogger(__name__)

if _enabled:

@skill(
    name="waifu",
    keywords=["launch waifu", "start avatar", "open waifu", "visual interface", "enable waifu", "show avatar"],
    description="Launch the Desktop Waifu visual avatar interface",
    priority=3
)
class WaifuSkill(BaseSkill):
    """Launches the Desktop Waifu interface (VTube Studio integration)."""

    def __init__(self):
        super().__init__()
        self.process = None

    async def handle(self, query: str, context: dict[str, Any]) -> str | None:
        if self.process and self.process.poll() is None:
            return "The Waifu interface is already running."

        base_dir = os.getcwd()
        script_path = os.path.join(base_dir, "external_tools", "desktop-waifu", "waifu", "Src", "jarvis_runner.py")

        if not os.path.exists(script_path):
            return "I cannot find the Waifu runner script. Please ensure 'desktop-waifu' is installed in 'external_tools'."

        try:
            cwd = os.path.dirname(script_path)
            python_exe = sys.executable
            self.process = subprocess.Popen(
                [python_exe, "jarvis_runner.py"],
                cwd=cwd,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                shell=False
            )
            return "Launching Desktop Waifu interface... Please ensure VTube Studio is running!"
        except Exception as e:
            logger.error(f"Failed to launch waifu: {e}")
            return f"Error launching interface: {e}"
