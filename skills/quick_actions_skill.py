
import os
import ctypes
import platform
from typing import Dict, Any
from skills.base_skill import BaseSkill, skill

@skill(
    name="quick_actions",
    keywords=[
        "lock computer", "lock pc", "lock screen",
        "go to sleep", "put computer to sleep", "sleep mode",
        "shutdown", "restart computer", "reboot",
        "mute volume", "unmute volume", "max volume"
    ],
    description="Quick system actions: Lock, Sleep, Shutdown, Mute"
)
class QuickActionsSkill(BaseSkill):
    """
    Skill for quick system actions.
    """
    
    async def handle(self, text: str, context: Dict[str, Any]) -> str:
        text_lower = text.lower()
        
        if "lock" in text_lower:
            return self._lock_computer()
            
        if "sleep" in text_lower:
            return self._sleep_computer()
            
        if "shutdown" in text_lower:
            # Dangerous, ask for confirmation? For now, just warn.
            return "I can shutdown, but I need you to confirm. Say 'Execute shutdown protocol'."
            
        if "restart" in text_lower or "reboot" in text_lower:
            return "To restart, please say 'Execute restart protocol'."

        # Volume controls (Windows-specific mainly)
        if "mute" in text_lower or "unmute" in text_lower:
            return self._toggle_mute()
            
        return "I didn't understand the system action."

    def _lock_computer(self) -> str:
        system = platform.system()
        try:
            if system == "Windows":
                ctypes.windll.user32.LockWorkStation()
            elif system == "Darwin": # macOS
                os.system("pmset displaysleepnow")
            elif system == "Linux":
                os.system("xdg-screensaver lock")
            return "Locking your computer."
        except Exception as e:
            return f"Failed to lock: {e}"

    def _sleep_computer(self) -> str:
        system = platform.system()
        try:
            if system == "Windows":
                # Rundll32.exe powrprof.dll,SetSuspendState 0,1,0
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            elif system == "Darwin":
                os.system("pmset sleepnow")
            elif system == "Linux":
                os.system("systemctl suspend")
            return "Going to sleep. Goodnight!"
        except Exception as e:
            return f"Failed to sleep: {e}"
            
    def _toggle_mute(self) -> str:
        # Simplest way on Windows without heavy deps is sending VK_VOLUME_MUTE key
        system = platform.system()
        if system == "Windows":
            try:
                # 0xAD is VK_VOLUME_MUTE
                ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0) # Key up
                return "Toggled mute."
            except Exception as e:
                return f"Failed to toggle mute using ctypes: {e}"
        return "I can only toggle mute on Windows currently."
