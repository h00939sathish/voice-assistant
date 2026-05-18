"""
Desktop Agent Core Module

Main DesktopAgent class providing all desktop automation capabilities.
Includes mouse, keyboard, window, file, clipboard, and app management.
"""

import ctypes
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

# Optional imports - will be checked at runtime
logger = logging.getLogger(__name__)

pyautogui = None
pygetwindow = None
psutil = None
pyperclip = None

try:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
except ImportError:
    logger.warning("pyautogui not installed - mouse/keyboard control disabled")

try:
    import pygetwindow as gw
except ImportError:
    logger.warning("pygetwindow not installed - window control limited")

try:
    import psutil
except ImportError:
    logger.warning("psutil not installed - process control limited")

try:
    import pyperclip
except ImportError:
    logger.warning("pyperclip not installed - clipboard limited")

WIN_EXTENSIONS = (".exe", ".lnk", ".bat", ".cmd")
SEARCH_PATHS = [
    os.environ.get("PROGRAMFILES", "C:\\Program Files"),
    os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
    os.environ.get("LOCALAPPDATA", "") + "\\Programs",
    str(Path.home() / "AppData" / "Local" / "Programs"),
]


class DesktopAgent:
    """
    Main desktop automation agent.

    Provides methods for mouse control, keyboard input, window management,
    file operations, clipboard, and application control.
    """

    def __init__(
        self,
        safety_layer: Any | None = None,
        default_timeout: int = 30,
        log_actions: bool = True,
    ):
        """
        Initialize DesktopAgent.

        Args:
            safety_layer: Optional SafetyLayer instance for logging/timeouts
            default_timeout: Default timeout in seconds for actions
            log_actions: Whether to log actions to file
        """
        self._safety_layer = safety_layer
        self._default_timeout = default_timeout
        self._log_actions = log_actions
        self._screen_size = (1920, 1080)  # Default, will update if pyautogui available

        # Get actual screen size if pyautogui available
        if pyautogui:
            try:
                self._screen_size = pyautogui.size()
            except Exception:
                pass

        self._user32 = ctypes.windll.user32
        self._shell32 = ctypes.windll.shell32

        logger.info(f"DesktopAgent initialized. Screen: {self._screen_size}")

    @property
    def screen_size(self) -> tuple[int, int]:
        return self._screen_size

    def _log(self, action: str, params: dict, result: Any, success: bool):
        """Log action to safety layer or logger."""
        if self._safety_layer:
            self._safety_layer.log_action(action, params, result, success)
        elif self._log_actions:
            logger.info(f"Action: {action} | Params: {params} | Success: {success}")

    def _check_timeout(self, start_time: float) -> bool:
        """Check if action has exceeded timeout."""
        if self._safety_layer:
            return self._safety_layer.check_timeout(start_time)
        return time.time() - start_time > self._default_timeout

    # ==================== MOUSE METHODS ====================

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> bool:
        """
        Move mouse to specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            duration: Movement duration in seconds (0 = instant)

        Returns:
            bool: True if successful
        """
        try:
            time.time()
            pyautogui.moveTo(x, y, duration=duration)
            self._log("move_mouse", {"x": x, "y": y, "duration": duration}, True, True)
            return True
        except Exception as e:
            logger.error(f"move_mouse failed: {e}")
            self._log("move_mouse", {"x": x, "y": y}, str(e), False)
            return False

    def click(
        self,
        x: int | None = None,
        y: int | None = None,
        button: str = "left",
        clicks: int = 1,
    ) -> bool:
        """
        Click at specified coordinates (or current position if None).

        Args:
            x: X coordinate (None = current position)
            y: Y coordinate (None = current position)
            button: "left", "right", or "middle"
            clicks: Number of clicks

        Returns:
            bool: True if successful
        """
        try:
            if x is not None and y is not None:
                pyautogui.click(x, y, clicks=clicks, button=button)
            else:
                pyautogui.click(clicks=clicks, button=button)
            self._log(
                "click",
                {"x": x, "y": y, "button": button, "clicks": clicks},
                True,
                True,
            )
            return True
        except Exception as e:
            logger.error(f"click failed: {e}")
            self._log("click", {"x": x, "y": y, "button": button}, str(e), False)
            return False

    def double_click(
        self,
        x: int | None = None,
        y: int | None = None,
    ) -> bool:
        """
        Double click at specified coordinates.

        Args:
            x: X coordinate (None = current position)
            y: Y coordinate (None = current position)

        Returns:
            bool: True if successful
        """
        return self.click(x, y, button="left", clicks=2)

    def right_click(
        self,
        x: int | None = None,
        y: int | None = None,
    ) -> bool:
        """
        Right click at specified coordinates.

        Args:
            x: X coordinate (None = current position)
            y: Y coordinate (None = current position)

        Returns:
            bool: True if successful
        """
        return self.click(x, y, button="right", clicks=1)

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.5,
    ) -> bool:
        """
        Drag from (x1, y1) to (x2, y2).

        Args:
            x1: Start X
            y1: Start Y
            x2: End X
            y2: End Y
            duration: Drag duration in seconds

        Returns:
            bool: True if successful
        """
        try:
            pyautogui.moveTo(x1, y1)
            pyautogui.mouseDown()
            pyautogui.moveTo(x2, y2, duration=duration)
            pyautogui.mouseUp()
            self._log(
                "drag",
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration": duration},
                True,
                True,
            )
            return True
        except Exception as e:
            logger.error(f"drag failed: {e}")
            self._log("drag", {"x1": x1, "y1": y1, "x2": x2, "y2": y2}, str(e), False)
            return False

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> bool:
        """
        Scroll the mouse wheel.

        Args:
            clicks: Number of scroll clicks (positive = up, negative = down)
            x: X coordinate (None = current)
            y: Y coordinate (None = current)

        Returns:
            bool: True if successful
        """
        try:
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)
            pyautogui.scroll(clicks)
            self._log("scroll", {"clicks": clicks, "x": x, "y": y}, True, True)
            return True
        except Exception as e:
            logger.error(f"scroll failed: {e}")
            return False

    # ==================== KEYBOARD METHODS ====================

    def type_text(self, text: str, interval: float = 0.0) -> bool:
        """
        Type text using keyboard.

        Args:
            text: Text to type
            interval: Interval between keystrokes in seconds

        Returns:
            bool: True if successful
        """
        try:
            pyautogui.write(text, interval=interval)
            self._log(
                "type_text", {"text": text[:50], "interval": interval}, True, True
            )
            return True
        except Exception as e:
            logger.error(f"type_text failed: {e}")
            self._log("type_text", {"text": text[:50]}, str(e), False)
            return False

    def press(self, key: str) -> bool:
        """
        Press a single key.

        Args:
            key: Key name (e.g., "enter", "esc", "space", "tab")

        Returns:
            bool: True if successful
        """
        try:
            pyautogui.press(key)
            self._log("press", {"key": key}, True, True)
            return True
        except Exception as e:
            logger.error(f"press failed: {e}")
            return False

    def hotkey(self, *keys: str) -> bool:
        """
        Press a combination of keys (e.g., Ctrl+C).

        Args:
            *keys: Keys to press simultaneously (e.g., "ctrl", "c", "shift", "a")

        Returns:
            bool: True if successful
        """
        try:
            pyautogui.hotkey(*keys)
            self._log("hotkey", {"keys": list(keys)}, True, True)
            return True
        except Exception as e:
            logger.error(f"hotkey failed: {e}")
            self._log("hotkey", {"keys": list(keys)}, str(e), False)
            return False

    # ==================== APP / WINDOW METHODS ====================

    def open_app(self, path_or_name: str, wait: bool = True, timeout: int = 10) -> bool:
        """
        Open an application by path or name.

        Args:
            path_or_name: Full path to executable or app name
            wait: Whether to wait for app to start
            timeout: Timeout in seconds

        Returns:
            bool: True if successful
        """
        try:
            # Check if it's a full path
            if os.path.exists(path_or_name):
                subprocess.Popen(path_or_name)
                self._log("open_app", {"path": path_or_name}, True, True)
                return True

            # Try to find by name
            app_path = self._find_app_by_name(path_or_name)
            if app_path:
                subprocess.Popen(app_path)
                self._log(
                    "open_app", {"name": path_or_name, "path": app_path}, True, True
                )
                return True

            # Try as command
            subprocess.Popen(path_or_name)
            self._log("open_app", {"command": path_or_name}, True, True)
            return True

        except Exception as e:
            logger.error(f"open_app failed: {e}")
            self._log("open_app", {"path_or_name": path_or_name}, str(e), False)
            return False

    def _find_app_by_name(self, name: str) -> str | None:
        """Find application path by name."""
        name_clean = name.lower().replace(" ", "")

        # Special cases for common apps
        special_apps = {
            "chrome": "Google\\Chrome\\Application\\chrome.exe",
            "firefox": "Mozilla Firefox\\firefox.exe",
            "spotify": "Spotify\\Spotify.exe",
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "explorer": "explorer.exe",
            "vscode": "Microsoft VS Code\\Code.exe",
        }

        if name_clean in special_apps:
            search_path = os.path.join(
                os.environ.get("LOCALAPPDATA", ""), "Programs", special_apps[name_clean]
            )
            if os.path.exists(search_path):
                return search_path

            # Try Program Files
            pf = os.environ.get("PROGRAMFILES", "C:\\Program Files")
            search_path2 = os.path.join(pf, special_apps[name_clean])
            if os.path.exists(search_path2):
                return search_path2

        # Search in PATH and common locations
        for search_dir in SEARCH_PATHS:
            if not search_dir or not os.path.exists(search_dir):
                continue
            try:
                for root, _, files in os.walk(search_dir):
                    for f in files:
                        if name_clean in f.lower().replace(" ", "").replace(".exe", ""):
                            return os.path.join(root, f)
            except (PermissionError, OSError):
                continue

        return None

    def close_app(self, name: str, force: bool = False) -> bool:
        """
        Close an application by name.

        Args:
            name: Application name (window title or process name)
            force: Force close (kill process)

        Returns:
            bool: True if successful
        """
        try:
            # Try window-based close first
            windows = gw.getWindowsWithTitle(name)
            if windows:
                for win in windows:
                    try:
                        win.close()
                        self._log(
                            "close_app", {"name": name, "method": "window"}, True, True
                        )
                        return True
                    except Exception:
                        continue

            # Try process-based close
            if force:
                for proc in psutil.process_iter(["name"]):
                    try:
                        if name.lower() in proc.info["name"].lower():
                            proc.kill()
                            self._log(
                                "close_app",
                                {"name": name, "method": "process"},
                                True,
                                True,
                            )
                            return True
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

            self._log("close_app", {"name": name}, "Not found", False)
            return False

        except Exception as e:
            logger.error(f"close_app failed: {e}")
            return False

    def focus_window(self, title: str, match_exact: bool = False) -> bool:
        """
        Focus a window by title.

        Args:
            title: Window title (partial match unless match_exact=True)
            match_exact: Require exact title match

        Returns:
            bool: True if successful
        """
        try:
            windows = gw.getWindowsWithTitle(title)

            if not windows:
                if not match_exact:
                    # Try case-insensitive search
                    for win in gw.listWindows():
                        if title.lower() in win.title.lower():
                            windows.append(win)
                if not windows:
                    self._log("focus_window", {"title": title}, "Not found", False)
                    return False

            win = windows[0]

            # Restore if minimized
            if win.isMinimized:
                win.restore()

            # Activate
            win.activate()

            self._log("focus_window", {"title": title, "window": win.title}, True, True)
            return True

        except Exception as e:
            logger.error(f"focus_window failed: {e}")
            return False

    def list_windows(self) -> list[dict[str, Any]]:
        """
        List all visible windows.

        Returns:
            List of window info dicts: {"title": str, "hwnd": int, "process": str}
        """
        try:
            windows = []
            for win in gw.listWindows():
                if win.title and win.isVisible:
                    try:
                        proc_name = ""
                        if win.processID:
                            try:
                                proc = psutil.Process(win.processID)
                                proc_name = proc.name()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass

                        windows.append(
                            {
                                "title": win.title,
                                "hwnd": win._hWnd,
                                "process": proc_name,
                                "is_minimized": win.isMinimized,
                            }
                        )
                    except Exception:
                        continue

            return windows

        except Exception as e:
            logger.error(f"list_windows failed: {e}")
            return []

    def move_window(
        self,
        title: str,
        x: int,
        y: int,
        w: int | None = None,
        h: int | None = None,
    ) -> bool:
        """
        Move and optionally resize a window.

        Args:
            title: Window title to match
            x: New X position
            y: New Y position
            w: New width (None = keep current)
            h: New height (None = keep current)

        Returns:
            bool: True if successful
        """
        try:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return False

            win = windows[0]
            win.moveTo(x, y)

            if w is not None and h is not None:
                win.resizeTo(w, h)

            self._log(
                "move_window",
                {"title": title, "x": x, "y": y, "w": w, "h": h},
                True,
                True,
            )
            return True

        except Exception as e:
            logger.error(f"move_window failed: {e}")
            return False

    def get_active_window(self) -> dict[str, Any] | None:
        """Get currently active window info."""
        try:
            win = gw.getActiveWindow()
            if win:
                return {
                    "title": win.title,
                    "hwnd": win._hWnd,
                    "is_minimized": win.isMinimized,
                    "is_maximized": win.isMaximized,
                }
        except Exception as e:
            logger.error(f"get_active_window failed: {e}")
        return None

    # ==================== FILE METHODS ====================

    def open_file(self, path: str) -> bool:
        """
        Open a file with default application.

        Args:
            path: Full path to file

        Returns:
            bool: True if successful
        """
        try:
            path_abs = os.path.abspath(path)
            if not os.path.exists(path_abs):
                self._log("open_file", {"path": path}, "File not found", False)
                return False

            os.startfile(path_abs)
            self._log("open_file", {"path": path}, True, True)
            return True

        except Exception as e:
            logger.error(f"open_file failed: {e}")
            return False

    def search_files(
        self,
        query: str,
        root: str | None = None,
        max_results: int = 20,
    ) -> list[str]:
        """
        Search for files by name.

        Args:
            query: Search query
            root: Root directory to search (default: user folders)
            max_results: Maximum number of results

        Returns:
            List of file paths
        """
        try:
            if root is None:
                roots = [
                    Path.home() / "Documents",
                    Path.home() / "Desktop",
                    Path.home() / "Downloads",
                ]
            else:
                roots = [Path(root)]

            results = []
            query_lower = query.lower()

            for root_path in roots:
                if not root_path.exists():
                    continue

                try:
                    for path in root_path.rglob(f"*{query}*"):
                        if len(results) >= max_results:
                            break
                        if path.is_file() and query_lower in path.name.lower():
                            results.append(str(path))
                except (PermissionError, OSError):
                    continue

                if len(results) >= max_results:
                    break

            self._log(
                "search_files",
                {"query": query, "root": root, "count": len(results)},
                results,
                True,
            )
            return results

        except Exception as e:
            logger.error(f"search_files failed: {e}")
            return []

    def list_folder(self, path: str = ".") -> list[dict[str, Any]]:
        """
        List contents of a folder.

        Args:
            path: Folder path (default: current directory)

        Returns:
            List of file/folder info dicts
        """
        try:
            folder_path = Path(path).resolve()
            if not folder_path.exists():
                return []

            items = []
            for item in folder_path.iterdir():
                try:
                    items.append(
                        {
                            "name": item.name,
                            "path": str(item),
                            "is_file": item.is_file(),
                            "is_dir": item.is_dir(),
                            "size": item.stat().st_size if item.is_file() else 0,
                        }
                    )
                except (PermissionError, OSError):
                    continue

            return items

        except Exception as e:
            logger.error(f"list_folder failed: {e}")
            return []

    # ==================== CLIPBOARD METHODS ====================

    def copy_text(self, text: str) -> bool:
        """
        Copy text to clipboard.

        Args:
            text: Text to copy

        Returns:
            bool: True if successful
        """
        try:
            import pyperclip

            pyperclip.copy(text)
            self._log("copy_text", {"text": text[:50]}, True, True)
            return True
        except ImportError:
            # Fallback to Windows API
            try:
                self._user32.GlobalAlloc(0x0042, len(text) + 1)
                # Try tkinter as fallback
                import tkinter as tk

                root = tk.Tk()
                root.withdraw()
                root.clipboard_clear()
                root.clipboard_append(text)
                root.update()
                root.destroy()
                return True
            except Exception as e:
                logger.error(f"copy_text failed: {e}")
                return False
        except Exception as e:
            logger.error(f"copy_text failed: {e}")
            return False

    def paste(self) -> bool:
        """
        Paste clipboard content at current position.

        Returns:
            bool: True if successful
        """
        try:
            import pyperclip

            text = pyperclip.paste()
            if text:
                pyautogui.write(text)
                self._log("paste", {"length": len(text)}, True, True)
                return True
            return False
        except ImportError:
            # Fallback: Ctrl+V
            pyautogui.hotkey("ctrl", "v")
            return True
        except Exception as e:
            logger.error(f"paste failed: {e}")
            return False

    def get_clipboard_text(self) -> str | None:
        """
        Get current clipboard text.

        Returns:
            Clipboard text or None
        """
        try:
            import pyperclip

            return pyperclip.paste()
        except ImportError:
            try:
                import tkinter as tk

                root = tk.Tk()
                root.withdraw()
                text = root.clipboard_get()
                root.update()
                root.destroy()
                return text
            except Exception:
                return None
        except Exception as e:
            logger.error(f"get_clipboard_text failed: {e}")
            return None

    # ==================== UTILITY METHODS ====================

    def wait(self, seconds: float) -> bool:
        """
        Wait for specified seconds.

        Args:
            seconds: Number of seconds to wait

        Returns:
            bool: True (always succeeds)
        """
        time.sleep(seconds)
        return True

    def get_screen_size(self) -> tuple[int, int]:
        """Get screen dimensions."""
        return self._screen_size

    def get_cursor_position(self) -> tuple[int, int]:
        """Get current cursor position."""
        return pyautogui.position()
