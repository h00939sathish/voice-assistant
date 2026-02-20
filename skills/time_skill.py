"""Time Skill - Tells the current time."""
import datetime
from typing import Any, Optional
from skills.base_skill import BaseSkill, skill


@skill(
    name="time",
    keywords=["time", "clock", "what time", "current time"],
    description="Tells the current time",
    priority=10  # High priority - simple, fast response
)
class TimeSkill(BaseSkill):
    """Tells the current time."""

    async def handle(self, text: str, context: Any) -> Optional[str]:
        """Return current time in HH:MM format."""
        now = datetime.datetime.now()
        return f"The time is {now.strftime('%I:%M %p')}"  # 12-hour format with AM/PM