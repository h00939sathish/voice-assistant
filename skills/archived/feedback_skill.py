"""
Feedback Skill - Log user feedback to database

ARCHIVED: Not part of core skill set - functionality not fully implemented.
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
    name="feedback",
    keywords=["feedback", "suggestion", "report a bug", "comment"],
    description="Log feedback and suggestions about the assistant's performance",
    priority=2
)
class FeedbackSkill(BaseSkill):

    async def handle(self, text: str, context: dict[str, Any]) -> str | None:
        match = re.search(r"(?:feedback|suggestion|report|comment)\s+(.+)", text, re.IGNORECASE)

        if not match:
            return "What feedback would you like to provide? Say something like 'feedback this was a good response.'"

        feedback_text = match.group(1).strip()
        if not feedback_text:
            return "It seems you didn't provide any feedback. Please try again."

        try:
            # Log to file for now (can be extended to DB)
            logger.info(f"[USER FEEDBACK] {feedback_text}")
            return "Thank you! Your feedback has been logged."
        except Exception as e:
            logger.error(f"Failed to save feedback: {e}")
            return "Sorry, I was unable to save your feedback at this time."
