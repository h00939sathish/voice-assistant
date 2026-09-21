from __future__ import annotations

import ctypes
import logging
import os
import platform
import shlex
import subprocess
import time

import pyautogui
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from assistant.app_scanner import AppManager

IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    try:
        import psutil
        import win32con
        import win32gui
        import win32process
    except Exception:
        # fall back gracefully if pywin32 not available
        win32gui = win32con = win32process = None
        import psutil  # psutil usually available or will raise

logger = logging.getLogger("AI_Assistant.AppController")

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.4


class AppController:
    """
    Controls applications after opening them.
    Supports keyboard shortcuts, mouse clicks, and window management.
    """

    APP_MAP = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "firefox": "firefox",
        "edge": "msedge",
        "brave": "brave",
        "opera": "opera",
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

    WINDOW_TITLE_BLACKLIST = [
        "remote desktop",
        "credentials",
        "notification",
        "settings",
        "security",
    ]

    def __init__(self):
        self.system = platform.system()
        self.active_app: str | None = None
        self.active_window_handle: int | None = None
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.volume = interface.QueryInterface(IAudioEndpointVolume)
        except Exception:
            self.volume = None

        # Initialize App Scanner
        self.app_scanner = AppManager()

        self.app_commands = {
            "spotify": {
                "play": self._spotify_play,
                "pause": self._spotify_pause,
                "next": self._spotify_next,
                "previous": self._spotify_previous,
                "search": self._spotify_search,
                "volume_up": self._spotify_volume_up,
                "volume_down": self._spotify_volume_down,
            },
            "chrome": {
                "new_tab": lambda **k: self._browser_action("chrome", "new_tab", **k),
                "close_tab": lambda **k: self._browser_action("chrome", "close_tab", **k),
                "search": lambda **k: self._browser_action("chrome", "search", **k),
                "go_to": lambda **k: self._browser_action("chrome", "go_to", **k),
                "find_on_page": lambda **k: self._browser_action("chrome", "find_on_page", **k),
            },
            "edge": {
                "new_tab": lambda **k: self._browser_action("edge", "new_tab", **k),
                "close_tab": lambda **k: self._browser_action("edge", "close_tab", **k),
                "search": lambda **k: self._browser_action("edge", "search", **k),
                "go_to": lambda **k: self._browser_action("edge", "go_to", **k),
                "find_on_page": lambda **k: self._browser_action("edge", "find_on_page", **k),
            },
            "brave": {
                "new_tab": lambda **k: self._browser_action("brave", "new_tab", **k),
                "close_tab": lambda **k: self._browser_action("brave", "close_tab", **k),
                "search": lambda **k: self._browser_action("brave", "search", **k),
                "go_to": lambda **k: self._browser_action("brave", "go_to", **k),
                "find_on_page": lambda **k: self._browser_action("brave", "find_on_page", **k),
            },
            "opera": {
                "new_tab": lambda **k: self._browser_action("opera", "new_tab", **k),
                "close_tab": lambda **k: self._browser_action("opera", "close_tab", **k),
                "search": lambda **k: self._browser_action("opera", "search", **k),
                "go_to": lambda **k: self._browser_action("opera", "go_to", **k),
                "find_on_page": lambda **k: self._browser_action("opera", "find_on_page", **k),
            },
            "notepad": {
                "type": self._notepad_type,
                "save": self._notepad_save,
            },
            "vscode": {
                "new_file": self._vscode_new_file,
                "save": self._vscode_save,
                "run": self._vscode_run,
            },
            "discord": {
                "send_message": self._discord_send_message,
                "mute": self._discord_mute,
            },
            "whatsapp": {
                "send_message": self._whatsapp_send_message,
                "search_contact": self._whatsapp_search_contact,
            },
        }

    def _ensure_app_window(self, app_name: str, window_title: str | None = None) -> int | None:
        """Find window, auto-launching app if not found."""
        title = window_title or app_name
        handle = self.find_window_by_title(title)
        if not handle:
            self.launch_by_name(app_name)
            time.sleep(2.0)
            handle = self.find_window_by_title(title)
        return handle

    def set_volume(self, lvl: int) -> str:
        if self.volume:
            self.volume.SetMasterVolumeLevelScalar(
                max(0.0, min(1.0, lvl / 100.0)), None
            )
            return f"Volume set to {lvl}%"
        return "Volume control unavailable"

    def change_volume(self, delta: int) -> str:
        if not self.volume:
            return "Volume control unavailable"
        current = int(self.volume.GetMasterVolumeLevelScalar() * 100)
        new = max(0, min(100, current + delta))
        self.set_volume(new)
        return f"Volume {new}%"

    def _ensure_windows(self) -> bool:
        if not IS_WINDOWS:
            logger.warning("AppController feature is Windows-only on this build.")
            return False
        if win32gui is None:
            logger.warning("pywin32 not available; limited window operations.")
            return False
        return True

    @staticmethod
    def windows_only(method):
        """Decorator: wrap a method so it returns an error string on non-Windows."""
        def wrapper(self, *args, **kwargs):
            if not self._ensure_windows():
                return f"{method.__name__} is Windows-only"
            return method(self, *args, **kwargs)
        return wrapper

    def find_window_by_title(
        self, title_contains: str, retries: int = 3, delay: float = 0.6
    ) -> int | None:
        """Find window handle by partial title match (Windows). Retries once to allow apps to start."""
        if not self._ensure_windows():
            return None

        target = title_contains.lower()
        blacklist = tuple(b.lower() for b in self.WINDOW_TITLE_BLACKLIST)
        for _attempt in range(retries):
            found_handle = None

            def callback(hwnd, _):
                nonlocal found_handle
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        window_title = win32gui.GetWindowText(hwnd) or ""
                        title_lower = window_title.lower()
                        if target in title_lower and not any(b in title_lower for b in blacklist):
                            found_handle = hwnd
                            return False
                except Exception:
                    pass
                return True

            try:
                win32gui.EnumWindows(callback, None)
                if found_handle:
                    return found_handle
            except Exception:
                logger.exception("Window enumeration failed", exc_info=True)
            time.sleep(delay)
        return None

    def focus_window(self, handle: int, fallback_click: bool = False) -> bool:
        """Bring window to foreground using multiple aggressive techniques."""
        if not self._ensure_windows() or not handle:
            return False
        try:
            # 1. Force restore if minimized
            if win32gui.IsIconic(handle):
                win32gui.ShowWindow(handle, win32con.SW_RESTORE)

            # 2. Key-press trick to allow background focus stealing
            # Windows blocks SetForegroundWindow unless the calling process has input focus
            # Pro-tip: Pressing 'Alt' sometimes bypasses this restriction
            pyautogui.press("alt", interval=0.01)

            # 3. Try standard SetForegroundWindow
            try:
                win32gui.SetForegroundWindow(handle)
            except Exception:
                # If that fails, try ShowWindow
                win32gui.ShowWindow(handle, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(handle)

            time.sleep(0.25)

            # 4. Verify it worked
            active_window = win32gui.GetForegroundWindow()
            if active_window == handle:
                return True

            # 5. Retry loop
            for _ in range(3):
                win32gui.ShowWindow(handle, win32con.SW_SHOWMAXIMIZED)
                win32gui.SetForegroundWindow(handle)
                time.sleep(0.2)
                if win32gui.GetForegroundWindow() == handle:
                    return True

            return False

        except Exception:
            logger.exception("Failed to focus window")
            return False

    def is_app_running(self, app_name: str) -> bool:
        """Check if application is currently running."""
        try:
            app_name_lower = app_name.lower()
            for proc in psutil.process_iter(["name"]):
                try:
                    pname = (proc.info.get("name") or "").lower()
                    if app_name_lower in pname:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            logger.exception("is_app_running failed")
        return False

    def wait_for_app_start(self, app_name: str, timeout: int = 10) -> bool:
        """Wait for application start; returns True if detected."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_app_running(app_name):
                time.sleep(1.0)
                return True
            time.sleep(0.5)
        return False

    def kill_process(self, app_name: str) -> str:
        """Kill an application by name."""
        try:
            app_lower = app_name.lower()
            killed = []
            for proc in psutil.process_iter(["name"]):
                try:
                    pname = (proc.info.get("name") or "").lower()
                    if app_lower in pname:
                        proc.kill()
                        killed.append(pname)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if killed:
                return f"Killed {len(killed)} process(es) matching '{app_name}'."
            return f"No running process found for '{app_name}'."
        except Exception as e:
            logger.exception(f"kill_process failed for {app_name}")
            return f"Failed to kill {app_name}: {e}"

    def launch_app(self, app_name: str) -> str:
        """Launch an application using App Scanner."""
        logger.info(f"Attempting to launch: {app_name}")

        # 1. Check App Scanner
        match = self.app_scanner.find_best_match(app_name)
        if match:
            path = self.app_scanner.apps[match]
            logger.info(f"Found match: {match} -> {path}")
            try:
                if path.startswith("shell:"):
                    # UWP apps - use explorer.exe to launch safely
                    # "explorer.exe" is a standard Windows executable, so full path isn't strictly needed if in PATH,
                    # but using the command directly avoids shell=True.
                    subprocess.run(["explorer.exe", path], check=True, shell=False)
                else:
                    # Normal apps
                    os.startfile(path)
                return f"Launching {match}..."
            except Exception as e:
                logger.error(f"Failed to launch {match}: {e}")
                return f"Failed to launch {match}"

        return f"I couldn't find an app named '{app_name}'"

    def launch_by_name(self, app_name: str) -> str:
        """Launch an app: try AppScanner first, then the curated APP_MAP allowlist.

        The APP_MAP branch tokenizes the (constant) command into an argv list and
        launches with ``shell=False``. Names that are not resolved by AppScanner
        or APP_MAP are reported as not found — the raw user/LLM-supplied string is
        never handed to a shell, which previously allowed arbitrary command
        execution via the free-text ``Popen(app_name, shell=True)`` fallback.
        """
        app_name_lower = app_name.lower().strip()

        result = self.launch_app(app_name_lower)
        if "couldn't find" not in result.lower():
            return result

        exe = None
        for name, command in sorted(
            self.APP_MAP.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if name in app_name_lower:
                exe = command
                break

        if not exe:
            return f"I couldn't find an app named '{app_name_lower}'"

        try:
            if exe.startswith("ms-"):
                os.startfile(exe)
            else:
                argv = shlex.split(exe)
                if not argv:
                    return f"I couldn't find an app named '{app_name_lower}'"
                subprocess.Popen(
                    argv,
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return f"Opening {app_name_lower.title()}."
        except Exception as e:
            return f"Failed to open {app_name_lower}: {e}"

    def keyboard_mute(self) -> str:
        try:
            if IS_WINDOWS:
                user32 = ctypes.windll.user32
                user32.keybd_event(0xAD, 0, 0, 0)
                user32.keybd_event(0xAD, 0, 2, 0)
                return "Toggled mute."
            return "Mute is only supported on Windows."
        except Exception as e:
            return f"Failed to toggle mute: {e}"

    # ==================== Spotify Controls ====================
    def _spotify_play(self, **kwargs) -> str:
        try:
            pyautogui.press("playpause")
            return "Playing Spotify"
        except Exception:
            logger.exception("Spotify play failed")
            return "Failed to play Spotify"

    def _spotify_pause(self, **kwargs) -> str:
        try:
            pyautogui.press("playpause")
            return "Paused Spotify"
        except Exception:
            logger.exception("Spotify pause failed")
            return "Failed to pause Spotify"

    def _spotify_next(self, **kwargs) -> str:
        try:
            pyautogui.press("nexttrack")
            return "Playing next track"
        except Exception:
            logger.exception("Spotify next failed")
            return "Failed to skip track"

    def _spotify_previous(self, **kwargs) -> str:
        try:
            pyautogui.press("prevtrack")
            return "Playing previous track"
        except Exception:
            logger.exception("Spotify previous failed")
            return "Failed to go to previous track"

    def _spotify_search(self, query: str = "", **kwargs) -> str:
        try:
            if not self._ensure_windows():
                return "Spotify search available on Windows only"

            # Find and focus window
            handle = self.find_window_by_title("spotify")
            if not handle:
                return "Spotify window not found"

            # Bringing window to front - aggressive check
            if not self.focus_window(handle):
                logger.error(
                    "Could not force focus to Spotify. Aborting search to prevent typing in wrong window."
                )
                return "Could not focus Spotify window."

            # Double check we are ACTUALLY in focused window
            if win32gui.GetForegroundWindow() != handle:
                return "Spotify failed to take focus."

            # Open search (Ctrl+L)
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.2)

            # Clear text
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
            pyautogui.press("backspace")

            # Type slowly
            pyautogui.write(query, interval=0.05)
            time.sleep(0.5)
            pyautogui.press("enter")

            # Wait for search results - Spotify can be slow
            time.sleep(2.5)

            # Navigate to "Top Result"
            # Sequence: Tab -> Tab -> Tab -> Enter
            pyautogui.press("tab")
            time.sleep(0.1)
            pyautogui.press("tab")  # to All
            time.sleep(0.1)
            pyautogui.press("tab")  # to Top Result
            time.sleep(0.1)
            pyautogui.press("enter")  # Play

            return f"Playing '{query}' on Spotify"
        except Exception:
            logger.exception("Spotify search failed")
            return "Spotify search failed"

    def _spotify_volume_up(self, **kwargs) -> str:
        try:
            pyautogui.press("volumeup")
            return "Volume increased"
        except Exception:
            logger.exception("Volume up failed")
            return "Failed to change volume"

    def _spotify_volume_down(self, **kwargs) -> str:
        try:
            pyautogui.press("volumedown")
            return "Volume decreased"
        except Exception:
            logger.exception("Volume down failed")
            return "Failed to change volume"

    # ==================== Consolidated Browser Controls ====================
    _BROWSER_WINDOW_TITLES = {
        "chrome": "chrome",
        "edge": "edge",
        "brave": "brave",
        "opera": "opera",
    }

    def _browser_action(self, browser: str, action: str, query: str = "", url: str = "", **kwargs) -> str:
        try:
            if not self._ensure_windows():
                return f"{browser} operations are Windows-only"

            title = self._BROWSER_WINDOW_TITLES.get(browser, browser)
            handle = self._ensure_app_window(browser, window_title=title)
            if not handle:
                return f"{browser} window not found"

            self.focus_window(handle)

            if action == "new_tab":
                pyautogui.hotkey("ctrl", "t")
                return f"Opened new tab in {browser}"
            if action == "close_tab":
                pyautogui.hotkey("ctrl", "w")
                return f"Closed tab in {browser}"
            if action in ("search", "go_to"):
                target = query or url or ""
                pyautogui.hotkey("ctrl", "l")
                if target:
                    pyautogui.write(target, interval=0.03)
                    pyautogui.press("enter")
                    return f"Navigating to '{target}' in {browser}"
                return f"Opened address bar in {browser}"
            if action == "find_on_page":
                pyautogui.hotkey("ctrl", "f")
                time.sleep(0.3)
                if query:
                    pyautogui.write(query, interval=0.03)
                    pyautogui.press("enter")
                    return f"Finding '{query}' in {browser}"
                return f"Opened find bar in {browser}"

            return f"Unknown browser action: {action}"
        except Exception:
            logger.exception(f"{browser} {action} failed")
            return f"Failed to {action} in {browser}"

    # ==================== Notepad Controls ====================
    def _notepad_type(self, text: str = "", **kwargs) -> str:
        try:
            if not self._ensure_windows():
                return "Notepad is Windows-only"
            handle = self.find_window_by_title("notepad")
            if not handle:
                return "Notepad window not found"
            self.focus_window(handle)
            pyautogui.write(text, interval=0.02)
            return "Typed text"
        except Exception:
            logger.exception("Notepad type failed")
            return "Failed to type in Notepad"

    def _notepad_save(self, filename: str = "document.txt", **kwargs) -> str:
        try:
            if not self._ensure_windows():
                return "Notepad save is Windows-only"
            handle = self.find_window_by_title("notepad")
            if not handle:
                return "Notepad window not found"
            self.focus_window(handle)
            pyautogui.hotkey("ctrl", "s")
            time.sleep(0.5)
            pyautogui.write(filename, interval=0.04)
            pyautogui.press("enter")
            return f"Saved as {filename}"
        except Exception:
            logger.exception("Notepad save failed")
            return "Failed to save Notepad file"

    # ==================== VS Code ====================
    def _vscode_new_file(self, **kwargs) -> str:
        try:
            handle = self.find_window_by_title("visual studio code")
            if handle:
                self.focus_window(handle)
                pyautogui.hotkey("ctrl", "n")
                return "Created new file"
            return "VS Code not found"
        except Exception:
            logger.exception("VS Code new file failed")
            return "Failed to create file"

    def _vscode_save(self, **kwargs) -> str:
        try:
            handle = self.find_window_by_title("visual studio code")
            if handle:
                self.focus_window(handle)
                pyautogui.hotkey("ctrl", "s")
                return "File saved"
            return "VS Code not found"
        except Exception:
            logger.exception("VS Code save failed")
            return "Failed to save file"

    def _vscode_run(self, **kwargs) -> str:
        try:
            handle = self.find_window_by_title("visual studio code")
            if handle:
                self.focus_window(handle)
                pyautogui.press("f5")
                return "Running code"
            return "VS Code not found"
        except Exception:
            logger.exception("VS Code run failed")
            return "Failed to run code"

    # ==================== Discord ====================
    def _discord_send_message(self, message: str = "", **kwargs) -> str:
        try:
            handle = self.find_window_by_title("discord")
            if not handle:
                return "Discord not found"
            self.focus_window(handle)
            time.sleep(0.2)
            pyautogui.write(message, interval=0.02)
            pyautogui.press("enter")
            return "Sent message"
        except Exception:
            logger.exception("Discord send failed")
            return "Failed to send Discord message"

    def _discord_mute(self, **kwargs) -> str:
        try:
            handle = self.find_window_by_title("discord")
            if handle:
                self.focus_window(handle)
                pyautogui.hotkey("ctrl", "shift", "m")
                return "Toggled mute"
            return "Discord not found"
        except Exception:
            logger.exception("Discord mute failed")
            return "Failed to toggle mute"

    # ==================== WhatsApp ====================
    def _whatsapp_send_message(self, message: str = "", **kwargs) -> str:
        try:
            handle = self.find_window_by_title("whatsapp")
            if not handle:
                return "WhatsApp not found"
            self.focus_window(handle)
            time.sleep(0.25)
            pyautogui.write(message, interval=0.02)
            pyautogui.press("enter")
            return "Sent WhatsApp message"
        except Exception:
            logger.exception("WhatsApp send failed")
            return "Failed to send WhatsApp message"

    def _whatsapp_search_contact(self, contact: str = "", **kwargs) -> str:
        try:
            handle = self.find_window_by_title("whatsapp")
            if not handle:
                return "WhatsApp not found"
            self.focus_window(handle)
            pyautogui.hotkey("ctrl", "f")
            time.sleep(0.2)
            pyautogui.write(contact, interval=0.03)
            time.sleep(0.35)
            pyautogui.press("enter")
            return f"Opened chat with {contact}"
        except Exception:
            logger.exception("WhatsApp contact search failed")
            return "Failed to search contact"

    # ==================== PUBLIC API ====================
    def execute_command(self, app_name: str, command: str, **params) -> str:
        app_name = app_name.lower()
        command = command.lower()

        if app_name not in self.app_commands:
            return f"App '{app_name}' not supported yet"

        if command not in self.app_commands[app_name]:
            available = ", ".join(self.app_commands[app_name].keys())
            return f"Command '{command}' not available. Available: {available}"

        try:
            func = self.app_commands[app_name][command]
            return func(**params)
        except Exception as e:
            logger.exception("Command execution failed: %s", e)
            return f"Error executing command: {e}"

    def list_supported_apps(self) -> list[str]:
        return list(self.app_commands.keys())

    def list_app_commands(self, app_name: str) -> list[str]:
        app_name = app_name.lower()
        if app_name in self.app_commands:
            return list(self.app_commands[app_name].keys())
        return []
