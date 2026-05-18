"""
Desktop Agent Tool

JARVIS Tool that provides desktop automation as structured function calls.
Inherits from BaseTool and provides OpenAI function schemas.
"""

import logging

from assistant.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Import DesktopAgent
from assistant.desktop_agent import DesktopAgent, WorkflowEngine
from assistant.desktop_agent.safety import SafetyLayer


class DesktopAgentTool(BaseTool):
    """
    Tool for desktop automation.

    Provides all DesktopAgent methods as callable tools with
    OpenAI function schema definitions.
    """

    name: str = "desktop_agent"
    description: str = "Control the desktop: click, type, open apps, manage windows, automate workflows"
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The action to execute: click, type_text, press, hotkey, open_app, close_app, focus_window, move_window, list_windows, search_files, list_folder, copy_text, paste, take_screenshot, ocr, run_workflow",
            },
            "x": {
                "type": "integer",
                "description": "X coordinate for mouse actions",
            },
            "y": {
                "type": "integer",
                "description": "Y coordinate for mouse actions",
            },
            "text": {
                "type": "string",
                "description": "Text to type or copy",
            },
            "key": {
                "type": "string",
                "description": "Key to press (enter, esc, tab, space, etc.)",
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keys for hotkey combination",
            },
            "path_or_name": {
                "type": "string",
                "description": "Application path or name",
            },
            "title": {
                "type": "string",
                "description": "Window title to match",
            },
            "query": {
                "type": "string",
                "description": "Search query",
            },
            "workflow_name": {
                "type": "string",
                "description": "Workflow name to execute",
            },
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle"],
                "description": "Mouse button",
            },
            "clicks": {
                "type": "integer",
                "description": "Number of clicks",
            },
        },
        "required": ["command"],
    }

    def __init__(self):
        super().__init__()
        self._agent: DesktopAgent | None = None
        self._workflow_engine: WorkflowEngine | None = None
        self._safety_layer: SafetyLayer | None = None

    def _get_agent(self) -> DesktopAgent:
        if self._agent is None:
            self._safety_layer = SafetyLayer()
            self._agent = DesktopAgent(safety_layer=self._safety_layer)
        return self._agent

    def _get_workflow_engine(self) -> WorkflowEngine:
        if self._workflow_engine is None:
            self._workflow_engine = WorkflowEngine(desktop_agent=self._get_agent())
        return self._workflow_engine

    async def execute(self, **kwargs) -> ToolResult:
        """Execute a desktop agent command."""
        command = kwargs.get("command", "").lower()

        try:
            agent = self._get_agent()

            # Mouse commands
            if command == "click":
                x = kwargs.get("x")
                y = kwargs.get("y")
                button = kwargs.get("button", "left")
                clicks = kwargs.get("clicks", 1)
                success = agent.click(x, y, button, clicks)
                return ToolResult(success=success, result=f"Clicked at ({x}, {y})")

            if command == "double_click":
                x = kwargs.get("x")
                y = kwargs.get("y")
                success = agent.double_click(x, y)
                return ToolResult(
                    success=success, result=f"Double-clicked at ({x}, {y})"
                )

            if command == "right_click":
                x = kwargs.get("x")
                y = kwargs.get("y")
                success = agent.right_click(x, y)
                return ToolResult(
                    success=success, result=f"Right-clicked at ({x}, {y})"
                )

            if command == "move_mouse":
                x = kwargs.get("x", 0)
                y = kwargs.get("y", 0)
                success = agent.move_mouse(x, y)
                return ToolResult(success=success, result=f"Moved to ({x}, {y})")

            if command == "drag":
                x1 = kwargs.get("x", 0)
                y1 = kwargs.get("y", 0)
                x2 = kwargs.get("x2", 0)
                y2 = kwargs.get("y2", 0)
                success = agent.drag(x1, y1, x2, y2)
                return ToolResult(
                    success=success, result=f"Dragged from ({x1},{y1}) to ({x2},{y2})"
                )

            if command == "scroll":
                clicks = kwargs.get("clicks", 3)
                success = agent.scroll(clicks)
                return ToolResult(success=success, result=f"Scrolled {clicks} clicks")

            # Keyboard commands
            if command == "type_text":
                text = kwargs.get("text", "")
                success = agent.type_text(text)
                return ToolResult(success=success, result=f"Typed: {text}")

            if command == "press":
                key = kwargs.get("key", "enter")
                success = agent.press(key)
                return ToolResult(success=success, result=f"Pressed: {key}")

            if command == "hotkey":
                keys = kwargs.get("keys", [])
                if keys:
                    success = agent.hotkey(*keys)
                    return ToolResult(
                        success=success, result=f"Hotkey: {'+'.join(keys)}"
                    )
                return ToolResult(success=False, result=None, error="No keys specified")

            # App/Window commands
            if command == "open_app":
                path_or_name = kwargs.get("path_or_name", "")
                success = agent.open_app(path_or_name)
                return ToolResult(success=success, result=f"Opened: {path_or_name}")

            if command == "close_app":
                name = kwargs.get("path_or_name", "")
                success = agent.close_app(name)
                return ToolResult(success=success, result=f"Closed: {name}")

            if command == "focus_window":
                title = kwargs.get("title", "")
                success = agent.focus_window(title)
                return ToolResult(success=success, result=f"Focused: {title}")

            if command == "list_windows":
                windows = agent.list_windows()
                return ToolResult(success=True, result=windows)

            if command == "move_window":
                title = kwargs.get("title", "")
                x = kwargs.get("x", 0)
                y = kwargs.get("y", 0)
                w = kwargs.get("w")
                h = kwargs.get("h")
                success = agent.move_window(title, x, y, w, h)
                return ToolResult(success=success, result=f"Moved window: {title}")

            # File commands
            if command == "open_file":
                path = kwargs.get("path_or_name", "")
                success = agent.open_file(path)
                return ToolResult(success=success, result=f"Opened: {path}")

            if command == "search_files":
                query = kwargs.get("query", "")
                results = agent.search_files(query)
                return ToolResult(success=True, result=results)

            if command == "list_folder":
                path = kwargs.get("path_or_name", ".")
                items = agent.list_folder(path)
                return ToolResult(success=True, result=items)

            # Clipboard commands
            if command == "copy_text":
                text = kwargs.get("text", "")
                success = agent.copy_text(text)
                return ToolResult(success=success, result=f"Copied: {text}")

            if command == "paste":
                success = agent.paste()
                return ToolResult(success=success, result="Pasted")

            if command == "get_clipboard":
                text = agent.get_clipboard_text()
                return ToolResult(success=text is not None, result=text)

            # Screen commands
            if command == "take_screenshot":
                path = kwargs.get("path", "screenshots/screen.png")
                from pathlib import Path

                Path("screenshots").mkdir(exist_ok=True)

                from assistant.desktop_agent.vision import ScreenVision

                sv = ScreenVision()
                success = sv.save_screenshot(path)
                return ToolResult(success=success, result=f"Saved to {path}")

            if command == "ocr":
                from assistant.desktop_agent.vision import ScreenVision

                sv = ScreenVision(ocr_enabled=True)
                text = sv.ocr_screen()
                return ToolResult(success=bool(text), result=text)

            if command == "find_image":
                template_path = kwargs.get("template_path", "")
                from assistant.desktop_agent.vision import ScreenVision

                sv = ScreenVision()
                pos = sv.find_image(template_path)
                return ToolResult(success=pos is not None, result=pos)

            # Workflow commands
            if command == "run_workflow":
                workflow_name = kwargs.get("workflow_name", "")
                engine = self._get_workflow_engine()
                result = await engine.run(workflow_name)
                return ToolResult(
                    success=result.get("success", False),
                    result=result,
                )

            if command == "list_workflows":
                engine = self._get_workflow_engine()
                workflows = engine.list_workflows()
                return ToolResult(
                    success=True,
                    result=[wf.name for wf in workflows],
                )

            # Utility
            if command == "wait":
                seconds = kwargs.get("seconds", 1)
                agent.wait(seconds)
                return ToolResult(success=True, result=f"Waited {seconds}s")

            if command == "get_screen_size":
                size = agent.get_screen_size()
                return ToolResult(success=True, result=size)

            if command == "get_cursor_position":
                pos = agent.get_cursor_position()
                return ToolResult(success=True, result=pos)

            return ToolResult(
                success=False,
                result=None,
                error=f"Unknown command: {command}",
            )

        except Exception as e:
            logger.error(f"DesktopAgentTool execution error: {e}")
            return ToolResult(success=False, result=None, error=str(e))

    def get_tool_schema(self) -> list[dict]:
        """Get OpenAI function schema for all desktop agent methods."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "desktop_click",
                    "description": "Click the mouse at specified coordinates or current position",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer", "description": "X coordinate"},
                            "y": {"type": "integer", "description": "Y coordinate"},
                            "button": {
                                "type": "string",
                                "enum": ["left", "right", "middle"],
                                "default": "left",
                            },
                            "clicks": {"type": "integer", "default": 1},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_type",
                    "description": "Type text using the keyboard",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Text to type"},
                        },
                        "required": ["text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_press",
                    "description": "Press a single key",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "Key name (enter, esc, tab, space, etc.)",
                            },
                        },
                        "required": ["key"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_hotkey",
                    "description": "Press a key combination (hotkey)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keys": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Keys to press together",
                            },
                        },
                        "required": ["keys"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_open_app",
                    "description": "Open an application by name or path",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "App name or path",
                            },
                        },
                        "required": ["name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_close_app",
                    "description": "Close an application by name",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "App name"},
                        },
                        "required": ["name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_focus_window",
                    "description": "Focus (activate) a window by title",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Window title to match",
                            },
                        },
                        "required": ["title"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_list_windows",
                    "description": "List all visible windows",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_move_window",
                    "description": "Move and optionally resize a window",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "w": {"type": "integer"},
                            "h": {"type": "integer"},
                        },
                        "required": ["title", "x", "y"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_search_files",
                    "description": "Search for files by name",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_list_folder",
                    "description": "List contents of a folder",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "default": "."},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_copy_text",
                    "description": "Copy text to clipboard",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                        },
                        "required": ["text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_paste",
                    "description": "Paste clipboard content at current position",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_take_screenshot",
                    "description": "Take a screenshot",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "default": "screenshots/screen.png",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_ocr",
                    "description": "Read text from screen using OCR",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_workflow",
                    "description": "Execute a named workflow",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Workflow name"},
                        },
                        "required": ["name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_wait",
                    "description": "Wait for specified seconds",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "seconds": {"type": "number", "default": 1},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "desktop_screen_info",
                    "description": "Get screen size or cursor position",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "info": {"type": "string", "enum": ["size", "cursor"]},
                        },
                        "required": ["info"],
                    },
                },
            },
        ]


# Singleton instance
_desktop_agent_tool: DesktopAgentTool | None = None


def get_desktop_agent_tool() -> DesktopAgentTool:
    """Get DesktopAgentTool singleton."""
    global _desktop_agent_tool
    if _desktop_agent_tool is None:
        _desktop_agent_tool = DesktopAgentTool()
    return _desktop_agent_tool
