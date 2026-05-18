"""
Google Search Skill — searches via Google Custom Search API.
Runs as an MCP-isolated subprocess to keep aiohttp/requests out of the main process heap.
"""

import os

from skills.base_skill import BaseSkill, skill


@skill(
    name="google_search",
    keywords=["search for", "google", "find info on", "look up", "who is", "what is"],
    description="Searches the web using Google Custom Search API",
    mcp_isolated=True,  # ← runs as subprocess: aiohttp stays out of main process
)
class GoogleSearchSkill(BaseSkill):
    """Web search via Google Custom Search API."""

    async def handle(self, query: str, context: dict) -> str:
        # Use standard Google API key (same key works for Custom Search if enabled)
        api_key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
        cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

        if not api_key or not cx:
            return (
                "I need a Google API Key (YOUTUBE_API_KEY or GOOGLE_API_KEY) "
                "and a GOOGLE_SEARCH_ENGINE_ID to search the web."
            )

        # Strip keyword prefix from query
        search_term = query
        for kw in [
            "search for",
            "google",
            "find info on",
            "look up",
            "who is",
            "what is",
        ]:
            if query.lower().startswith(kw):
                search_term = query[len(kw) :].strip()
                break

        try:
            import aiohttp

            url = "https://www.googleapis.com/customsearch/v1"
            params = {"key": api_key, "cx": cx, "q": search_term, "num": 3}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status != 200:
                        return f"Google search returned status {resp.status}."
                    data = await resp.json()

            items = data.get("items", [])
            if not items:
                return f"No results found for '{search_term}'."

            lines = [f"Here's what I found for '{search_term}':\n"]
            for item in items:
                lines.append(
                    f"🔹 {item.get('title')}\n"
                    f"   {item.get('snippet')}\n"
                    f"   {item.get('link')}"
                )
            return "\n\n".join(lines)

        except Exception as e:
            return f"Search failed: {e}"


# ── MCP Subprocess Entry Point ──────────────────────────────────────────────
# When Buddy spawns this file as a subprocess, Python calls this block.
# The JSON-lines server reads requests from stdin and writes results to stdout.
if __name__ == "__main__":
    from assistant.mcp_skill_server import run_skill_server

    run_skill_server(GoogleSearchSkill())
