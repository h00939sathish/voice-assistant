"""
Add or remove Buddy from Windows Startup
"""

import sys
import winreg
from pathlib import Path


def get_script_path():
    return str(Path(__file__).parent / "main.py")


def add_to_startup():
    """Add Buddy to Windows startup registry"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value_name = "BuddyAssistant"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
        winreg.SetValueEx(
            key,
            value_name,
            0,
            winreg.REG_SZ,
            f'"{sys.executable.replace("python.exe", "pythonw.exe")}" "{get_script_path()}"',
        )
        winreg.CloseKey(key)
        print("✅ Added Buddy to Windows Startup")
        return True
    except Exception as e:
        print(f"❌ Failed to add startup: {e}")
        return False


def remove_from_startup():
    """Remove Buddy from Windows startup registry"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value_name = "BuddyAssistant"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
        try:
            winreg.DeleteValue(key, value_name)
            print("✅ Removed Buddy from Windows Startup")
        except FileNotFoundError:
            print("ℹ️ Buddy was not in startup")
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"❌ Failed to remove startup: {e}")
        return False


def check_startup():
    """Check if Buddy is in startup"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value_name = "BuddyAssistant"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, value_name)
            winreg.CloseKey(key)
            print(f"✅ Buddy is in startup: {value}")
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            print("ℹ️ Buddy is NOT in startup")
            return False
    except Exception as e:
        print(f"❌ Error checking startup: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage Buddy startup")
    parser.add_argument("--add", action="store_true", help="Add to startup")
    parser.add_argument("--remove", action="store_true", help="Remove from startup")
    parser.add_argument("--check", action="store_true", help="Check startup status")

    args = parser.parse_args()

    if args.check:
        check_startup()
    elif args.add:
        add_to_startup()
    elif args.remove:
        remove_from_startup()
    else:
        check_startup()
        print("\nUsage:")
        print("  python start_buddy.py --add     # Add to startup")
        print("  python start_buddy.py --remove   # Remove from startup")
        print("  python start_buddy.py --check   # Check status")
