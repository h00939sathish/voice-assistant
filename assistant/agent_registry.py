"""
Agent Registry - Defines specialist sub-agent roles and system prompts for Buddy.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentRole:
    """Represents a specialist agent role with specific system prompts and capabilities."""

    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)


class AgentRegistry:
    """Registry managing specialist sub-agent roles for task delegation."""

    def __init__(self) -> None:
        self._roles: dict[str, AgentRole] = {}
        self._register_default_roles()

    def _register_default_roles(self) -> None:
        """Register built-in specialist sub-agent roles."""

        self.register(
            AgentRole(
                name="researcher",
                description="Specialist in web search, information extraction, and topic synthesis.",
                system_prompt=(
                    "You are the Researcher Specialist Agent for Buddy. "
                    "Your objective is to find accurate information, summarize key findings, "
                    "and cite reliable facts using available search tools."
                ),
                allowed_tools=["google_search", "web_reader", "news"],
            )
        )

        self.register(
            AgentRole(
                name="coder",
                description="Specialist in code generation, terminal execution, and technical debugging.",
                system_prompt=(
                    "You are the Software Engineer Agent for Buddy. "
                    "Your objective is to write clean, maintainable code, analyze software errors, "
                    "and execute commands in controlled sandbox environments."
                ),
                allowed_tools=["file_manager", "terminal", "computer_use"],
            )
        )

        self.register(
            AgentRole(
                name="system_admin",
                description="Specialist in local system monitoring, file organization, and environment management.",
                system_prompt=(
                    "You are the System Administrator Agent for Buddy. "
                    "Your objective is to inspect hardware metrics, manage local files, "
                    "and maintain desktop health."
                ),
                allowed_tools=["system_monitor", "file_manager", "clipboard"],
            )
        )

        self.register(
            AgentRole(
                name="executive_assistant",
                description="Specialist in scheduling, reminders, calendar management, and personal organization.",
                system_prompt=(
                    "You are the Executive Assistant Agent for Buddy. "
                    "Your objective is to keep the user organized by scheduling calendar events, "
                    "setting timely reminders, and triaging priority tasks."
                ),
                allowed_tools=["calendar", "reminder", "time", "weather"],
            )
        )

    def register(self, role: AgentRole) -> None:
        """Register a new specialist role."""
        self._roles[role.name.lower()] = role
        logger.info(f"Registered sub-agent role: {role.name}")

    def get_role(self, role_name: str) -> AgentRole | None:
        """Retrieve a role by name."""
        return self._roles.get(role_name.lower())

    def list_roles(self) -> list[dict[str, str]]:
        """List all available specialist roles."""
        return [
            {"name": role.name, "description": role.description}
            for role in self._roles.values()
        ]

    def select_role_for_intent(self, intent: str) -> AgentRole | None:
        """Match user intent to the most suitable specialist role."""
        intent_lower = intent.lower()

        if any(w in intent_lower for w in ["search", "find news", "research", "summarize"]):
            return self.get_role("researcher")
        elif any(w in intent_lower for w in ["code", "script", "terminal", "debug", "run command"]):
            return self.get_role("coder")
        elif any(w in intent_lower for w in ["cpu", "ram", "memory", "files", "folder", "disk"]):
            return self.get_role("system_admin")
        elif any(w in intent_lower for w in ["remind", "calendar", "event", "schedule", "time", "weather"]):
            return self.get_role("executive_assistant")

        return None
