"""
Router Engine — High-level orchestration for tool discovery, categorisation, and query routing.
Wraps ToolCatalogue with Buddy-aware seeding from MCP_SERVERS config.
"""

import os
import sys
from typing import Any

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from tool_catalogue import CATEGORY_SEEDS, ToolCatalogue

# ── Built-in tool seeds ──────────────────────────────────────────────────
# Pre-populate the catalogue with known Buddy skills + MCP tools at startup.
# Category assignments are static and curated.

BUILTIN_TOOLS: list[dict[str, Any]] = [
    # ── Planner MCP ─────────────────────────────────────────────────────
    {
        "name": "create_goal",
        "server": "mcp__planner",
        "category": "planning",
        "description": "Create a high-level goal or objective to plan and execute",
        "keywords": ["goal", "plan", "create", "objective", "audit", "project"],
    },
    {
        "name": "add_tasks",
        "server": "mcp__planner",
        "category": "planning",
        "description": "Add steps/tasks to an existing goal with dependencies",
        "keywords": ["task", "step", "add", "decompose", "subtask", "dependency"],
    },
    {
        "name": "get_next_task",
        "server": "mcp__planner",
        "category": "planning",
        "description": "Get the next ready-to-execute task for a goal",
        "keywords": ["next", "task", "execute", "proceed", "step"],
    },
    {
        "name": "update_task_status",
        "server": "mcp__planner",
        "category": "planning",
        "description": "Mark a task completed, failed, or skipped",
        "keywords": ["complete", "finish", "fail", "skip", "done", "status", "update"],
    },
    {
        "name": "replan",
        "server": "mcp__planner",
        "category": "planning",
        "description": "Cancel remaining tasks and insert a new plan",
        "keywords": ["replan", "change", "new plan", "cancel", "replace"],
    },
    {
        "name": "get_goal_status",
        "server": "mcp__planner",
        "category": "planning",
        "description": "Full progress report for a goal",
        "keywords": ["progress", "status", "report", "goal", "percent"],
    },
    {
        "name": "list_goals",
        "server": "mcp__planner",
        "category": "planning",
        "description": "List all goals with summary status",
        "keywords": ["list", "goals", "all", "summary", "active", "completed"],
    },
    # ── Native Skills ────────────────────────────────────────────────────
    {
        "name": "time",
        "server": "native",
        "category": "time",
        "description": "Tell the current time or date",
        "keywords": ["time", "clock", "date", "what time", "now"],
    },
    {
        "name": "reminder",
        "server": "native",
        "category": "time",
        "description": "Set and manage reminders and alarms",
        "keywords": ["remind", "reminder", "alarm", "alert", "in", "minutes", "hours"],
    },
    {
        "name": "calendar",
        "server": "native",
        "category": "time",
        "description": "Manage calendar events and appointments",
        "keywords": ["calendar", "event", "appointment", "schedule", "meeting"],
    },
    {
        "name": "weather",
        "server": "native",
        "category": "web",
        "description": "Get current weather and forecast",
        "keywords": ["weather", "temperature", "forecast", "rain", "sunny", "wind"],
    },
    {
        "name": "google_search",
        "server": "native",
        "category": "web",
        "description": "Search the internet using Google",
        "keywords": ["search", "google", "find", "look up", "internet", "web"],
    },
    {
        "name": "browser",
        "server": "native",
        "category": "web",
        "description": "Open URLs and browse websites",
        "keywords": ["browse", "open", "website", "url", "http", "page"],
    },
    {
        "name": "news",
        "server": "native",
        "category": "web",
        "description": "Get latest news headlines",
        "keywords": ["news", "headlines", "article", "latest", "today"],
    },
    {
        "name": "spotify",
        "server": "native",
        "category": "media",
        "description": "Control Spotify music playback",
        "keywords": [
            "spotify",
            "play",
            "pause",
            "music",
            "song",
            "track",
            "next",
            "previous",
        ],
    },
    {
        "name": "youtube_music",
        "server": "native",
        "category": "media",
        "description": "Control YouTube Music playback",
        "keywords": ["youtube", "music", "play", "video", "song"],
    },
    {
        "name": "system_monitor",
        "server": "native",
        "category": "system",
        "description": "Monitor CPU, RAM, battery, and system performance",
        "keywords": [
            "cpu",
            "ram",
            "memory",
            "battery",
            "system",
            "performance",
            "usage",
        ],
    },
    {
        "name": "system",
        "server": "native",
        "category": "system",
        "description": "System controls: shutdown, restart, lock, sleep",
        "keywords": ["shutdown", "restart", "lock", "sleep", "power", "reboot"],
    },
    {
        "name": "app_controller",
        "server": "native",
        "category": "system",
        "description": "Launch, close, and switch between applications",
        "keywords": [
            "open",
            "launch",
            "close",
            "app",
            "application",
            "switch",
            "focus",
        ],
    },
    {
        "name": "window_manager",
        "server": "native",
        "category": "system",
        "description": "Manage application windows: move, resize, minimise",
        "keywords": ["window", "minimise", "maximise", "resize", "move", "snap"],
    },
    {
        "name": "file_manager",
        "server": "native",
        "category": "filesystem",
        "description": "File system operations: list, read, write, move files",
        "keywords": [
            "file",
            "folder",
            "directory",
            "read",
            "write",
            "list",
            "move",
            "copy",
        ],
    },
    {
        "name": "clipboard",
        "server": "native",
        "category": "filesystem",
        "description": "Read and write the system clipboard",
        "keywords": ["clipboard", "copy", "paste", "text"],
    },
    {
        "name": "vision",
        "server": "native",
        "category": "general",
        "description": "Describe what is on the screen using computer vision",
        "keywords": ["see", "look", "screen", "screenshot", "describe", "camera"],
    },
    {
        "name": "quick_actions",
        "server": "native",
        "category": "system",
        "description": "Quick system actions: volume, brightness, wifi",
        "keywords": ["volume", "brightness", "wifi", "bluetooth", "mute", "toggle"],
    },
    # ── DesktopCommander MCP ─────────────────────────────────────────────
    {
        "name": "execute_command",
        "server": "mcp__desktop_commander",
        "category": "shell",
        "description": "Run terminal shell commands on the local machine",
        "keywords": [
            "run",
            "execute",
            "command",
            "bash",
            "terminal",
            "shell",
            "script",
        ],
    },
    {
        "name": "read_file",
        "server": "mcp__desktop_commander",
        "category": "filesystem",
        "description": "Read file contents from the local filesystem",
        "keywords": ["read", "file", "content", "open", "text", "view"],
    },
    {
        "name": "write_file",
        "server": "mcp__desktop_commander",
        "category": "filesystem",
        "description": "Write or create files on the local filesystem",
        "keywords": ["write", "create", "save", "file", "edit"],
    },
    {
        "name": "search_files",
        "server": "mcp__desktop_commander",
        "category": "filesystem",
        "description": "Search for files by name or content",
        "keywords": ["search", "find", "file", "grep", "locate"],
    },
]


