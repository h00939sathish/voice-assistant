"""
News Skill - Fetches real headlines via DuckDuckGo RSS
"""

import logging
from typing import Any

import aiohttp

from skills.base_skill import BaseSkill, skill

logger = logging.getLogger(__name__)


@skill(
    name="news",
    keywords=["news", "headlines", "latest news", "what's happening", "current events"],
    description="Fetches latest news headlines",
    priority=4,
    requires_internet=True,
)
class NewsSkill(BaseSkill):
    """Fetches real news headlines via DuckDuckGo News API."""

    async def handle(self, text: str, context: dict[str, Any]) -> str | None:
        # Extract topic
        import re

        topic = "world"
        m = re.search(r"(?:news|headlines)\s+(?:about|on|for)\s+(.+)", text, re.I)
        if m:
            topic = m.group(1).strip()

        try:
            url = f"https://duckduckgo.com/news.js?q={topic}&o=json"
            headers = {"User-Agent": "BuddyAssistant/1.0"}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        results = data.get("results", [])
                        if results:
                            lines = [f"Here are the latest headlines about {topic}:"]
                            for item in results[:5]:
                                title = item.get("title", "")
                                source = item.get("source", "")
                                lines.append(f"• {title} ({source})")
                            return "\n".join(lines)

            # Fallback if API doesn't work
            return f"I couldn't fetch news about {topic} right now. Try again later."

        except Exception as e:
            logger.error(f"News fetch failed: {e}")
            return f"I had trouble fetching the news: {e}"
