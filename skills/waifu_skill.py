import logging
import os
import subprocess
from typing import Dict, Any
from skills.base_skill import BaseSkill

logger = logging.getLogger(__name__)

class WaifuSkill(BaseSkill):
    """
    Skill to launch the Desktop Waifu interface (VTube Studio integration).
    """
    
    def __init__(self):
        self.name = "waifu_skill"
        self.description = "Launch the visual avatar interface (Desktop Waifu)"
        self.keywords = [
            "launch waifu", "start avatar", "open waifu", "start visual interface",
            "enable waifu", "show avatar"
        ]
        self.process = None

    async def handle(self, query: str, context: Dict[str, Any] = None) -> str:
        if self.process and self.process.poll() is None:
            return "The Waifu interface is already running."
            
        # Path to the runner script
        base_dir = os.getcwd()
        script_path = os.path.join(base_dir, "external_tools", "desktop-waifu", "waifu", "Src", "jarvis_runner.py")
        
        if not os.path.exists(script_path):
            return "I cannot find the Waifu runner script. Please ensure 'desktop-waifu' is installed in 'external_tools'."

        try:
            # Run in a separate thread/process so it doesn't block JARVIS
            # We use Popen to keep it running
            cwd = os.path.dirname(script_path)
            
            # We need to run it with the same python interpreter or the one with dependencies
            # Assuming dependencies are installed in current env
            python_exe = sys.executable
            
            self.process = subprocess.Popen(
                [python_exe, "jarvis_runner.py"],
                cwd=cwd,
                creationflags=subprocess.CREATE_NEW_CONSOLE, # Open in new window
                shell=False
            )
            
            return "Launching Desktop Waifu interface... Please ensure VTube Studio is running!"
            
        except Exception as e:
            logger.error(f"Failed to launch waifu: {e}")
            return f"Error launching interface: {e}"

import sys
