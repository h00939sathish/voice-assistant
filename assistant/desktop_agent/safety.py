"""
Safety Layer Module

Provides safety features including:
- Emergency stop (global hotkey)
- Action logging
- Timeout protection
- Allowlist mode
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Try to import pynput for global hotkeys
keyboard = None
PYNPUT_AVAILABLE = False

try:
    from pynput import keyboard

    PYNPUT_AVAILABLE = True
except ImportError:
    logger.warning("pynput not available - emergency stop disabled")


class ActionLogger:
    """Logs all desktop agent actions to file."""

    def __init__(self, log_path: str = "logs/desktop_actions.log"):
        self._log_path = log_path
        self._lock = threading.Lock()

        log_dir = Path(log_path).parent
        if not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, action: str, params: dict, result: Any, success: bool):
        try:
            with self._lock:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "action": action,
                    "params": params,
                    "result": str(result)[:500],
                    "success": success,
                }
                with open(self._log_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to log action: {e}")


class SafetyLayer:
    """
    Safety layer for DesktopAgent.

    Features:
    - Action logging
    - Timeout protection
    - Emergency stop
    - Allowlist mode
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        enable_logging: bool = True,
        log_path: str = "logs/desktop_actions.log",
        enable_emergency_stop: bool = True,
        default_timeout: int = 30,
        enable_allowlist: bool = False,
    ):
        """Initialize safety layer."""
        # Avoid re-initialization
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._enable_logging = enable_logging
        self._log_path = log_path
        self._enable_emergency_stop = enable_emergency_stop and PYNPUT_AVAILABLE
        self._default_timeout = default_timeout
        self._enable_allowlist = enable_allowlist

        self._action_start_times: dict[str, float] = {}
        self._allowlist: set[str] = set()
        self._emergency_stop_triggered = False
        self._stop_event = threading.Event()

        # Initialize logger
        self._logger = ActionLogger(log_path) if enable_logging else None

        # Start emergency stop listener
        if self._enable_emergency_stop:
            self._start_emergency_listener()

        self._initialized = True
        logger.info(
            f"SafetyLayer initialized (emergency_stop={self._enable_emergency_stop}, logging={enable_logging})"
        )

    def _start_emergency_listener(self):
        """Start emergency stop global hotkey listener."""
        if not PYNPUT_AVAILABLE or keyboard is None:
            self._enable_emergency_stop = False
            return

        self._emergency_stop_triggered = False

        def on_press(key):
            # Check for Ctrl+Alt+Esc
            try:
                if key == keyboard.Key.esc:
                    # Get pressed modifier keys
                    pressed = set()

                    def on_release(k):
                        pass

                    # Simple check: if ESC is pressed with Ctrl+Alt
                    try:
                        from pynput import keyboard as kbd_module

                        current = kbd_module.GetHeldKey()
                        if current in (kbd_module.Key.ctrl_l, kbd_module.Key.ctrl_r):
                            pressed.add("ctrl")
                        if current in (kbd_module.Key.alt_l, kbd_module.Key.alt_r):
                            pressed.add("alt")
                    except Exception:
                        pass

                    if "ctrl" in pressed and "alt" in pressed:
                        self._trigger_emergency_stop()
            except Exception as e:
                logger.error(f"Emergency stop check error: {e}")

        def on_release(key):
            pass

        try:
            self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._listener.start()
            logger.info("Emergency stop listener started (Ctrl+Alt+Esc)")
        except Exception as e:
            logger.warning(f"Failed to start emergency stop listener: {e}")
            self._enable_emergency_stop = False

    def _trigger_emergency_stop(self):
        """Trigger emergency stop."""
        if not self._emergency_stop_triggered:
            self._emergency_stop_triggered = True
            self._stop_event.set()
            logger.warning("⚠️ EMERGENCY STOP TRIGGERED")

            # Try to log critical alert
            if self._logger:
                try:
                    with open(
                        self._log_path.replace(".log", "_emergency.log"), "a"
                    ) as f:
                        f.write(
                            json.dumps(
                                {
                                    "timestamp": datetime.now().isoformat(),
                                    "type": "EMERGENCY_STOP",
                                }
                            )
                            + "\n"
                        )
                except Exception:
                    pass

    def log_action(
        self,
        action: str,
        params: dict,
        result: Any,
        success: bool,
    ):
        """Log an action."""
        if self._logger:
            self._logger.log(action, params, result, success)

    def check_timeout(self, start_time: float, timeout: int | None = None) -> bool:
        """Check if action has exceeded timeout."""
        if timeout is None:
            timeout = self._default_timeout
        return time.time() - start_time > timeout

    def is_allowed(self, action: str, target: str | None = None) -> bool:
        """
        Check if action is allowed.

        Uses allowlist mode if enabled.
        """
        if not self._enable_allowlist:
            return True

        # Check if action in allowlist
        allowed_actions = {
            "move_mouse",
            "click",
            "double_click",
            "right_click",
            "scroll",
            "type_text",
            "press",
            "hotkey",
            "focus_window",
            "list_windows",
            "move_window",
            "get_clipboard_text",
            "copy_text",
            "paste",
            "take_screenshot",
            "ocr_screen",
            "find_image",
            "search_files",
            "list_folder",
            "wait",
        }

        if action in allowed_actions:
            return True

        # For app operations, check allowlist
        dangerous_actions = {"open_app", "close_app", "open_file", "delete_file"}
        if action in dangerous_actions:
            if target and target in self._allowlist:
                return True
            logger.warning(f"Action {action} on {target} not in allowlist")
            return False

        return True

    def add_to_allowlist(self, item: str):
        """Add item to allowlist."""
        self._allowlist.add(item)
        logger.info(f"Added to allowlist: {item}")

    def remove_from_allowlist(self, item: str):
        """Remove item from allowlist."""
        self._allowlist.discard(item)
        logger.info(f"Removed from allowlist: {item}")

    def get_allowlist(self) -> set[str]:
        """Get current allowlist."""
        return self._allowlist.copy()

    def is_emergency_stopped(self) -> bool:
        """Check if emergency stop was triggered."""
        return self._emergency_stop_triggered

    def reset_emergency_stop(self):
        """Reset emergency stop flag."""
        self._emergency_stop_triggered = False
        self._stop_event.clear()
        logger.info("Emergency stop reset")

    def should_stop(self) -> bool:
        """Check if should stop (emergency or timeout)."""
        return self._emergency_stop_triggered or self._stop_event.is_set()

    @property
    def default_timeout(self) -> int:
        return self._default_timeout

    @default_timeout.setter
    def default_timeout(self, value: int):
        self._default_timeout = value

    def get_log_path(self) -> str:
        return self._log_path

    def get_recent_actions(self, count: int = 10) -> list[dict]:
        """Get recent logged actions."""
        if not self._logger:
            return []

        try:
            actions = []
            if os.path.exists(self._log_path):
                with open(self._log_path) as f:
                    lines = f.readlines()
                    for line in lines[-count:]:
                        try:
                            actions.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            continue
            return actions
        except Exception as e:
            logger.error(f"Failed to get recent actions: {e}")
            return []


