"""
Skills Registry - Central registration system for all skills.
Uses decorators for clean skill declaration.
"""
import logging
from typing import Dict, List, Type, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Metadata container for registered skills."""
    name: str
    keywords: List[str]
    description: str
    priority: int = 0
    requires_internet: bool = False
    skill_class: Type = None
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        return f"SkillMetadata({self.name}, keywords={self.keywords})"


class SkillsRegistry:
    """
    Central registry for all skills.
    Uses decorators for registration - no file scanning needed.
    Singleton pattern for global access.
    """

    _instance = None
    _skills: Dict[str, SkillMetadata] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, name: str, keywords: List[str], description: str,
                 priority: int = 0, requires_internet: bool = False,
                 parameters: Dict[str, Any] = None):
        """
        Decorator to register a skill.

        Args:
            name: Unique skill identifier
            keywords: Words that trigger this skill
            description: Human-readable description
            priority: Higher priority skills checked first (default 0)
            requires_internet: If True, skill disabled in offline mode
            parameters: JSON Schema for function calling (optional)
        """
        def decorator(skill_class: Type) -> Type:
            # Ensure skill has handle method
            if not hasattr(skill_class, 'handle'):
                raise ValueError(f"Skill {name} must have a handle method")

            metadata = SkillMetadata(
                name=name,
                keywords=[k.lower() for k in keywords],
                description=description,
                priority=priority,
                requires_internet=requires_internet,
                skill_class=skill_class,
                parameters=parameters or {}
            )
            cls._skills[name] = metadata
            skill_class._skill_metadata = metadata
            logger.debug(f"Registered skill: {name}")
            return skill_class
        return decorator

    @classmethod
    def get_skill(cls, name: str) -> Optional[SkillMetadata]:
        """Get skill metadata by name."""
        return cls._skills.get(name)

    @classmethod
    def get_all_skills(cls) -> Dict[str, SkillMetadata]:
        """Get all registered skills."""
        return cls._skills.copy()

    @classmethod
    def get_skill_names(cls) -> List[str]:
        """Get list of all registered skill names."""
        return list(cls._skills.keys())

    @classmethod
    def match_skill(cls, text: str) -> Optional[SkillMetadata]:
        """
        Find matching skill based on keywords.
        Returns highest priority match.
        """
        text_lower = text.lower()
        matches = []

        for metadata in cls._skills.values():
            if not metadata.enabled:
                continue
            for keyword in metadata.keywords:
                if keyword in text_lower:
                    matches.append(metadata)
                    break

        if matches:
            # Return highest priority match
            return max(matches, key=lambda m: m.priority)
        return None

    @classmethod
    def create_instance(cls, name: str, **kwargs):
        """Create an instance of a registered skill."""
        metadata = cls._skills.get(name)
        if metadata:
            try:
                instance = metadata.skill_class(**kwargs)
                # Inject metadata for reference
                instance._metadata = metadata
                return instance
            except Exception as e:
                logger.error(f"Failed to instantiate skill {name}: {e}")
                return None
        return None

    @classmethod
    def unregister(cls, name: str):
        """Remove a skill from registry."""
        if name in cls._skills:
            del cls._skills[name]
            logger.debug(f"Unregistered skill: {name}")

    @classmethod
    def clear(cls):
        """Clear all registered skills."""
        cls._skills.clear()

    @classmethod
    def set_enabled(cls, name: str, enabled: bool):
        """Enable or disable a skill."""
        if name in cls._skills:
            cls._skills[name].enabled = enabled
            logger.debug(f"Skill {name} {'enabled' if enabled else 'disabled'}")

    def list_skills(self):
        """For backward compatibility."""
        return list(self._skills.values())

    def search(self, query: str):
        """Simple keyword search."""
        query = query.lower()
        results = []
        for skill in self._skills.values():
            if (query in skill.name.lower() or
                query in skill.description.lower() or
                any(query in k for k in skill.keywords)):
                results.append(skill)
        return results

    @classmethod
    def get_tool_definitions(cls) -> List[Dict[str, Any]]:
        """
        Get all skills formatted as OpenAI/Ollama Tools.
        Only returns skills that have defined 'parameters'.
        """
        tools = []
        for meta in cls._skills.values():
            if not meta.enabled or not meta.parameters: 
                continue
            
            tool = {
                "type": "function",
                "function": {
                    "name": meta.name,
                    "description": meta.description,
                    "parameters": meta.parameters
                }
            }
            tools.append(tool)
        return tools


# Convenience function for skill registration
# Usage: from assistant.skills_registry import skill
#        @skill(name="time", keywords=["time", "clock"], description="...")
#        class TimeSkill(BaseSkill): ...

def skill(name: str, keywords: List[str], description: str,
          priority: int = 0, requires_internet: bool = False,
          parameters: Dict[str, Any] = None):
    """
    Decorator to register a skill with the registry.

    Example:
        @skill(name="time", keywords=["time", "clock"], description="Tells the time")
        class TimeSkill(BaseSkill):
            async def handle(self, text, context):
                return f"The time is {datetime.now()}"
    """
    return SkillsRegistry.register(name, keywords, description, priority, requires_internet, parameters)


# Global registry instance for import convenience
registry = SkillsRegistry()