class RouterEngine:
    """Query-aware tool router with Buddy-specific category knowledge."""

    def __init__(self, db_path: str | None = None):
        self.catalogue = ToolCatalogue(db_path)
        self._seeded = False

    def seed_defaults(self):
        """Load built-in tools into catalogue (idempotent — safe to call repeatedly)."""
        if self._seeded:
            return
        if self.catalogue.count() < len(BUILTIN_TOOLS):
            self.catalogue.bulk_register(BUILTIN_TOOLS)
        self._seeded = True

    # ── Main API ──────────────────────────────────────────────────────────

    def get_tools_for_query(self, query: str, top_k: int = 12) -> dict[str, Any]:
        """Return top-k tools ranked by relevance to the query."""
        self.seed_defaults()
        tools = self.catalogue.search(query, top_k=top_k)
        return {
            "query": query,
            "top_k": top_k,
            "total_in_catalogue": self.catalogue.count(),
            "returned": len(tools),
            "tools": [
                {
                    "name": t["name"],
                    "server": t["server"],
                    "category": t["category"],
                    "description": t["description"],
                }
                for t in tools
            ],
        }

    def register_tool(
        self,
        name: str,
        description: str,
        server: str = "native",
        category: str = "general",
        keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        self.seed_defaults()
        is_new = self.catalogue.register_tool(
            name, description, server, category, keywords
        )
        return {
            "name": name,
            "registered": True,
            "is_new": is_new,
            "category": category,
        }

    def record_tool_use(self, tool_name: str) -> dict[str, Any]:
        self.seed_defaults()
        self.catalogue.record_use(tool_name)
        return {"tool": tool_name, "recorded": True}

    def list_catalogue(self, category: str | None = None) -> dict[str, Any]:
        self.seed_defaults()
        tools = self.catalogue.list_all(category)
        return {
            "total": len(tools),
            "category_filter": category,
            "tools": [
                {
                    "name": t["name"],
                    "server": t["server"],
                    "category": t["category"],
                    "use_count": t["use_count"],
                }
                for t in tools
            ],
        }

    def list_categories(self) -> list[str]:
        return list(CATEGORY_SEEDS.keys())

    def close(self):
        self.catalogue.close()
