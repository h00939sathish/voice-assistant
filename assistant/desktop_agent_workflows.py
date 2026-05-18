"""
Desktop Agent Example Workflows

Pre-built workflows for common desktop automation tasks.
Can be loaded by WorkflowEngine or used directly.

Usage:
    from assistant.desktop_agent_workflows import WORKFLOWS, load_workflows

    engine = WorkflowEngine()
    for name, wf in WORKFLOWS.items():
        engine.register_workflow(wf)
"""

from assistant.desktop_agent.workflows import Workflow, WorkflowStep

# ==================== BROWSER WORKFLOWS ====================

WORKFLOWS = {
    "open_chrome": Workflow(
        name="open_chrome",
        description="Open Chrome browser",
        tags=["browser", "common"],
        steps=[
            WorkflowStep("open_app", {"path_or_name": "chrome"}, "Open Chrome"),
            WorkflowStep("wait", {"seconds": 2}, "Wait for Chrome to start"),
            WorkflowStep("focus_window", {"title": "Chrome"}, "Focus Chrome window"),
        ],
    ),
    "google_search": Workflow(
        name="google_search",
        description="Open browser and search Google",
        tags=["browser", "search", "google"],
        steps=[
            WorkflowStep("open_app", {"path_or_name": "chrome"}, "Open Chrome"),
            WorkflowStep("wait", {"seconds": 2}, "Wait for Chrome"),
            WorkflowStep("focus_window", {"title": "Chrome"}, "Focus Chrome"),
            WorkflowStep("hotkey", {"keys": ["ctrl", "l"]}, "Focus address bar"),
            WorkflowStep("type_text", {"text": "{{query}}"}, "Type search query"),
            WorkflowStep("press", {"key": "enter"}, "Submit search"),
        ],
    ),
    "close_browser": Workflow(
        name="close_browser",
        description="Close the browser",
        tags=["browser", "close"],
        steps=[
            WorkflowStep("close_app", {"name": "Chrome"}, "Close Chrome"),
        ],
    ),
    # ==================== MEDIA WORKFLOWS ====================
    "open_spotify": Workflow(
        name="open_spotify",
        description="Open Spotify",
        tags=["music", "media", "spotify"],
        steps=[
            WorkflowStep("open_app", {"path_or_name": "spotify"}, "Open Spotify"),
            WorkflowStep("wait", {"seconds": 3}, "Wait for Spotify"),
            WorkflowStep("focus_window", {"title": "Spotify"}, "Focus Spotify"),
        ],
    ),
    "play_music": Workflow(
        name="play_music",
        description="Play/Pause music",
        tags=["music", "media", "play"],
        steps=[
            WorkflowStep("focus_window", {"title": "Spotify"}, "Focus Spotify"),
            WorkflowStep("wait", {"seconds": 1}, "Wait"),
            WorkflowStep("press", {"key": "space"}, "Play/Pause toggle"),
        ],
    ),
    # ==================== FILE WORKFLOWS ====================
    "open_downloads": Workflow(
        name="open_downloads",
        description="Open Downloads folder in Explorer",
        tags=["file", "folder", "common"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["win", "e"]}, "Open Explorer"),
            WorkflowStep("wait", {"seconds": 1}, "Wait for Explorer"),
            WorkflowStep("type_text", {"text": "Downloads"}, "Type folder name"),
            WorkflowStep("press", {"key": "enter"}, "Open folder"),
        ],
    ),
    "open_documents": Workflow(
        name="open_documents",
        description="Open Documents folder",
        tags=["file", "folder"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["win", "e"]}, "Open Explorer"),
            WorkflowStep("wait", {"seconds": 1}, "Wait"),
            WorkflowStep("type_text", {"text": "Documents"}, "Type folder name"),
            WorkflowStep("press", {"key": "enter"}, "Open folder"),
        ],
    ),
    # ==================== SCREEN WORKFLOWS ====================
    "take_screenshot": Workflow(
        name="take_screenshot",
        description="Take a screenshot",
        tags=["screen", "utility", "screenshot"],
        steps=[
            WorkflowStep(
                "take_screenshot", {"path": "screenshots/screen.png"}, "Take screenshot"
            ),
        ],
    ),
    "screenshot_selection": Workflow(
        name="screenshot_selection",
        description="Take screenshot and copy to clipboard",
        tags=["screen", "screenshot", "clipboard"],
        steps=[
            WorkflowStep("take_screenshot", {}, "Take screenshot"),
            WorkflowStep(
                "hotkey", {"keys": ["win", "shift", "s"]}, "Open snippet tool"
            ),
            WorkflowStep("wait", {"seconds": 1}, "Wait for tool"),
        ],
    ),
    # ==================== WINDOW WORKFLOWS ====================
    "minimize_all": Workflow(
        name="minimize_all",
        description="Minimize all windows (show desktop)",
        tags=["window", "minimize", "utility"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["win", "d"]}, "Show desktop"),
        ],
    ),
    "show_desktop": Workflow(
        name="show_desktop",
        description="Show desktop",
        tags=["window", "desktop"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["win", "d"]}, "Show desktop"),
        ],
    ),
    "task_view": Workflow(
        name="task_view",
        description="Open Task View",
        tags=["window", "task"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["win", "tab"]}, "Open Task View"),
        ],
    ),
    # ==================== SYSTEM WORKFLOWS ====================
    "lock_computer": Workflow(
        name="lock_computer",
        description="Lock the computer",
        tags=["system", "security", "lock"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["win", "l"]}, "Lock screen"),
        ],
    ),
    "open_settings": Workflow(
        name="open_settings",
        description="Open Windows Settings",
        tags=["system", "settings"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["win", "i"]}, "Open Settings"),
        ],
    ),
    # ==================== TYPING WORKFLOWS ====================
    "copy_all": Workflow(
        name="copy_all",
        description="Select all and copy (Ctrl+A, Ctrl+C)",
        tags=["clipboard", "copy", "keyboard"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["ctrl", "a"]}, "Select all"),
            WorkflowStep("hotkey", {"keys": ["ctrl", "c"]}, "Copy"),
        ],
    ),
    "paste_special": Workflow(
        name="paste_special",
        description="Paste without formatting",
        tags=["clipboard", "paste"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["ctrl", "shift", "v"]}, "Paste special"),
        ],
    ),
    "new_file": Workflow(
        name="new_file",
        description="Create new file (Ctrl+N)",
        tags=["keyboard", "new"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["ctrl", "n"]}, "New"),
        ],
    ),
    "save_file": Workflow(
        name="save_file",
        description="Save current file (Ctrl+S)",
        tags=["keyboard", "save"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["ctrl", "s"]}, "Save"),
        ],
    ),
    # ==================== MULTI-STEP COMPLEX WORKFLOWS ====================
    "morning_routine": Workflow(
        name="morning_routine",
        description="Open essential apps for morning work",
        tags=["daily", "routine"],
        steps=[
            WorkflowStep("open_app", {"path_or_name": "chrome"}, "Open Chrome"),
            WorkflowStep("wait", {"seconds": 2}, "Wait"),
            WorkflowStep("open_app", {"path_or_name": "spotify"}, "Open Spotify"),
            WorkflowStep("wait", {"seconds": 3}, "Wait for Spotify"),
            WorkflowStep("focus_window", {"title": "Spotify"}, "Focus Spotify"),
            WorkflowStep("press", {"key": "space"}, "Start music"),
        ],
    ),
    "focus_mode": Workflow(
        name="focus_mode",
        description="Enter focus mode - close distractions",
        tags=["focus", "productivity"],
        steps=[
            WorkflowStep("hotkey", {"keys": ["win", "d"]}, "Show desktop"),
            WorkflowStep("close_app", {"name": "Discord"}, "Close Discord if open"),
            WorkflowStep("close_app", {"name": "Slack"}, "Close Slack if open"),
            WorkflowStep("close_app", {"name": "Teams"}, "Close Teams if open"),
        ],
    ),
    "presentation_mode": Workflow(
        name="presentation_mode",
        description="Prepare for presentation",
        tags=["presentation", "meeting"],
        steps=[
            WorkflowStep("open_app", {"path_or_name": "chrome"}, "Open Chrome"),
            WorkflowStep("wait", {"seconds": 2}, "Wait"),
            WorkflowStep(
                "move_window",
                {"title": "Chrome", "x": 0, "y": 0, "w": 960, "h": 1080},
                "Left half",
            ),
        ],
    ),
}


