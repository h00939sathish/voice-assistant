import ctypes
from typing import Any

from skills.base_skill import BaseSkill, skill

# Constants for Windows API
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
WM_CLOSE = 0x0010


@skill(
    name="window_manager",
    keywords=[
        "minimize window",
        "maximize window",
        "restore window",
        "close window",
        "switch to",
        "focus on",
        "activate window",
        "hide all windows",
        "show desktop",
    ],
    description="Manage application windows: minimize, maximize, switch focus",
)
class WindowManagerSkill(BaseSkill):
    def __init__(self):
        super().__init__()
        self.user32 = ctypes.windll.user32

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        text_lower = text.lower()

        if "minimize" in text_lower:
            if "all" in text_lower:
                return self._minimize_all()
            return self._minimize_current()

        if "maximize" in text_lower:
            return self._maximize_current()

        if "restore" in text_lower:
            return self._restore_current()

        if "close" in text_lower and ("current" in text_lower or "this" in text_lower):
            # Dangerous
            return "To close the active window, please confirm by saying 'Force close active window'."

        if "force close" in text_lower:
            return self._close_current()

        if "switch to" in text_lower or "focus on" in text_lower:
            target = text_lower.split("to")[-1].split("on")[-1].strip()
            return self._switch_to(target)

        return "I can help minimize, maximize, or switch windows. What would you like?"

    def _minimize_current(self) -> str:
        hwnd = self.user32.GetForegroundWindow()
        if hwnd:
            self.user32.ShowWindow(hwnd, SW_MINIMIZE)
            return "Minimized."
        return "No active window found."

    def _minimize_all(self) -> str:
        # Win+M or Win+D logic is complex via API directly
        # Easiest: multiple minimizations? No.
        # Use keybd_event to send Win+D (Toggle Desktop)
        # VK_LWIN = 0x5B, 'D' = 0x44
        self.user32.keybd_event(0x5B, 0, 0, 0)  # Win Down
        self.user32.keybd_event(0x44, 0, 0, 0)  # D Down
        self.user32.keybd_event(0x44, 0, 2, 0)  # D Up
        self.user32.keybd_event(0x5B, 0, 2, 0)  # Win Up
        return "Showing desktop."

    def _maximize_current(self) -> str:
        hwnd = self.user32.GetForegroundWindow()
        if hwnd:
            self.user32.ShowWindow(hwnd, SW_MAXIMIZE)
            return "Maximized."
        return "No active window found."

    def _restore_current(self) -> str:
        hwnd = self.user32.GetForegroundWindow()
        if hwnd:
            self.user32.ShowWindow(hwnd, SW_RESTORE)
            return "Restored."
        return "No active window found."

    def _close_current(self) -> str:
        hwnd = self.user32.GetForegroundWindow()
        if hwnd:
            # Send WM_CLOSE message
            self.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return "Closed active window."
        return "No active window found."

    def _switch_to(self, target_name: str) -> str:
        # Enumerate windows and find match
        target_name = target_name.lower()
        found_hwnds = []

        def enum_handler(hwnd, ctx):
            if self.user32.IsWindowVisible(hwnd):
                length = self.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    self.user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    if target_name in title.lower():
                        found_hwnds.append((hwnd, title))
            return True

        wndenumproc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        self.user32.EnumWindows(wndenumproc(enum_handler), 0)

        if found_hwnds:
            # Pick first match (or most relevant)
            hwnd, title = found_hwnds[0]

            # Switch logic (complex in modern Windows due to foreground lock)
            # Try efficient method:
            # 1. AttachThreadInput
            # 2. SetForegroundWindow
            # For now, just try straightforward SetForegroundWindow
            # Often fails if not from a UI thread, but we'll try.
            # Use 'Alt' press trick to bypass restriction
            self.user32.keybd_event(0x12, 0, 0, 0)  # Alt Down
            self.user32.keybd_event(0x12, 0, 2, 0)  # Alt Up

            self.user32.SetForegroundWindow(hwnd)
            if self.user32.IsIconic(hwnd):  # If minimized
                self.user32.ShowWindow(hwnd, SW_RESTORE)

            return f"Switched to {title}."

        return f"I couldn't find a window matching '{target_name}'."