class EmergencyStop:
    """
    Simple emergency stop handler.

    Usage:
        stop = EmergencyStop()
        stop.start()

        # In your code, check:
        if stop.triggered:
            break  # or raise exception
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, hotkey: tuple = ("ctrl", "alt", "esc")):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._hotkey = hotkey
        self._triggered = False
        self._stop_event = threading.Event()
        self._listener = None

        # Try to start listener
        if PYNPUT_AVAILABLE:
            try:
                self._listener = keyboard.Listener(
                    on_press=self._on_key_press, on_release=self._on_key_release
                )
                self._listener.start()
            except Exception as e:
                logger.warning(f"Failed to start EmergencyStop listener: {e}")

        self._initialized = True
        logger.info("EmergencyStop initialized")

    def _on_key_press(self, key):
        """Handle key press."""
        try:
            # Check for ESC
            if key == keyboard.Key.esc:
                self._triggered = True
                self._stop_event.set()
                logger.warning("EMERGENCY STOP TRIGGERED")
        except Exception as e:
            logger.error(f"EmergencyStop key press error: {e}")

    def _on_key_release(self, key):
        """Handle key release."""
        pass

    @property
    def triggered(self) -> bool:
        return self._triggered

    @property
    def should_stop(self) -> bool:
        return self._triggered or self._stop_event.is_set()

    def reset(self):
        """Reset emergency stop."""
        self._triggered = False
        self._stop_event.clear()
        logger.info("EmergencyStop reset")

    def stop(self):
        """Stop listening."""
        if self._listener:
            self._listener.stop()
            self._listener = None

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for emergency stop signal."""
        return self._stop_event.wait(timeout)


def create_safety_layer(
    enable_logging: bool = True,
    log_path: str = "logs/desktop_actions.log",
    emergency_stop: bool = True,
    default_timeout: int = 30,
) -> SafetyLayer:
    """Factory function to create SafetyLayer."""
    return SafetyLayer(
        enable_logging=enable_logging,
        log_path=log_path,
        enable_emergency_stop=emergency_stop,
        default_timeout=default_timeout,
    )
