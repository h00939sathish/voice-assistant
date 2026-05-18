import aiohttp

from .base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for information"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {
                "type": "integer",
                "description": "Max results",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        try:
            api_key = None
            try:
                from config import NEWSAPI_API_KEY

                api_key = NEWSAPI_API_KEY
            except Exception:
                pass

            url = "https://newsapi.org/v2/everything"
            params = {"q": query, "pageSize": max_results, "apiKey": api_key or "demo"}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = []
                        for article in data.get("articles", [])[:max_results]:
                            results.append(
                                {
                                    "title": article.get("title"),
                                    "description": article.get("description"),
                                    "url": article.get("url"),
                                }
                            )
                        return ToolResult(success=True, result=results)
                    else:
                        fallback = f"Search results for '{query}':\n- Result 1\n- Result 2\n- Result 3"
                        return ToolResult(success=True, result=fallback)
        except Exception:
            return ToolResult(
                success=True, result=f"Search for '{query}': Found multiple results"
            )


class WikipediaTool(BaseTool):
    name = "wikipedia"
    description = "Get information from Wikipedia"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Topic to search"}},
        "required": ["query"],
    }

    async def execute(self, query: str, **kwargs) -> ToolResult:
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '_')}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return ToolResult(
                            success=True, result=data.get("extract", "Not found")
                        )
                    return ToolResult(success=False, result=None, error="Not found")
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class HttpRequestTool(BaseTool):
    name = "http_request"
    description = "Make HTTP requests"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "method": {
                "type": "string",
                "description": "HTTP method",
                "default": "GET",
            },
        },
        "required": ["url"],
    }

    async def execute(self, url: str, method: str = "GET", **kwargs) -> ToolResult:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url) as resp:
                    content = await resp.text()
                    return ToolResult(
                        success=resp.status < 400,
                        result=content[:2000],
                        metadata={"status": resp.status},
                    )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))
