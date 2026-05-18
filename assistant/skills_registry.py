"""
Skills Registry - Central registration system for all skills.
Uses decorators for clean skill declaration.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Metadata container for registered skills."""

    name: str
    keywords: list[str]
    description: str
    priority: int = 0
    requires_internet: bool = False
    skill_class: type = None
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)
    # MCP isolation: run this skill as a subprocess to save RAM
    mcp_isolated: bool = False
    # Absolute path to the skill script (auto-set by @skill decorator)
    script_path: str = ""

    def __repr__(self):
        return f"SkillMetadata({self.name}, keywords={self.keywords})"


class SkillsRegistry:
    """
    Central registry for all skills.
    Uses decorators for registration - no file scanning needed.
    Singleton pattern for global access.
    """

    _instance = None
    _skills: dict[str, SkillMetadata] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls,
        name: str,
        keywords: list[str],
        description: str,
        priority: int = 0,
        requires_internet: bool = False,
        parameters: dict[str, Any] = None,
        mcp_isolated: bool = False,
    ):
        """Decorator to register a skill."""

        def decorator(skill_class: type) -> type:
            if not hasattr(skill_class, "handle"):
                raise ValueError(f"Skill {name} must have a handle method")

            import inspect

            script_path = inspect.getfile(skill_class) if mcp_isolated else ""

            metadata = SkillMetadata(
                name=name,
                keywords=[k.lower() for k in keywords],
                description=description,
                priority=priority,
                requires_internet=requires_internet,
                skill_class=skill_class,
                parameters=parameters or {},
                mcp_isolated=mcp_isolated,
                script_path=script_path,
            )
            if name in cls._skills:
                logger.warning(f"Skill '{name}' already registered — overwriting")
            cls._skills[name] = metadata
            skill_class._skill_metadata = metadata
            logger.debug(
                f"Registered skill: {name}{'  [MCP isolated]' if mcp_isolated else ''}"
            )
            return skill_class

        return decorator

    @classmethod
    def get_skill(cls, name: str) -> SkillMetadata | None:
        """Get skill metadata by name."""
        return cls._skills.get(name)

    @classmethod
    def get_all_skills(cls) -> dict[str, SkillMetadata]:
        """Get all registered skills."""
        return cls._skills.copy()

    @classmethod
    def get_skill_names(cls) -> list[str]:
        """Get list of all registered skill names."""
        return list(cls._skills.keys())

    @classmethod
    def match_skill(cls, text: str) -> SkillMetadata | None:
        """
        Find matching skill based on keywords.
        Uses word-boundary matching to prevent false positives (e.g. 'wind' matching 'window').
        Returns the best match using priority first, then keyword specificity.
        """
        import re

        text_lower = text.lower()
        matches = []

        for metadata in cls._skills.values():
            if not metadata.enabled:
                continue
            best_keyword_match = None
            for keyword in metadata.keywords:
                matched = False
                # Use word boundaries for single-word keywords to prevent substring false positives
                if " " in keyword:
                    # Multi-word keywords: exact phrase match
                    if keyword in text_lower:
                        matched = True
                else:
                    # Single-word keywords: word boundary match
                    if re.search(r"\b" + re.escape(keyword) + r"\b", text_lower):
                        matched = True

                if not matched:
                    continue

                # Prefer higher-priority skills, then longer / more specific keywords.
                keyword_words = len(keyword.split())
                keyword_len = len(keyword)
                exact_query_match = 1 if keyword == text_lower.strip() else 0
                match_score = (
                    metadata.priority,
                    exact_query_match,
                    keyword_words,
                    keyword_len,
                )
                if best_keyword_match is None or match_score > best_keyword_match[0]:
                    best_keyword_match = (match_score, metadata)

            if best_keyword_match is not None:
                matches.append(best_keyword_match)

        if matches:
            return max(matches, key=lambda item: item[0])[1]
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
            if (
                query in skill.name.lower()
                or query in skill.description.lower()
                or any(query in k for k in skill.keywords)
            ):
                results.append(skill)
        return results

    @classmethod
    def get_tool_definitions(cls) -> list[dict[str, Any]]:
        """
        Get all skills formatted as OpenAI/Ollama Tools.
        """
        import re

        from skills.base_skill import BaseSkill

        tools = []
        for meta in cls._skills.values():
            if not meta.enabled:
                continue

            # Prefer an explicit custom schema exposed by the skill itself.
            try:
                instance = cls.create_instance(meta.name)
                if (
                    instance
                    and getattr(type(instance), "get_tool_schema", None)
                    is not BaseSkill.get_tool_schema
                ):
                    custom_schema = instance.get_tool_schema()
                    if isinstance(custom_schema, list):
                        tools.extend(
                            [tool for tool in custom_schema if isinstance(tool, dict)]
                        )
                        continue
                    if isinstance(custom_schema, dict):
                        tools.append(custom_schema)
                        continue
            except Exception as e:
                logger.warning(
                    f"Failed to load custom tool schema for {meta.name}: {e}"
                )

            # Use explicit parameters if defined in the decorator
            if meta.parameters:
                parameters = meta.parameters
            else:
                # Default parameter schema for all generic Python skills
                parameters = {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The specific instruction, action, or query for this tool.",
                        }
                    },
                    "required": ["command"],
                }

            safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", meta.name.lower())

            tool = {
                "type": "function",
                "function": {
                    "name": safe_name,
                    "description": meta.description or "Generic assistant tool.",
                    "parameters": parameters,
                },
            }
            tools.append(tool)
        return tools


# Convenience function for skill registration
# Usage: from assistant.skills_registry import skill
#        @skill(name="time", keywords=["time", "clock"], description="...")
#        class TimeSkill(BaseSkill): ...


def skill(
    name: str,
    keywords: list[str],
    description: str,
    priority: int = 0,
    requires_internet: bool = False,
    parameters: dict[str, Any] = None,
    mcp_isolated: bool = False,
):
    """
    Decorator to register a skill with the registry.

    Set mcp_isolated=True to run the skill as a subprocess (saves RAM for heavy deps).

    Example:
        @skill(name="time", keywords=["time", "clock"], description="Tells the time")
        class TimeSkill(BaseSkill):
            async def handle(self, text, context):
                return f"The time is {datetime.now()}"
    """
    return SkillsRegistry.register(
        name,
        keywords,
        description,
        priority,
        requires_internet,
        parameters,
        mcp_isolated,
    )


# Global registry instance for import convenience
registry = SkillsRegistry()
