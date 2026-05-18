import json
import logging
import os
import subprocess
import winreg
from datetime import datetime, timedelta
from pathlib import Path

from rapidfuzz import fuzz, process

from assistant.config_manager import Config

logger = logging.getLogger("AI_Assistant.AppScanner")


class AppManager:
    """Scans for and manages all detectable applications on the system."""

    def __init__(self):
        self.cache_file = Path(Config.CACHE_DIR) / "apps_cache.json"
        self.cache_duration = timedelta(hours=24)
        self.apps = self._load_apps_with_cache()
        logger.info(f"Initialized with {len(self.apps)} applications found.")

    def rescan_apps(self) -> str:
        """Deletes the cache and rescans for all applications."""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
                logger.info("Application cache deleted.")
            self.apps = self._load_apps_with_cache()
            return f"Successfully rescanned. I found {len(self.apps)} applications."
        except OSError as e:
            logger.error(f"Error deleting cache file: {e}")
            return "There was an error while trying to rescan applications."

    def _load_custom_apps(self) -> dict[str, str]:
        """Loads app paths from a custom JSON file and adds them to memory."""
        custom_apps_path = Path(__file__).with_name("custom_apps.json")
        if custom_apps_path.exists():
            try:
                with custom_apps_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error reading {custom_apps_path}: {e}")
        return {}

    def _load_apps_with_cache(self) -> dict[str, str]:
        """Loads apps from cache or rescans, with robust error handling."""
        if self.cache_file.exists():
            if (
                datetime.now() - datetime.fromtimestamp(self.cache_file.stat().st_mtime)
                < self.cache_duration
            ):
                try:
                    with self.cache_file.open("r", encoding="utf-8") as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    logger.warning("Cache file is corrupted, rebuilding...")
                    self.cache_file.unlink(missing_ok=True)

        apps = {}
        apps.update(self._scan_registry_apps())
        apps.update(self._scan_start_menu())
        apps.update(self._scan_store_apps())
        apps.update(self._load_custom_apps())

        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_file.open("w", encoding="utf-8") as f:
                json.dump(apps, f, indent=4)
        except OSError as e:
            logger.error(f"Error writing to cache file: {e}")

        return apps

    def _scan_store_apps(self) -> dict[str, str]:
        """Scans installed Microsoft Store (UWP) apps and normalizes their paths."""
        apps = {}
        command = "Get-StartApps | Select-Object Name, AppId | ConvertTo-Json"
        try:
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )
            if result.stdout:
                data = json.loads(result.stdout)
                if isinstance(data, dict):
                    data = [data]

                for entry in data:
                    name = entry.get("Name", "").lower()
                    app_id = entry.get("AppID", "")
                    if name and app_id:
                        apps[name] = f"shell:appsFolder\\{app_id}"
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            json.JSONDecodeError,
        ) as e:
            logger.error(f"Error scanning Microsoft Store apps: {e}")
        return apps

    def _scan_start_menu(self) -> dict[str, str]:
        """Scans Windows Start Menu, prioritizing .lnk files over .exe files."""
        apps = {}
        start_paths = [
            Path(os.environ["APPDATA"])
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs",
            Path(os.environ["PROGRAMDATA"])
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs",
        ]
        for path in start_paths:
            if not path.exists():
                continue
            for item in path.rglob("*"):
                if item.suffix.lower() == ".lnk":
                    apps[item.stem.lower()] = str(item)
                elif item.suffix.lower() == ".exe" and item.stem.lower() not in apps:
                    apps[item.stem.lower()] = str(item)
        return apps

    def _scan_registry_apps(self) -> dict[str, str]:
        """Scans the registry for app paths and validates their existence."""
        apps = {}
        reg_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ]
        for reg_path in reg_paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                path, _ = winreg.QueryValueEx(subkey, "")
                                if path and Path(path).exists():
                                    apps[Path(subkey_name).stem.lower()] = path
                        except OSError:
                            continue
            except FileNotFoundError:
                continue
        return apps

    def find_best_match(self, query: str) -> str | None:
        """Finds the best application match using improved fuzzy logic."""
        if not self.apps:
            return None
        if query in self.apps:
            return query

        scorer = fuzz.token_set_ratio
        matches = process.extractOne(query, self.apps.keys(), scorer=scorer)

        if matches and (matches[1] > 75 or (len(query) <= 4 and matches[1] > 60)):
            return matches[0]

        return None
