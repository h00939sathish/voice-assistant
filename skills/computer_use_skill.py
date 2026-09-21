"""
Computer Use Skill — Unified app, window, system, and screen control.

Replaces: app_integration_skill, window_manager_skill, quick_actions_skill, system_skill
"""

import asyncio
import base64
import ctypes
import io
import logging
import os
import platform
import re
import subprocess
import time
from typing import Any

import pyautogui

from assistant.uia_utils import (
    _UIA_AVAILABLE,
)
from assistant.uia_utils import (
    click_element as uia_click,
)
from assistant.uia_utils import (
    find_elements as uia_find,
)
from assistant.uia_utils import (
    get_element_info as uia_element_info,
)
from assistant.uia_utils import (
    list_visible as uia_list,
)
from assistant.uia_utils import (
    wait_for_element as uia_wait,
)
from skills.base_skill import BaseSkill, skill

logger = logging.getLogger("buddy.computer_use")

IS_WINDOWS = platform.system() == "Windows"

_SW_MINIMIZE = 6
_SW_MAXIMIZE = 3
_SW_RESTORE = 9
_WM_CLOSE = 0x0010

_OCR_AVAILABLE = False
try:
    import pytesseract

    _OCR_AVAILABLE = True
except ImportError:
    pass


@skill(
    name="computer_use",
    keywords=[
        "open app",
        "launch",
        "minimize",
        "maximize",
        "restore window",
        "close window",
        "switch to",
        "focus on",
        "lock computer",
        "shutdown",
        "restart",
        "sleep",
        "mute",
        "volume",
        "gaming mode",
        "screen",
        "what's on my screen",
        "click on",
        "find on screen",
    ],
    description="Control apps, windows, system settings, and screen. Launch, manage windows, lock/shutdown/mute, or ask about what's visible.",
    priority=8,
)
class ComputerUseSkill(BaseSkill):

    _KEY_MAP = {
        "ctrl": 0x11, "control": 0x11,
        "alt": 0x12,
        "shift": 0x10,
        "win": 0x5B, "windows": 0x5B, "cmd": 0x5B,
        "tab": 0x09,
        "c": 0x43, "v": 0x56, "x": 0x58, "z": 0x5A, "a": 0x41,
        "d": 0x44, "s": 0x53, "f": 0x46, "t": 0x54, "n": 0x4E,
        "esc": 0x1B, "escape": 0x1B,
        "enter": 0x0D, "return": 0x0D,
        "space": 0x20,
        "delete": 0x2E, "del": 0x2E,
        "backspace": 0x08,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
        "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
        "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
        "1": 0x30, "2": 0x31, "3": 0x32, "4": 0x33, "5": 0x34,
        "6": 0x35, "7": 0x36, "8": 0x37, "9": 0x38, "0": 0x39,
    }

    def __init__(self):
        super().__init__()
        self._controller = None
        self._controller_loaded = False
        self._user32 = ctypes.windll.user32 if IS_WINDOWS else None
        self._state = {
            "focused_window": None,
            "last_action": None,
        }

    def _get_controller(self):
        if not self._controller_loaded:
            try:
                from assistant.app_controller import AppController

                self._controller = AppController()
                self._controller_loaded = True
            except Exception as e:
                logger.error(f"Failed to load AppController: {e}")
        return self._controller

    # ------------------------------------------------------------------
    # Tool schema
    # ------------------------------------------------------------------

    def get_tool_schema(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "computer_use",
                    "description": "Control apps, windows, system settings, or ask about what's on screen",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "enum": [
                                    "launch_app",
                                    "control_window",
                                    "system_action",
                                    "app_command",
                                    "screen_question",
                                    "keyboard",
                                    "accessibility",
                                ],
                                "description": "What type of action to perform",
                            },
                            "app": {
                                "type": "string",
                                "description": "App name for launch_app or app_command (e.g. spotify, chrome, discord)",
                            },
                            "action": {
                                "type": "string",
                                "description": "For control_window: minimize/maximize/restore/close/switch_to. For system_action: lock/sleep/shutdown/restart/mute/gaming_mode/volume",
                            },
                            "target": {
                                "type": "string",
                                "description": "Window title or app name to switch to",
                            },
                            "query": {
                                "type": "string",
                                "description": "Search query, song name, or screen question",
                            },
                            "level": {
                                "type": "integer",
                                "description": "Volume level 0-100",
                            },
                            "message": {
                                "type": "string",
                                "description": "Text message to send",
                            },
                            "contact": {
                                "type": "string",
                                "description": "Contact name for messaging apps",
                            },
                            "keys": {
                                "type": "string",
                                "description": "Keyboard shortcut for keyboard command (e.g. 'ctrl+c', 'alt+tab', 'win+d')",
                            },
                            "uia_action": {
                                "type": "string",
                                "enum": ["list", "find", "click", "info", "wait_for"],
                                "description": "Accessibility tree action: list visible elements, find by name/role, click element, get element info, or wait for element",
                            },
                            "uia_target": {
                                "type": "string",
                                "description": "Element name or role for accessibility action",
                            },
                            "uia_role": {
                                "type": "string",
                                "description": "Element role filter for accessibility find action (e.g. Button, Edit, Window)",
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Timeout in seconds for accessibility wait_for action (default 5)",
                            },
                        },
                        "required": ["command"],
                    },
                },
            }
        ]

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    async def handle(self, text: str, context: Any) -> str | None:
        intent = self._classify_intent(text)
        if intent is None:
            return None

        cmd = intent["type"]

        if cmd == "launch":
            return await self._launch_app(intent.get("app", ""))
        if cmd == "window":
            return await self._control_window(
                intent.get("action", ""), intent.get("target")
            )
        if cmd == "system":
            return await self._system_action(intent.get("action", ""), intent)
        if cmd == "app_command":
            return await self._app_command(intent)
        if cmd == "screen":
            return await self._screen_question(intent.get("query", ""))
        if cmd == "keyboard":
            return self._send_keys(intent.get("keys", ""))
        if cmd == "accessibility":
            return await self._accessibility_action(intent)

        return None

    async def handle_tool_call(self, args: dict, context: Any) -> str:
        cmd = args.get("command", "")
        if cmd == "launch_app":
            return await self._launch_app(args.get("app", ""))
        if cmd == "control_window":
            return await self._control_window(
                args.get("action", "switch_to"), args.get("target")
            )
        if cmd == "system_action":
            return await self._system_action(args.get("action", ""), args)
        if cmd == "app_command":
            return await self._app_command(args)
        if cmd == "screen_question":
            return await self._screen_question(args.get("query", ""))
        if cmd == "keyboard":
            return self._send_keys(args.get("keys", ""))
        if cmd == "accessibility":
            return await self._accessibility_action(args)
        return f"Unknown computer_use command: {cmd}"

    # ------------------------------------------------------------------
    # Intent classification
    # ------------------------------------------------------------------

    _LAUNCH_PATTERNS = re.compile(
        r"(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?(.+)", re.I
    )
    _WINDOW_ACTIONS = {
        "minimize": r"\bminimize\b",
        "maximize": r"\bmaximize\b",
        "restore": r"\brestore\b",
        "close": r"(?:close|kill)\s+(?:this\s+|the\s+|current\s+)?window",
        "switch_to": r"(?:switch\s+to|focus\s+(?:on\s+)?|go\s+to)\s+(.+)",
        "show_desktop": r"(?:show\s+desktop|hide\s+all\s+windows)",
    }
    _SYSTEM_ACTIONS = {
        "lock": r"\block\b",
        "sleep": r"\bsleep\b",
        "shutdown": r"\bshut\s*down\b",
        "restart": r"\bre(start|boot)\b",
        "mute": r"\bmute\b",
        "gaming_mode": r"\bgaming\s*mode\b",
        "volume": r"\bvolume\b",
    }
    _APP_COMMANDS = {
        "spotify": [r"\bspotify\b", r"\bplay\b", r"\bpause\b", r"\bnext\b", r"\bskip\b"],
        "discord": [r"\bdiscord\b", r"\bsend\b", r"\bmessage\b"],
        "whatsapp": [r"\bwhatsapp\b", r"\bsend\b", r"\bmessage\b"],
        "chrome": [r"\bchrome\b", r"\bsearch\b", r"\bgoogle\b"],
    }
    _SCREEN_PATTERNS = re.compile(
        r"(?:what'?s?\s+on\s+(?:my\s+)?screen|click\s+on|find\s+on\s+screen|what\s+do\s+(?:you\s+)?see|describe\s+screen)",
        re.I,
    )

    def _classify_intent(self, text: str) -> dict | None:
        t = text.strip()
        if not t:
            return None

        # Screen vision
        if self._SCREEN_PATTERNS.search(t):
            return {"type": "screen", "query": t}

        # Launch app
        m = self._LAUNCH_PATTERNS.match(t)
        if m:
            app = m.group(1).strip().rstrip(".")
            if app:
                return {"type": "launch", "app": app}

        # Control window
        for action, pattern in self._WINDOW_ACTIONS.items():
            if action == "switch_to":
                sm = re.search(pattern, t, re.I)
                if sm and sm.group(1):
                    return {"type": "window", "action": action, "target": sm.group(1).strip()}
            elif action == "show_desktop":
                if re.search(pattern, t, re.I):
                    return {"type": "window", "action": "show_desktop"}
            else:
                if re.search(pattern, t, re.I):
                    return {"type": "window", "action": action}

        # System action
        for action, pattern in self._SYSTEM_ACTIONS.items():
            if re.search(pattern, t, re.I):
                if action == "volume":
                    vm = re.search(r"(\d+)", t)
                    level = int(vm.group(1)) if vm else None
                    return {"type": "system", "action": action, "level": level}
                return {"type": "system", "action": action}

        # App commands (spotify play/pause/next etc.)
        if re.search(r"\bplay\b", t, re.I) and re.search(r"\b(?:music|song|track)\b", t, re.I):
            qm = re.search(r"play\s+(.+?)(?:\s+on\s+spotify)?$", t, re.I)
            return {"type": "app_command", "app": "spotify", "action": "play", "query": qm.group(1).strip() if qm else ""}
        if re.search(r"\bplay\b", t, re.I) and re.search(r"\bspotify\b", t, re.I):
            qm = re.search(r"play\s+(.+?)\s+on\s+spotify", t, re.I)
            return {"type": "app_command", "app": "spotify", "action": "play", "query": qm.group(1).strip() if qm else "play"}
        if re.search(r"\bpause\b", t, re.I) and re.search(r"\bspotify|music\b", t, re.I):
            return {"type": "app_command", "app": "spotify", "action": "pause"}
        if re.search(r"\bnext\b.*\bsong\b|\bskip\b", t, re.I):
            return {"type": "app_command", "app": "spotify", "action": "next"}

        # Messaging commands
        dm = re.search(r"(?:send|message)\s+(.+?)(?:\s+on\s+discord)?$", t, re.I)
        if dm and re.search(r"\bdiscord\b", t, re.I):
            return {"type": "app_command", "app": "discord", "action": "send", "message": dm.group(1).strip()}
        wm = re.search(r"(?:send|message)\s+(.+?)(?:\s+to\s+(.+?))?(?:\s+on\s+whatsapp)?$", t, re.I)
        if wm and re.search(r"\bwhatsapp\b", t, re.I):
            result = {"type": "app_command", "app": "whatsapp", "action": "send", "message": wm.group(1).strip()}
            if wm.group(2):
                result["contact"] = wm.group(2).strip()
            return result

        # Browser search
        if re.search(r"\bsearch\b", t, re.I) and re.search(r"\bchrome|google\b", t, re.I):
            sm = re.search(r"search\s+(?:for\s+)?(.+?)(?:\s+on\s+chrome|\s+in\s+chrome)?$", t, re.I)
            if sm:
                return {"type": "app_command", "app": "chrome", "action": "search", "query": sm.group(1).strip()}

        # Keyboard combos
        km = re.search(r"(?:press|hit|send)\s+(.+?)(?:\s+key(?:board)?)?$", t, re.I)
        if km:
            keys = km.group(1).strip().lower()
            if any(k in keys for k in ("ctrl", "alt", "shift", "win", "cmd")):
                return {"type": "keyboard", "keys": keys}

        # Accessibility
        if re.search(r"(?:list|show|what)\s+(?:ui\s+)?(?:elements?|controls?|tree)", t, re.I):
            return {"type": "accessibility", "uia_action": "list"}
        if re.search(r"find\s+(element|button|field|control)", t, re.I):
            fm = re.search(r"(?:named|called|with\s+(?:name|text))\s+\"?([^\"]+)\"?", t, re.I)
            if fm:
                return {"type": "accessibility", "uia_action": "find", "uia_target": fm.group(1).strip()}
        am = re.search(r"(?:click|press|tap)\s+(?:the\s+)?(?:button|element|link)\s+(?:named|called)\s+\"?([^\"]+)\"?", t, re.I)
        if am:
            return {"type": "accessibility", "uia_action": "click", "uia_target": am.group(1).strip()}

        return None

    # ------------------------------------------------------------------
    # Launch app
    # ------------------------------------------------------------------

    async def _launch_app(self, app_name: str) -> str:
        if not app_name:
            return "What app would you like to open?"
        controller = self._get_controller()
        if not controller:
            return "App controller unavailable."
        return await asyncio.to_thread(controller.launch_by_name, app_name)

    # ------------------------------------------------------------------
    # Control window
    # ------------------------------------------------------------------

    async def _control_window(self, action: str, target: str | None = None) -> str:
        if not IS_WINDOWS:
            return "Window control is Windows-only."

        if action == "show_desktop":
            self._user32.keybd_event(0x5B, 0, 0, 0)
            self._user32.keybd_event(0x44, 0, 0, 0)
            self._user32.keybd_event(0x44, 0, 2, 0)
            self._user32.keybd_event(0x5B, 0, 2, 0)
            return "Showing desktop."

        if action == "switch_to" and target:
            hwnd = self._find_window(target)
            if not hwnd:
                return f"No window matching '{target}' found."
            return self._focus_window(hwnd)

        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return "No active window found."

        if action == "minimize":
            self._user32.ShowWindow(hwnd, _SW_MINIMIZE)
            return "Minimized."
        if action == "maximize":
            self._user32.ShowWindow(hwnd, _SW_MAXIMIZE)
            return "Maximized."
        if action == "restore":
            self._user32.ShowWindow(hwnd, _SW_RESTORE)
            return "Restored."
        if action == "close":
            self._user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
            return "Closed active window."

        return f"Unknown window action: {action}"

    def _find_window(self, target: str) -> int | None:
        target_lower = target.lower()
        found = []

        def enum_handler(hwnd, _):
            if self._user32.IsWindowVisible(hwnd):
                length = self._user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    self._user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    if target_lower in title.lower():
                        found.append(hwnd)
            return True

        WndEnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)  # noqa: N806 -- Win32 callback type convention
        self._user32.EnumWindows(WndEnumProc(enum_handler), 0)
        return found[0] if found else None

    def _focus_window(self, hwnd: int) -> str:
        title_buf = ctypes.create_unicode_buffer(256)
        self._user32.GetWindowTextW(hwnd, title_buf, 256)
        title = title_buf.value

        self._user32.keybd_event(0x12, 0, 0, 0)
        self._user32.keybd_event(0x12, 0, 2, 0)
        self._user32.SetForegroundWindow(hwnd)
        if self._user32.IsIconic(hwnd):
            self._user32.ShowWindow(hwnd, _SW_RESTORE)
        self._update_state(focused_window=title)
        return f"Switched to {title}."

    # ------------------------------------------------------------------
    # System action
    # ------------------------------------------------------------------

    async def _system_action(self, action: str, context: Any) -> str:
        if action == "lock":
            if IS_WINDOWS:
                ctypes.windll.user32.LockWorkStation()
                return "Locking your computer."
            return "Lock is only supported on Windows."

        if action == "sleep":
            if IS_WINDOWS:
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            elif platform.system() == "Darwin":
                os.system("pmset sleepnow")
            else:
                os.system("systemctl suspend")
            return "Going to sleep."

        if action == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "30"], shell=False)
            return "Shutdown scheduled in 30 seconds. Say 'shutdown /a' to cancel."

        if action == "restart":
            subprocess.Popen(["shutdown", "/r", "/t", "30"], shell=False)
            return "Restart scheduled in 30 seconds."

        if action == "mute":
            controller = self._get_controller()
            if controller:
                return await asyncio.to_thread(controller.keyboard_mute)
            return "Controller unavailable."

        if action == "gaming_mode":
            try:
                from assistant.config_manager import Config

                Config.GAMING_MODE = not Config.GAMING_MODE
                status = "enabled" if Config.GAMING_MODE else "disabled"
                return f"Gaming mode {status}."
            except ImportError:
                return "Config manager not available."

        if action == "volume":
            controller = self._get_controller()
            if controller:
                level = context.get("level") if isinstance(context, dict) else None
                if level is not None:
                    return await asyncio.to_thread(controller.set_volume, level)
                return await asyncio.to_thread(controller.change_volume, 0)
            return "Volume control unavailable."

        return f"Unknown system action: {action}"

    # ------------------------------------------------------------------
    # App command (Spotify, Chrome, Discord, WhatsApp)
    # ------------------------------------------------------------------

    async def _app_command(self, intent: dict) -> str:
        app = intent.get("app", "").lower()
        action = intent.get("action", "")
        query = intent.get("query", "")
        message = intent.get("message", "")
        contact = intent.get("contact", "")

        if app == "spotify":
            return await self._spotify_command(action, query)
        if app == "discord":
            return await self._messaging_command("discord", message)
        if app == "whatsapp":
            return await self._messaging_command("whatsapp", message, contact)
        if app == "chrome":
            return await self._browser_command("chrome", action, query)

        return f"App '{app}' is not yet supported."

    async def _spotify_command(self, action: str, query: str = "") -> str:
        try:
            from assistant.spotify_controller import get_spotify_controller

            spotify = get_spotify_controller()
            if spotify.is_available:
                if action == "play" and query:
                    return spotify.search_and_play(query)
                if action == "play":
                    return spotify.play()
                if action == "pause":
                    return spotify.pause()
                if action == "next":
                    return spotify.next_track()
        except Exception:
            logger.info("Spotify API unavailable, falling back to keyboard")

        controller = self._get_controller()
        if not controller:
            return "Spotify controller unavailable."
        if not await asyncio.to_thread(controller.is_app_running, "spotify"):
            await asyncio.to_thread(controller.launch_app, "spotify")
            await asyncio.sleep(2.5)

        if action == "play" and query:
            return await asyncio.to_thread(
                controller.execute_command, "spotify", "search", query=query
            )
        if action == "play":
            return await asyncio.to_thread(controller.execute_command, "spotify", "play")
        if action == "pause":
            return await asyncio.to_thread(controller.execute_command, "spotify", "pause")
        if action == "next":
            return await asyncio.to_thread(controller.execute_command, "spotify", "next")
        return f"Unknown spotify action: {action}"

    async def _messaging_command(self, app: str, message: str, contact: str = "") -> str:
        controller = self._get_controller()
        if not controller:
            return "Controller unavailable."
        if not await asyncio.to_thread(controller.is_app_running, app):
            await asyncio.to_thread(controller.launch_app, app)
            await asyncio.sleep(1.5)
        if contact:
            await asyncio.to_thread(
                controller.execute_command, app, "search_contact", contact=contact
            )
            time.sleep(0.5)
        return await asyncio.to_thread(
            controller.execute_command, app, "send_message", message=message
        )

    async def _browser_command(self, browser: str, action: str, query: str = "") -> str:
        controller = self._get_controller()
        if not controller:
            return "Controller unavailable."
        if not await asyncio.to_thread(controller.is_app_running, browser):
            await asyncio.to_thread(controller.launch_app, browser)
            await asyncio.sleep(1.2)
        if action == "search" and query:
            return await asyncio.to_thread(
                controller.execute_command, browser, "search", query=query
            )
        if action == "go_to" and query:
            return await asyncio.to_thread(
                controller.execute_command, browser, "go_to", url=query
            )
        if action == "new_tab":
            return await asyncio.to_thread(controller.execute_command, browser, "new_tab")
        return f"Browser action '{action}' not recognized."

    # ------------------------------------------------------------------
    # Screen vision
    # ------------------------------------------------------------------

    async def _screen_question(self, query: str) -> str:
        try:
            screenshot = await asyncio.to_thread(pyautogui.screenshot)
        except Exception as e:
            return f"Failed to capture screen: {e}"

        result = await self._vision_llm(screenshot, query)
        if result:
            return result

        result = self._vision_ocr(screenshot, query)
        if result:
            return result

        return "I couldn't analyze the screen right now."

    async def _vision_llm(self, screenshot, query: str) -> str | None:
        try:
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

            from assistant.conversation_memory import ConversationMemory
            from assistant.llm_router import LLMRouter

            mem = ConversationMemory()
            router = LLMRouter(conversation_memory=mem)

            data_url = f"data:image/png;base64,{b64}"
            img_tag = f'![screenshot]({data_url})'

            prompt = (
                f"Analyze this screenshot. The user asks: {query}\n\n"
                f"If the user wants to click something, return ONLY a JSON object with:\n"
                f'{{"action": "click", "x": <int>, "y": <int>, "target": "<what to click>"}}\n\n'
                f"If the user wants to know what's on screen, describe it naturally.\n"
                f"If the user wants to type something, return:\n"
                f'{{"action": "type", "text": "<text to type>"}}\n\n'
                f"{img_tag}"
            )

            response = await asyncio.wait_for(
                router.chat(prompt), timeout=30
            )

            import json

            try:
                parsed = json.loads(response.strip())
                action = parsed.get("action")
                if action == "click":
                    x, y = parsed.get("x"), parsed.get("y")
                    if x is not None and y is not None:
                        await asyncio.to_thread(pyautogui.click, x, y)
                        target = parsed.get("target", "target")
                        return f"Clicked on {target}."
                if action == "type":
                    text = parsed.get("text", "")
                    if text:
                        await asyncio.to_thread(pyautogui.write, text, interval=0.02)
                        return f"Typed: {text}"
            except (json.JSONDecodeError, KeyError):
                pass

            return response
        except Exception as e:
            logger.warning(f"LLM vision failed: {e}")
            return None

    def _vision_ocr(self, screenshot, query: str) -> str | None:
        if not _OCR_AVAILABLE:
            return None
        try:
            text = pytesseract.image_to_string(screenshot)
            text = text.strip()
            if not text:
                return "I can see the screen but couldn't read any text."
            if "find" in query.lower() or "search" in query.lower():
                words = query.lower().replace("find", "").replace("search", "").replace("for", "").strip()
                if words and words in text.lower():
                    return f"I found '{words}' on the screen."
            return f"I can read this text on screen: {text[:500]}"
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return None

    # ------------------------------------------------------------------
    # State tracking
    # ------------------------------------------------------------------

    def _update_state(self, focused_window: str | None = None, last_action: str = ""):
        if focused_window:
            self._state["focused_window"] = focused_window
        if last_action:
            self._state["last_action"] = last_action

    async def wait_for_window(self, title: str, timeout: float = 10.0) -> str:
        """Wait for a window matching title to appear (polling UIA)."""
        start = time.time()
        while time.time() - start < timeout:
            if IS_WINDOWS and _UIA_AVAILABLE:
                result = uia_wait(title, timeout=2.0)
                if result:
                    self._update_state(focused_window=title)
                    return f"Window '{result['name']}' appeared."
            # Fallback: check window titles via win32
            if IS_WINDOWS:
                found = self._find_window(title)
                if found:
                    self._update_state(focused_window=title)
                    return f"Window '{title}' appeared."
            await asyncio.sleep(0.5)
        return f"Timed out waiting for '{title}' to appear."

    # ------------------------------------------------------------------
    # Keyboard combos
    # ------------------------------------------------------------------

    def _send_keys(self, keys: str) -> str:
        if not IS_WINDOWS:
            return "Keyboard combos are Windows-only."
        parts = [p.strip().lower() for p in keys.replace("+", " ").split()]
        mods = []
        vks = []
        for p in parts:
            vk = self._KEY_MAP.get(p)
            if vk is None:
                return f"Unknown key: {p}"
            if p in ("ctrl", "control", "alt", "shift", "win", "windows", "cmd"):
                mods.append(vk)
            else:
                vks.append(vk)
        if not mods and not vks:
            return "No valid keys specified."
        for vk in mods:
            self._user32.keybd_event(vk, 0, 0, 0)
        for vk in vks:
            self._user32.keybd_event(vk, 0, 0, 0)
            self._user32.keybd_event(vk, 0, 2, 0)
        for vk in reversed(mods):
            self._user32.keybd_event(vk, 0, 2, 0)
        self._update_state(last_action=f"keyboard: {keys}")
        return f"Sent: {keys}"

    # ------------------------------------------------------------------
    # UIA / Accessibility tree
    # ------------------------------------------------------------------

    async def _accessibility_action(self, args: dict) -> str:
        if not IS_WINDOWS:
            return "Accessibility tree is Windows-only."
        if not _UIA_AVAILABLE:
            return "UIA module not available (install uiautomation)."

        action = args.get("uia_action", "")
        target = args.get("uia_target", "")
        role = args.get("uia_role", "")
        timeout = args.get("timeout", 5)

        if action == "list":
            tree = await asyncio.to_thread(uia_list, depth=2)
            if not tree:
                return "No UI elements found."
            lines = []
            def flatten(items, prefix=""):
                for item in items:
                    name = item.get("name", "")
                    role = item.get("role", "")
                    label = f"{name} ({role})" if name else f"({role})"
                    lines.append(f"{prefix}• {label}")
                    for child in item.get("children", []):
                        flatten([child], prefix + "  ")
            flatten(tree)
            return "UI elements:\n" + "\n".join(lines[:40])

        if action == "find":
            results = await asyncio.to_thread(uia_find, name=target, role=role, max_results=10)
            if not results:
                return f"No elements found matching '{target}'."
            lines = [f"{r.get('name','')} ({r.get('role','')})" for r in results]
            return f"Found {len(results)} element(s):\n" + "\n".join(lines)

        if action == "click":
            ok = await asyncio.to_thread(uia_click, target)
            if ok:
                self._update_state(last_action=f"clicked: {target}")
                return f"Clicked '{target}'."
            return f"Could not find or click '{target}'."

        if action == "info":
            info = await asyncio.to_thread(uia_element_info, target)
            if info:
                return f"Element '{target}':\n  Role: {info.get('role','')}\n  Rect: {info.get('rect','')}\n  Enabled: {info.get('enabled','')}"
            return f"No element '{target}' found on screen."

        if action == "wait_for":
            result = await self.wait_for_window(target, timeout=float(timeout))
            if result:
                return f"Element '{result['name']}' appeared."
            return f"Timed out waiting for '{target}'."

        return f"Unknown accessibility action: {action}"

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def help(self) -> str:
        return """
Computer Use Skill — Natural Commands:
• "open spotify" / "launch chrome"
• "minimize" / "maximize" / "restore"
• "close this window" / "switch to discord"
• "lock computer" / "shutdown" / "restart" / "sleep"
• "mute" / "volume 50"
• "play [song] on spotify"
• "send [message] on discord"
• "what's on my screen" / "click on the blue button"
• "press ctrl+c" / "alt+tab" / "win+d"
• "list UI elements" / "find element named Send" / "click button named Close"
• "enable gaming mode"
"""
