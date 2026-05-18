"""
Desktop Agent Skill

JARVIS Skill that provides desktop automation through natural language.
Inherits from BaseSkill and routes commands to DesktopAgent.
"""

import re
from pathlib import Path
from typing import Any

# Import DesktopAgent components
from assistant.desktop_agent import DesktopAgent, WorkflowEngine
from assistant.desktop_agent.safety import SafetyLayer
from skills.base_skill import BaseSkill, skill


@skill(
    name="desktop_agent",
    keywords=[
        "click",
        "type",
        "press",
        "hotkey",
        "key combo",
        "open app",
        "open application",
        "launch",
        "close app",
        "window",
        "focus",
        "minimize",
        "maximize",
        "move window",
        "search",
        "find file",
        "list folder",
        "open file",
        "screenshot",
        "screen capture",
        "ocr",
        "read text",
        "automation",
        "workflow",
        "macro",
        "script",
        "do something on my screen",
        " automate",
        "control desktop",
    ],
    description="Desktop automation: click, type, open apps, control windows, automate workflows",
    priority=3,
)
class DesktopAgentSkill(BaseSkill):
    """
    Skill for desktop automation via natural language.

    Maps voice/text commands to DesktopAgent actions:
    - Mouse: "click at 500 300", "double click", "right click"
    - Keyboard: "type hello", "press enter", "control c"
    - Apps: "open chrome", "close notepad"
    - Windows: "focus chrome", "minimize window", "move window"
    - Files: "search for resume", "open downloads"
    - Screen: "take screenshot", "read screen text"
    - Workflows: "run morning routine", "search google for..."
    """

    def __init__(self):
        super().__init__()
        self._agent: DesktopAgent | None = None
        self._workflow_engine: WorkflowEngine | None = None
        self._safety_layer: SafetyLayer | None = None

    def _get_agent(self) -> DesktopAgent:
        """Get or create DesktopAgent instance."""
        if self._agent is None:
            self._agent = DesktopAgent()
        return self._agent

    def _get_workflow_engine(self) -> WorkflowEngine:
        """Get or create WorkflowEngine instance."""
        if self._workflow_engine is None:
            self._workflow_engine = WorkflowEngine(desktop_agent=self._get_agent())
        return self._workflow_engine

    def _get_safety_layer(self) -> SafetyLayer:
        """Get or create SafetyLayer instance."""
        if self._safety_layer is None:
            self._safety_layer = SafetyLayer()
        return self._safety_layer

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        """Handle incoming command."""
        text_lower = text.lower()

        # Route to appropriate handler
        if any(w in text_lower for w in ["click", "double click", "right click"]):
            return await self._handle_click(text, context)

        if any(w in text_lower for w in ["type", "write", "enter text"]):
            return await self._handle_type(text, context)

        if "press" in text_lower or "hotkey" in text_lower:
            return await self._handle_press(text, context)

        if "open" in text_lower and any(
            w in text_lower for w in ["app", "application", "program"]
        ):
            return await self._handle_open_app(text, context)

        if "close" in text_lower and "app" in text_lower:
            return await self._handle_close_app(text, context)

        if "window" in text_lower:
            return await self._handle_window(text, context)

        if "search" in text_lower and "file" in text_lower:
            return await self._handle_search_files(text, context)

        if any(w in text_lower for w in ["list", "show files", "what's in"]):
            return await self._handle_list_folder(text, context)

        if "screenshot" in text_lower or "screen capture" in text_lower:
            return await self._handle_screenshot(text, context)

        if any(w in text_lower for w in ["ocr", "read text", "read screen"]):
            return await self._handle_ocr(text, context)

        if "workflow" in text_lower or "run" in text_lower:
            return await self._handle_workflow(text, context)

        if "browser" in text_lower and any(
            w in text_lower for w in ["search", "google"]
        ):
            return await self._handle_browser_search(text, context)

        # Help message
        return self._get_help_text()

    async def _handle_click(self, text: str, context: dict[str, Any]) -> str:
        """Handle click commands."""
        try:
            agent = self._get_agent()
            text_lower = text.lower()

            # Parse coordinates from text
            coords = self._extract_coordinates(text)

            if coords:
                x, y = coords
            else:
                # Use current position if not specified
                x, y = None, None

            # Determine click type
            if "double" in text_lower:
                agent.double_click(x, y)
                return f"Double-clicking at ({x}, {y})" if coords else "Double-clicking"
            elif "right" in text_lower:
                agent.right_click(x, y)
                return f"Right-clicking at ({x}, {y})" if coords else "Right-clicking"
            else:
                agent.click(x, y)
                return f"Clicking at ({x}, {y})" if coords else "Clicking"

        except Exception as e:
            return f"Click failed: {e}"

    async def _handle_type(self, text: str, context: dict[str, Any]) -> str:
        """Handle typing commands."""
        try:
            agent = self._get_agent()

            # Extract text to type
            match = re.search(r"type[:\s]+(.+)", text, re.IGNORECASE)
            if match:
                text_to_type = match.group(1).strip()
            else:
                # Try to get from after "type" keyword
                parts = text.lower().split("type")
                if len(parts) > 1:
                    text_to_type = parts[1].strip()
                else:
                    return "What would you like me to type?"

            agent.type_text(text_to_type)
            return f"Typing: {text_to_type}"

        except Exception as e:
            return f"Type failed: {e}"

    async def _handle_press(self, text: str, context: dict[str, Any]) -> str:
        """Handle key press commands."""
        try:
            agent = self._get_agent()
            text_lower = text.lower()

            # Hotkey
            if "hotkey" in text_lower or ("+" in text and len(text.split()) > 2):
                # Extract keys
                keys = []
                for key_name in [
                    "ctrl",
                    "alt",
                    "shift",
                    "win",
                    "enter",
                    "esc",
                    "tab",
                    "space",
                ]:
                    if key_name in text_lower:
                        keys.append(key_name)

                if keys:
                    agent.hotkey(*keys)
                    return f"Pressed: {'+'.join(keys)}"
                return "Invalid hotkey combination"

            # Single key press
            key = None
            for k in [
                "enter",
                "esc",
                "tab",
                "space",
                "backspace",
                "delete",
                "home",
                "end",
                "pageup",
                "pagedown",
            ]:
                if k in text_lower:
                    key = k
                    break

            if key:
                agent.press(key)
                return f"Pressed: {key}"

            return "What key would you like me to press?"

        except Exception as e:
            return f"Press failed: {e}"

    async def _handle_open_app(self, text: str, context: dict[str, Any]) -> str:
        """Handle open app commands."""
        try:
            agent = self._get_agent()

            # Extract app name
            app_name = text.lower()
            for prefix in ["open ", "launch ", "open application ", "open app "]:
                if prefix in app_name:
                    app_name = app_name.split(prefix)[1].strip()
                    break

            if not app_name:
                return "Which application would you like to open?"

            # Clean up
            app_name = app_name.strip(".\"'\n")

            self._get_safety_layer()  # Ensure logging

            success = agent.open_app(app_name)
            if success:
                return f"Opening {app_name}"
            return f"Could not open {app_name}"

        except Exception as e:
            return f"Open app failed: {e}"

    async def _handle_close_app(self, text: str, context: dict[str, Any]) -> str:
        """Handle close app commands."""
        try:
            agent = self._get_agent()

            # Extract app name
            match = re.search(r"close\s+(?:app\s+)?(.+)", text, re.IGNORECASE)
            if match:
                app_name = match.group(1).strip()
            else:
                return "Which application would you like to close?"

            success = agent.close_app(app_name)
            if success:
                return f"Closed {app_name}"
            return f"Could not close {app_name}"

        except Exception as e:
            return f"Close app failed: {e}"

    async def _handle_window(self, text: str, context: dict[str, Any]) -> str:
        """Handle window commands."""
        try:
            agent = self._get_agent()
            text_lower = text.lower()

            if "focus" in text_lower or "activate" in text_lower:
                # Extract window title
                match = re.search(r"(?:focus|activate)\s+(?:on\s+)?(.+)", text_lower)
                if match:
                    title = match.group(1).strip()
                    success = agent.focus_window(title)
                    if success:
                        return f"Focused {title}"
                    return f"Could not find window: {title}"

            if "minimize" in text_lower:
                pass  # Get from active window
                # Could extend to use _user32

            if "maximize" in text_lower:
                pass

            if "move" in text_lower:
                # Extract position
                coords = self._extract_coordinates(text)
                if coords:
                    pass  # Use move_window

            return (
                "I can focus, minimize, maximize, or move windows. What would you like?"
            )

        except Exception as e:
            return f"Window action failed: {e}"

    async def _handle_search_files(self, text: str, context: dict[str, Any]) -> str:
        """Handle file search."""
        try:
            agent = self._get_agent()

            # Extract query
            match = re.search(r"(?:search|find)\s+(?:for\s+)?(.+)", text, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
            else:
                query = text.lower().replace("search", "").replace("find", "").strip()

            results = agent.search_files(query)
            if results:
                return f"Found {len(results)} files:\n" + "\n".join(results[:5])
            return f"No files found for '{query}'"

        except Exception as e:
            return f"Search failed: {e}"

    async def _handle_list_folder(self, text: str, context: dict[str, Any]) -> str:
        """Handle list folder."""
        try:
            agent = self._get_agent()

            # Determine path
            path = "."
            if "downloads" in text.lower():
                path = str(Path.home() / "Downloads")
            elif "documents" in text.lower():
                path = str(Path.home() / "Documents")
            elif "desktop" in text.lower():
                path = str(Path.home() / "Desktop")

            items = agent.list_folder(path)
            if items:
                lines = [
                    f"{'[DIR] ' if i['is_dir'] else '[FILE] '}{i['name']}"
                    for i in items[:10]
                ]
                return "Contents:\n" + "\n".join(lines)
            return "Folder is empty"

        except Exception as e:
            return f"List failed: {e}"

    async def _handle_screenshot(self, text: str, context: dict[str, Any]) -> str:
        """Handle screenshot."""
        try:
            from assistant.desktop_agent.vision import ScreenVision

            sv = ScreenVision()
            path = "screenshots/screen.png"
            # Ensure directory exists
            from pathlib import Path

            Path("screenshots").mkdir(exist_ok=True)

            sv.save_screenshot(path)
            return f"Screenshot saved to {path}"

        except Exception as e:
            return f"Screenshot failed: {e}"

    async def _handle_ocr(self, text: str, context: dict[str, Any]) -> str:
        """Handle OCR."""
        try:
            from assistant.desktop_agent.vision import ScreenVision

            sv = ScreenVision(ocr_enabled=True)
            text = sv.ocr_screen()
            if text:
                return f"Screen text:\n{text[:500]}"
            return "Could not read text from screen"

        except Exception as e:
            return f"OCR failed: {e}"

    async def _handle_workflow(self, text: str, context: dict[str, Any]) -> str:
        """Handle workflow execution."""
        try:
            engine = self._get_workflow_engine()
            text_lower = text.lower()

            # Extract workflow name or build inline
            if "google" in text_lower and "search" in text_lower:
                query = (
                    text_lower.replace("run", "")
                    .replace("workflow", "")
                    .replace("google", "")
                    .replace("search", "")
                    .strip()
                )
                if query:
                    result = await engine.run("google_search", {"query": query})
                    return (
                        f"Searched Google for: {query}"
                        if result.get("success")
                        else "Search failed"
                    )

            # Check for registered workflow match
            for wf_name in engine.list_workflows():
                if wf_name.name in text_lower:
                    result = await engine.run(wf_name.name)
                    return (
                        f"Ran workflow: {wf_name.name}"
                        if result.get("success")
                        else "Workflow failed"
                    )

            return "Which workflow would you like to run?"

        except Exception as e:
            return f"Workflow failed: {e}"

    async def _handle_browser_search(self, text: str, context: dict[str, Any]) -> str:
        """Handle browser search workflow."""
        try:
            engine = self._get_workflow_engine()

            # Extract query
            match = re.search(r"(?:search|search for)\s+(.+)", text, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
            else:
                query = text.lower().split("search")[-1].strip()

            result = await engine.run("google_search", {"query": query})
            if result.get("success"):
                return f"Searching Google for: {query}"
            return "Search failed"

        except Exception as e:
            return f"Browser search failed: {e}"

    def _extract_coordinates(self, text: str) -> tuple[int, int] | None:
        """Extract x,y coordinates from text."""
        import re

        # Pattern: "at 500 300" or "at 500, 300"
        match = re.search(r"at\s+(\d+)[,\s]+(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))

        # Pattern: "500 300" (two numbers at end)
        match = re.search(r"(\d+)\s+(\d+)\s*$", text)
        if match:
            return int(match.group(1)), int(match.group(2))

        return None

    def _get_help_text(self) -> str:
        return """I can help you with desktop automation. Try:
- "Click at 500 300"
- "Type hello world"
- "Press enter"
- "Control c" (hotkey)
- "Open Chrome"
- "Close notepad"
- "Focus on Chrome"
- "Search for my resume"
- "Take a screenshot"
- "Read screen text"
- "Run google search for..." """
