"""
Registry Skill - Windows registry operations

ARCHIVED: Not part of core skill set - Windows registry operations are fragile and rare.
"""
import logging
import re
from typing import Any

# Temporarily disable - skill not part of core
_enabled = False

from skills.base_skill import BaseSkill, skill

logger = logging.getLogger(__name__)

if _enabled:

@skill(
    name="registry",
    keywords=["what can you do", "list skills", "capabilities", "help me", "your skills", "what skills"],
    description="Lists all available skills and their capabilities",
    priority=2
)
class RegistrySkill(BaseSkill):
    """Provides information about installed skills."""

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        text = text.lower()
        skills = sorted(
            SkillsRegistry.get_all_skills().values(),
            key=lambda metadata: metadata.name,
        )

        # Detail view
        if "tell me about" in text or "describe" in text:
            for metadata in skills:
                if metadata.name in text:
                    return f"**{metadata.name}**: {metadata.description}\nKeywords: {', '.join(metadata.keywords)}"

        # List view
        if not skills:
            return "I don't seem to have any skills loaded."

        response = ["Here are my active skills:"]
        for s in skills:
            response.append(f"• **{s.name}**: {s.description}")

        return "\n".join(response)
