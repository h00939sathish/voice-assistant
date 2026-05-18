"""
System Skill - Gaming mode and system-level toggles
"""

import logging
from typing import Any

from skills.base_skill import BaseSkill, skill

logger = logging.getLogger("Jarvis.SystemSkill")


@skill(
    name="system",
    keywords=[
        "gaming mode",
        "enable gaming mode",
        "disable gaming mode",
        "turn on gaming mode",
        "turn off gaming mode",
    ],
    description="Toggle system modes like Gaming Mode (unloads local models to free RAM)",
    priority=5,
)
class SystemSkill(BaseSkill):
    async def handle(self, text: str, context: Any) -> str | None:
        text_lower = text.lower()

        try:
            from assistant.config_manager import Config
        except ImportError:
            return "Config manager not available."

        if "enable" in text_lower or "on" in text_lower:
            if Config.GAMING_MODE:
                return "Gaming mode is already enabled."
            logger.info("Enabling Gaming Mode.")
            Config.GAMING_MODE = True
            return "Gaming mode enabled. Local models unloaded. Using cloud API. Enjoy your game!"

        elif "disable" in text_lower or "off" in text_lower:
            if not Config.GAMING_MODE:
                return "Gaming mode is already disabled."
            logger.info("Disabling Gaming Mode.")
            Config.GAMING_MODE = False
            return "Gaming mode disabled. Local models will load on next query."

        return None
