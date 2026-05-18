"""
Browser Skill - Native Windows Playwright Browser Automation
"""

import asyncio
import os
import sys
from typing import Any
from urllib.parse import quote_plus

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.logger import get_logger
from skills.base_skill import BaseSkill, skill

logger = get_logger("browser_skill")


@skill(
    name="browser",
    description="Native web browser automation to navigate pages, extract text, click elements, and take screenshots.",
    keywords=[
        "browse",
        "search the web",
        "open website",
        "read page",
        "click link",
        "extract content",
    ],
)
class BrowserSkill(BaseSkill):
    _playwright = None
    _browser = None
    _context = None
    _page = None
    _lock = asyncio.Lock()

    def __init__(self):
        super().__init__()

    @staticmethod
    def _normalize_command(command: str) -> dict[str, Any]:
        """Convert generic browser commands into structured browser tools."""
        text = (command or "").strip()
        lower = text.lower()

        if not text:
            return {"tool_name": ""}

        if "search for " in lower:
            query = text[lower.index("search for ") + len("search for ") :].strip(" .")
            return {"tool_name": "browser_search", "query": query}

        if lower.startswith("search "):
            query = text[len("search ") :].strip(" .")
            return {"tool_name": "browser_search", "query": query}

        if lower.startswith("open "):
            target = text[len("open ") :].strip()
            for prefix in ("website ", "site ", "url "):
                if target.lower().startswith(prefix):
                    target = target[len(prefix) :].strip()
            if " and search for " in lower:
                target = text[
                    lower.index(" and search for ") + len(" and search for ") :
                ].strip(" .")
                return {"tool_name": "browser_search", "query": target}
            if "." in target or "http" in target or "www" in target:
                return {"tool_name": "browser_navigate", "url": target}
            return {"tool_name": "browser_search", "query": target}

        return {"tool_name": ""}

    @classmethod
    async def _ensure_browser(cls):
        """Lazy load the playwright browser instance."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as err:
            raise RuntimeError(
                "Playwright is not installed. Please run 'pip install playwright' and 'playwright install'"
            ) from err

        async with cls._lock:
            if cls._browser is None:
                try:
                    logger.info("Starting Playwright browser...")
                    cls._playwright = await async_playwright().start()
                    # Launch non-headless by default so user can see what Buddy is doing
                    cls._browser = await cls._playwright.chromium.launch(headless=False)
                    cls._context = await cls._browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    )
                    cls._page = await cls._context.new_page()
                except Exception as e:
                    logger.error(f"Failed to start Playwright: {e}")
                    raise RuntimeError(
                        f"Playwright failed to start. Ensure you ran 'playwright install'. Error: {e}"
                    ) from e

    async def handle_tool_call(
        self, args: dict[str, Any], context: dict[str, Any] = None
    ) -> str:
        """Handle native tool execution from LLM. args must include 'tool_name'."""
        tool_name = args.get("tool_name", "") or args.get("command", "")
        if tool_name == "browser" or (tool_name and " " in str(tool_name)):
            normalized = self._normalize_command(str(tool_name))
            if normalized.get("tool_name"):
                args = {**args, **normalized}
                tool_name = normalized["tool_name"]
        await self._ensure_browser()

        try:
            if tool_name == "browser_navigate":
                url = args.get("url", "")
                if not url.startswith("http"):
                    url = "https://" + url
                await self._page.goto(url, wait_until="networkidle", timeout=15000)
                return f"Successfully navigated to {url}"

            elif tool_name == "browser_search":
                query = args.get("query", "").strip()
                engine = (args.get("engine") or "google").strip().lower()
                if not query:
                    return "Browser Error: Missing search query."
                if engine == "duckduckgo":
                    url = f"https://duckduckgo.com/?q={quote_plus(query)}"
                elif engine == "bing":
                    url = f"https://www.bing.com/search?q={quote_plus(query)}"
                else:
                    url = f"https://www.google.com/search?q={quote_plus(query)}"
                await self._page.goto(url, wait_until="networkidle", timeout=15000)
                return f"Searched {engine} for {query}"

            elif tool_name == "browser_extract_text":
                # Extracts the visible text body
                text = await self._page.evaluate("document.body.innerText")
                # Truncate to save tokens if massive
                return text[:8000] if len(text) > 8000 else text

            elif tool_name == "browser_click":
                selector = args.get("selector", "")
                await self._page.click(selector, timeout=5000)
                try:
                    await self._page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass  # Ignore if no navigation occurs
                return f"Clicked element '{selector}'"

            elif tool_name == "browser_type":
                selector = args.get("selector", "")
                text = args.get("text", "")
                await self._page.fill(selector, text, timeout=5000)
                return f"Typed text into '{selector}'"

            else:
                return f"Error: Unknown tool '{tool_name}' for browser skill."

        except Exception as e:
            logger.error(f"Browser Tool Error: {e}")
            return f"Browser Error: {str(e)}"

    async def handle(self, text: str, context: dict[str, Any] | None = None) -> str:
        """Fallback handler if reached by simple keyword."""
        return (
            "I am a robust browser automation tool. Please use me via LLM tool calls."
        )

    def get_tool_schema(self) -> list[dict[str, Any]]:
        """Export Playwright capabilities as OpenAI native tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "browser_search",
                    "description": "Open a search engine in the browser and search for a query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to look up.",
                            },
                            "engine": {
                                "type": "string",
                                "description": "Optional search engine name: google, duckduckgo, or bing.",
                                "enum": ["google", "duckduckgo", "bing"],
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_navigate",
                    "description": "Navigate the browser to a specific URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL to navigate to (e.g., 'https://en.wikipedia.org').",
                            }
                        },
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_extract_text",
                    "description": "Extract all visible plain text from the currently open webpage. Always call navigate first.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_click",
                    "description": "Click an element on the currently open page using a CSS selector or text attribute (e.g., 'text=Log In').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "description": "CSS selector or text-based locator (e.g., 'button#submit', 'text=Log In').",
                            }
                        },
                        "required": ["selector"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_type",
                    "description": "Type text into an input field on the currently open page.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "description": "CSS selector for the input field.",
                            },
                            "text": {
                                "type": "string",
                                "description": "The text to type.",
                            },
                        },
                        "required": ["selector", "text"],
                    },
                },
            },
        ]

    @classmethod
    async def cleanup_all(cls):
        """Close playwright context before exit."""
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None
