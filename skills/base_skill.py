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
from typing import Dict, Any, List, Union
from abc import ABC, abstractmethod

# Import SkillResponse for type hints
try:
    from assistant.skill_response import SkillResponse
except ImportError:
    # Fallback for when imported directly
    SkillResponse = None

# Import the skill decorator from registry
try:
    from assistant.skills_registry import skill, SkillsRegistry
except ImportError:
    # Fallback if not yet available
    def skill(*args, **kwargs):
        def decorator(cls):
            return cls
        return decorator
    SkillsRegistry = None


class BaseSkill(ABC):
    """Base class for all skills.

    Use the @skill decorator to register your skill:
        @skill(name="my_skill", keywords=["keyword"], description="...")
        class MySkill(BaseSkill):
            async def handle(self, text, context):
                return "Response"
    """

    # Legacy skill metadata - prefer decorator instead
    name: str = "base"
    description: str = "Base skill"
    keywords: List[str] = []

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self._metadata = getattr(self, '_skill_metadata', None)

    def configure(self, config: Dict[str, Any]):
        """Set skill configuration"""
        self.config = config

    @abstractmethod
    async def handle(self, text: str, context: Dict[str, Any]) -> Union[str, 'SkillResponse']:
        """
        Handle user input and return response.

        Args:
            text: User's spoken text
            context: Dict containing 'llm' (LLMRouter) and other helpers

        Returns:
            Response string or SkillResponse object with conversation control
        """
        pass

    async def handle_tool_call(self, args: Dict[str, Any], context: Dict[str, Any]) -> Union[str, 'SkillResponse']:
        """
        Handle structured tool call from LLM.
        Default implementation converts args to string and calls handle(), 
        but subclasses should override for better precision.
        """
        return await self.handle(str(args), context)

    def matches(self, text: str) -> bool:
        """
        Quick keyword check for routing.
        Uses registry keywords if available, otherwise class keywords.
        """
        text_lower = text.lower()
        keywords = self.keywords

        # Prefer registry metadata if available
        if self._metadata:
            keywords = self._metadata.keywords

        return any(kw in text_lower for kw in keywords)

    def get_name(self) -> str:
        """Get skill name from metadata or class attribute."""
        if self._metadata:
            return self._metadata.name
        return self.name

    def get_description(self) -> str:
        """Get skill description from metadata or class attribute."""
        if self._metadata:
            return self._metadata.description
        return self.description


# Alias for backward compatibility
Skill = BaseSkill

# Re-export decorator for convenience
__all__ = ['BaseSkill', 'Skill', 'skill', 'SkillsRegistry']
