"""
Registry Skill - Responds to questions about capabilities
"""
import logging
from typing import Dict, Any
from assistant.skills_registry import SkillsRegistry

# Metadata for the registry itself
SKILL_META = {
    "name": "Skills Registry",
    "description": "Lists available skills and their capabilities",
    "keywords": ["skills", "capabilities", "modules", "what can you do", "help"],
    "version": "1.0.0"
}

logger = logging.getLogger(__name__)

class RegistrySkill:
    """
    Provides information about installed skills.
    """
    
    def __init__(self):
        self.keywords = ["skills", "capabilities", "what can you do", "list skills", "help"]
        self.registry = SkillsRegistry() # This scans on init

    async def handle(self, text: str, context: Dict[str, Any]) -> str:
        text = text.lower()
        
        # 1. Detail view: "Tell me about the X skill"
        if "tell me about" in text or "describe" in text:
            for skill in self.registry.list_skills():
                if skill.name.lower() in text:
                    return f"**{skill.name} Skill**\n{skill.description}\nKeywords: {', '.join(skill.keywords)}"
        
        # 2. List view
        skills = self.registry.list_skills()
        if not skills:
            return "I don't seem to have any skills loaded. Check the logs."
            
        response = ["Here are my active skills:"]
        for skill in skills:
            response.append(f"• **{skill.name}**: {skill.description}")
            
        return "\n".join(response)