def load_workflows(engine) -> dict:
    """Load all example workflows into an engine."""
    registered = {}
    for name, wf in WORKFLOWS.items():
        engine.register_workflow(wf)
        registered[name] = wf
    return registered


def get_workflow(name: str) -> Workflow:
    """Get a specific workflow by name."""
    return WORKFLOWS.get(name)


def list_workflows_by_tag(tag: str) -> list[Workflow]:
    """List workflows filtered by tag."""
    return [wf for wf in WORKFLOWS.values() if tag in wf.tags]


# ==================== WORKFLOW TEMPLATES ====================

TEMPLATES = {
    "app_and_action": {
        "name": "app_and_action",
        "description": "Open an app and perform an action",
        "variables": ["app_name", "action", "target"],
        "steps_example": [
            {"action": "open_app", "args": {"path_or_name": "{{app_name}}"}},
            {"action": "wait", "args": {"seconds": 2}},
            {"action": "focus_window", "args": {"title": "{{app_name}}"}},
            {"action": "{{action}}", "args": {"{{target}}"}},
        ],
    },
    "browser_search": {
        "name": "browser_search",
        "description": "Search in browser",
        "variables": ["query", "engine"],
        "steps_example": [
            {"action": "open_app", "args": {"path_or_name": "chrome"}},
            {"action": "wait", "args": {"seconds": 2}},
            {"action": "focus_window", "args": {"title": "Chrome"}},
            {"action": "hotkey", "args": {"keys": ["ctrl", "l"]}},
            {
                "action": "type_text",
                "args": {"text": "https://{{engine}}.com/search?q={{query}}"},
            },
            {"action": "press", "args": {"key": "enter"}},
        ],
    },
    "fill_form": {
        "name": "fill_form",
        "description": "Fill a form field by field",
        "variables": ["field1", "value1", "field2", "value2", "submit"],
        "steps_example": [
            {"action": "click", "args": {"x": "<field1_x>", "y": "<field1_y>"}},
            {"action": "type_text", "args": {"text": "<value1>"}},
            {"action": "press", "args": {"key": "tab"}},
            {"action": "type_text", "args": {"text": "<value2>"}},
            {"action": "press", "args": {"key": "<submit>"}},
        ],
    },
}


# Export convenience
__all__ = [
    "WORKFLOWS",
    "TEMPLATES",
    "load_workflows",
    "get_workflow",
    "list_workflows_by_tag",
]
