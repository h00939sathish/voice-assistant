"""
System Tray Icon - Background management
"""

import os
import sys
import winreg
from pathlib import Path

import pystray
from PIL import Image, ImageDraw


def get_script_path():
    return str(Path(__file__).parent.parent / "main.py")


def is_in_startup():
    """Check if Buddy is in startup"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, "BuddyAssistant")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False


def toggle_startup():
    """Toggle startup setting"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value_name = "BuddyAssistant"
    value = f'"{sys.executable}" "{get_script_path()}"'

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
        if is_in_startup():
            try:
                winreg.DeleteValue(key, value_name)
            except Exception:
                pass
        else:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        return not is_in_startup()
    except Exception as e:
        print(f"Startup toggle error: {e}")
        return False


class SystemTrayApp:
    def __init__(self, on_exit=None, on_show=None):
        self.on_exit = on_exit
        self.on_show = on_show
        self.icon = None

    def create_icon(self):
        width = 64
        height = 64
        image = Image.new("RGB", (width, height), (255, 255, 255))
        dc = ImageDraw.Draw(image)
        dc.rectangle((0, 0, width, height), fill=(255, 255, 255))
        dc.ellipse((8, 8, width - 8, height - 8), fill=(0, 120, 255))
        return image

    def _get_startup_text(self, item):
        return "✓ Run on Startup" if is_in_startup() else "○ Run on Startup"

    def setup(self):
        def toggle_startup_action(icon, item):
            toggle_startup()
            self._restart_action(icon, item)

        menu = pystray.Menu(
            pystray.MenuItem("Show Assistant", self._show_action),
            pystray.MenuItem(self._get_startup_text, toggle_startup_action),
            pystray.MenuItem("Restart", self._restart_action),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._exit_action),
        )

        self.icon = pystray.Icon("Buddy", self.create_icon(), "Buddy Assistant", menu)

    def _show_action(self, icon, item):
        if self.on_show:
            self.on_show()

    def _restart_action(self, icon, item):
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def _exit_action(self, icon, item):
        icon.stop()
        if self.on_exit:
            self.on_exit()

    def run(self):
        self.setup()
        self.icon.run()

    def stop(self):
        if self.icon:
            self.icon.stop()
