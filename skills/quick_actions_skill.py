import ctypes
import os
import platform
import re
import secrets
import subprocess
import time
from typing import Any

from skills.base_skill import BaseSkill, skill


@skill(
    name="quick_actions",
    keywords=[
        "lock computer",
        "lock pc",
        "lock screen",
        "go to sleep",
        "put computer to sleep",
        "sleep mode",
        "shutdown",
        "restart computer",
        "reboot",
        "mute volume",
        "unmute volume",
        "max volume",
        "open app",
        "launch app",
        "start app",
        "run app",
        "open calculator",
        "open terminal",
        "open settings",
        "open explorer",
        "open file explorer",
        "open task manager",
        "open paint",
        "open word",
        "open excel",
        "open powerpoint",
    ],
    description="Quick system actions: Lock, Sleep, Shutdown, Mute, Open/Launch apps",
    priority=3,
)
class QuickActionsSkill(BaseSkill):
    """
    Skill for quick system actions.
    """

    # Common app name -> executable mapping (Windows)
    APP_MAP = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "firefox": "firefox",
        "edge": "msedge",
        "brave": "brave",
        "visual studio code": "code",
        "vs code": "code",
        "vscode": "code",
        "visual studio": "devenv",
        "notepad": "notepad",
        "calculator": "calc",
        "file explorer": "explorer",
        "explorer": "explorer",
        "spotify": "spotify",
        "discord": "discord",
        "slack": "slack",
        "terminal": "wt",
        "powershell": "powershell",
        "cmd": "cmd",
        "task manager": "taskmgr",
        "settings": "ms-settings:",
        "paint": "mspaint",
        "word": "winword",
        "excel": "excel",
        "powerpoint": "powerpnt",
    }

    CONFIRM_TIMEOUT_SECONDS = 45

    def __init__(self):
        super().__init__()
        self._pending_action: dict[str, Any] | None = None

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        text_lower = text.lower()

        if any(
            cancel in text_lower
            for cancel in ["cancel action", "abort action", "never mind"]
        ):
            return self._cancel_pending_action()

        confirmation_result = self._handle_confirmation(text_lower)
        if confirmation_result:
            return confirmation_result

        if "lock" in text_lower:
            return self._lock_computer()

        if "sleep" in text_lower:
            return self._request_confirmation("sleep")

        if "shutdown" in text_lower:
            return self._request_confirmation("shutdown")

        if "restart" in text_lower or "reboot" in text_lower:
            return self._request_confirmation("restart")

        if "mute" in text_lower or "unmute" in text_lower:
            return self._toggle_mute()

        # Open/Launch app
        if any(word in text_lower for word in ["open", "launch", "start", "run"]):
            return self._open_app(text_lower)

        return "I didn't understand the system action."

    def _open_app(self, text: str) -> str:
        """Open an application by name."""
        # Strip action/filler words token-by-token to avoid mangling app names.
        normalized = re.sub(r"[^\w\s-]", " ", text.lower())
        tokens = [
            token
            for token in normalized.split()
            if token
            not in {
                "open",
                "launch",
                "start",
                "run",
                "please",
                "can",
                "you",
                "the",
                "a",
                "an",
            }
        ]
        app_name = " ".join(tokens).strip()

        if not app_name:
            return "What would you like me to open?"

        # Check our known app map
        exe = None
        for name, command in sorted(
            self.APP_MAP.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if name in app_name:
                exe = command
                break

        if exe:
            try:
                if exe.startswith("ms-"):
                    # Windows URI scheme (ms-settings:, etc.)
                    os.startfile(exe)
                else:
                    subprocess.Popen(
                        exe,
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return f"Opening {app_name.strip().title()}."
            except Exception as e:
                return f"Failed to open {app_name.strip()}: {e}"

        # Fallback: Try opening directly via shell
        try:
            subprocess.Popen(
                app_name.strip(),
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Trying to open {app_name.strip().title()}."
        except Exception as e:
            return f"I couldn't find or open '{app_name.strip()}'. ({e})"

    def _request_confirmation(self, action: str) -> str:
        """Create a short-lived confirmation challenge for risky actions."""
        if self._pending_action and not self._is_pending_expired():
            pending_action = self._pending_action["action"]
            pending_token = self._pending_action["token"]
            return (
                f"I already have a pending {pending_action} request. "
                f"Say 'confirm {pending_action} {pending_token}' or 'cancel action'."
            )

        token = f"{secrets.randbelow(9000) + 1000}"
        self._pending_action = {
            "action": action,
            "token": token,
            "expires_at": time.time() + self.CONFIRM_TIMEOUT_SECONDS,
        }
        return (
            f"Safety check: to proceed, say 'confirm {action} {token}' "
            f"within {self.CONFIRM_TIMEOUT_SECONDS} seconds, or say 'cancel action'."
        )

    def _handle_confirmation(self, text_lower: str) -> str | None:
        """Execute pending risky action only on exact confirmation phrase."""
        if "confirm" not in text_lower:
            return None

        if not self._pending_action:
            return "There is no pending risky action to confirm."

        if self._is_pending_expired():
            action = self._pending_action["action"]
            self._pending_action = None
            return f"The pending {action} request expired. Please ask again."

        action = self._pending_action["action"]
        token = self._pending_action["token"]
        expected_phrase = f"confirm {action} {token}"
        if expected_phrase not in text_lower:
            return f"Confirmation mismatch. Say exactly: '{expected_phrase}'."

        self._pending_action = None
        return self._execute_confirmed_action(action)

    def _cancel_pending_action(self) -> str:
        if not self._pending_action:
            return "There is no pending risky action to cancel."
        action = self._pending_action["action"]
        self._pending_action = None
        return f"Cancelled pending {action} action."

    def _is_pending_expired(self) -> bool:
        if not self._pending_action:
            return True
        return time.time() > float(self._pending_action["expires_at"])

    def _execute_confirmed_action(self, action: str) -> str:
        if action == "shutdown":
            return self._shutdown_computer()
        if action == "restart":
            return self._restart_computer()
        if action == "sleep":
            return self._sleep_computer()
        return f"Unknown guarded action: {action}"

    def _run_command(self, command: list[str]) -> str | None:
        """Run OS command without shell and return an error string if it fails."""
        try:
            subprocess.Popen(
                command,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return None
        except Exception as e:
            return str(e)

    def _shutdown_computer(self) -> str:
        system = platform.system()
        if system == "Windows":
            err = self._run_command(["shutdown", "/s", "/t", "30"])
            if err:
                return f"Failed to schedule shutdown: {err}"
            return "Shutdown scheduled in 30 seconds. Run 'shutdown /a' to cancel."
        if system == "Linux":
            err = self._run_command(["shutdown", "-h", "+1"])
            if err:
                return f"Failed to schedule shutdown: {err}"
            return "Shutdown scheduled in 1 minute."
        if system == "Darwin":
            err = self._run_command(["shutdown", "-h", "+1"])
            if err:
                return f"Failed to schedule shutdown: {err}"
            return "Shutdown scheduled in 1 minute."
        return f"Shutdown is not supported on {system}."

    def _restart_computer(self) -> str:
        system = platform.system()
        if system == "Windows":
            err = self._run_command(["shutdown", "/r", "/t", "30"])
            if err:
                return f"Failed to schedule restart: {err}"
            return "Restart scheduled in 30 seconds. Run 'shutdown /a' to cancel."
        if system == "Linux":
            err = self._run_command(["shutdown", "-r", "+1"])
            if err:
                return f"Failed to schedule restart: {err}"
            return "Restart scheduled in 1 minute."
        if system == "Darwin":
            err = self._run_command(["shutdown", "-r", "+1"])
            if err:
                return f"Failed to schedule restart: {err}"
            return "Restart scheduled in 1 minute."
        return f"Restart is not supported on {system}."

    def _lock_computer(self) -> str:
        system = platform.system()
        try:
            if system == "Windows":
                ctypes.windll.user32.LockWorkStation()
            elif system == "Darwin":  # macOS
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
                # Keep behavior identical; guarded by confirmation now.
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            elif system == "Darwin":
                os.system("pmset sleepnow")
            elif system == "Linux":
                os.system("systemctl suspend")
            return "Going to sleep. Goodnight!"
        except Exception as e:
            return f"Failed to sleep: {e}"

    def _toggle_mute(self) -> str:
        system = platform.system()
        if system == "Windows":
            try:
                ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)  # Key up
                return "Toggled mute."
            except Exception as e:
                return f"Failed to toggle mute using ctypes: {e}"
        return "I can only toggle mute on Windows currently."
