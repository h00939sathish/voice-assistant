"""
Web Search Skill - DuckDuckGo + Playwright web search via WebAgent
"""

from typing import Any

from skills.base_skill import BaseSkill, skill


@skill(
    name="web",
    keywords=[
        "search the web",
        "look up",
        "browse",
        "web search",
        "search online",
        "google",
    ],
    description="Search the web using DuckDuckGo for real-time information",
    priority=4,
    requires_internet=True,
)
class WebSkill(BaseSkill):
    """Web search via the WebAgent dual-mode engine."""

    def __init__(self):
        super().__init__()
        self._agent = None

    def _get_agent(self):
        if self._agent is None:
            from assistant.web_agent import WebAgent

            self._agent = WebAgent()
        return self._agent

    async def handle(self, text: str, context: Any) -> str | None:
        # Extract query
        query = text.lower()
        for kw in [
            "search the web for",
            "look up",
            "browse",
            "web search",
            "search online",
            "google",
        ]:
            if query.startswith(kw):
                query = query[len(kw) :].strip()
                break
        # Also handle "search for X"
        import re

        m = re.search(r"(?:search|google|look up|browse)\s+(?:for\s+)?(.+)", text, re.I)
        if m:
            query = m.group(1).strip()

        if not query:
            return "What would you like me to search for?"

        try:
            agent = self._get_agent()
            results = await agent.search(query)
            if not results:
                return f"No results for '{query}'."
            lines = [f"Here's what I found for '{query}':"]
            for r in results[:3]:
                lines.append(f"• {r['title']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Web search failed: {e}"
