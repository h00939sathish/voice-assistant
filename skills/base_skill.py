"""
Base Skill class for Buddy Voice Assistant
All skills inherit from this class.

Usage with decorator:
    from skills.base_skill import BaseSkill, skill

    @skill(name="time", keywords=["time", "clock"], description="Tells current time")
    class TimeSkill(BaseSkill):
        async def handle(self, text, context):
            return "The time is now."
"""

from abc import ABC, abstractmethod
from typing import Any, Union

try:
    from assistant.skill_response import SkillResponse
except ImportError:
    SkillResponse = None

try:
    from assistant.skills_registry import SkillsRegistry, skill
except ImportError:

    def skill(*args, **kwargs):
        def decorator(cls):
            return cls

        return decorator

    SkillsRegistry = None


class BaseSkill(ABC):
    name: str = "base"
    description: str = "Base skill"
    keywords: list[str] = []

    def __init__(self):
        self.config: dict[str, Any] = {}
        self._metadata = getattr(self, "_skill_metadata", None)

    def configure(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    async def handle(
        self, text: str, context: dict[str, Any]
    ) -> Union[str, "SkillResponse"]:
        pass

    async def handle_tool_call(
        self, args: dict[str, Any], context: dict[str, Any]
    ) -> Union[str, "SkillResponse"]:
        command = args.get("command", "") if isinstance(args, dict) else str(args)
        return await self.handle(command, context)

    def get_tool_schema(self) -> list[dict[str, Any]]:
        import re

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", self.get_name().lower())
        if not safe_name:
            safe_name = "unknown_skill"

        return [
            {
                "type": "function",
                "function": {
                    "name": safe_name,
                    "description": self.get_description() or "Generic assistant tool.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The command to execute",
                            }
                        },
                        "required": ["command"],
                    },
                },
            }
        ]

    def matches(self, text: str) -> bool:
        text_lower = text.lower()
        keywords = self.keywords

        if self._metadata:
            keywords = self._metadata.keywords

        return any(kw in text_lower for kw in keywords)

    def get_name(self) -> str:
        if self._metadata:
            return self._metadata.name
        return self.name

    def get_description(self) -> str:
        if self._metadata:
            return self._metadata.description
        return self.description


Skill = BaseSkill

__all__ = ["BaseSkill", "Skill", "skill", "SkillsRegistry"]
