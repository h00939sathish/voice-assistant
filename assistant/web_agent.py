import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from datetime import datetime
import psutil

# Configure logger
logger = logging.getLogger("AI_Assistant.WebAgent")

# Mock valid_user_agent if not available
try:
    from fake_useragent import UserAgent
    ua = UserAgent()
    def get_user_agent():
        return ua.random
except ImportError:
    def get_user_agent():
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Global Playwright state
_playwright = None
_playwright_browser = None
_browser_context = None
_last_activity = None
_initialization_lock = asyncio.Lock()

async def quick_search_http(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Fast, lightweight search using DuckDuckGo HTML (no browser required).
    Great for simple queries.
    """
    import aiohttp
    from bs4 import BeautifulSoup
    
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {"User-Agent": get_user_agent()}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=params, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(f"HTTP search failed: {resp.status}")
                    return []
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        results = []

        for row in soup.select("tr")[:max_results * 2]:  # Get extra, filter later
            link = row.select_one("a.result-link")
            snippet = row.select_one("td.result-snippet")

            if link and link.get("href"):
                title = link.get_text(strip=True)
                url = link["href"]

                # Skip DuckDuckGo internal links
                if "duckduckgo.com" in url:
                    continue

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet.get_text(strip=True) if snippet else ""
                })

                if len(results) >= max_results:
                    break

        logger.info(f"✅ HTTP search found {len(results)} results")
        return results

    except Exception as e:
        logger.warning(f"HTTP search failed: {e}")
        return []

class WebAgent:
    """
    Web automation with dual-mode operation:
    - FAST: HTTP-only (no browser) for simple searches
    - FULL: Playwright browser for complex interactions
    """

    def __init__(self):
        # System detection
        self.total_ram_gb = psutil.virtual_memory().total / (1024**3)
        self.cpu_count = psutil.cpu_count()

        # Auto-configure based on RAM
        if self.total_ram_gb < 12:
            self.mode = "lightweight"
            self.max_memory_mb = 300
            self.prefer_http = True  # Use HTTP mode by default
        else:
            self.mode = "balanced"
            self.max_memory_mb = 600
            self.prefer_http = False  # Can use browser more freely

        logger.info(f"⚡ WebAgent: {self.mode.upper()} mode ({self.total_ram_gb:.1f}GB RAM)")

        # Browser settings
        self.browser_type = "chromium"
        self.headless = True
        self.auto_close_timeout = 300  # 5 minutes idle

        # State
        self.is_initialized = False
        self.active_tasks = 0
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_flag = False

        # Statistics
        self.stats = {
            "tasks_completed": 0,
            "http_searches": 0,
            "browser_searches": 0,
            "memory_peak_mb": 0,
        }

    # ========== BROWSER INITIALIZATION (Lazy) ==========

    async def initialize(self) -> bool:
        """
        Lazy browser initialization with proper locking.
        Only called when HTTP mode insufficient.
        """
        global _playwright, _playwright_browser, _browser_context, _last_activity

        if self.is_initialized:
            _last_activity = time.time()
            return True

        # Prevent double-initialization
        async with _initialization_lock:
            if self.is_initialized:  # Check again inside lock
                return True

            try:
                # Memory check
                available_mb = psutil.virtual_memory().available / (1024**2)
                if available_mb < 500:
                    logger.warning(f"⚠️ Low memory ({available_mb:.0f}MB) - browser disabled")
                    return False

                logger.info("🌐 Initializing Playwright browser...")
                start = time.time()

                # Import Playwright (lazy)
                from playwright.async_api import async_playwright

                _playwright = await async_playwright().start()

                # Optimized launch args
                launch_args = {
                    "headless": self.headless,
                    "args": [
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu" if self.total_ram_gb < 12 else "--enable-gpu-rasterization",
                        "--window-size=1920,1080",
                        "--disable-blink-features=AutomationControlled",
                    ],
                }

                # Remove empty args
                launch_args["args"] = [a for a in launch_args["args"] if a]

                # Launch browser
                _playwright_browser = await _playwright.chromium.launch(**launch_args)

                # Create persistent context
                _browser_context = await _playwright_browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )

                _last_activity = time.time()
                self.is_initialized = True

                # Start auto-cleanup
                if self._cleanup_task is None:
                    self._cleanup_task = asyncio.create_task(self._auto_cleanup_loop())

                elapsed = time.time() - start
                logger.info(f"✅ Browser ready in {elapsed:.1f}s")
                return True

            except Exception as e:
                logger.error(f"❌ Browser initialization failed: {e}")
                return False

    async def close(self) -> None:
        """Graceful shutdown with proper cleanup order."""
        global _playwright, _playwright_browser, _browser_context

        if not self.is_initialized:
            return

        self._shutdown_flag = True

        try:
            logger.info("🛑 Closing WebAgent...")

            # 1. Cancel cleanup task
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass

            # 2. Close browser context
            if _browser_context:
                try:
                    await asyncio.wait_for(_browser_context.close(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Context close timeout")
                _browser_context = None

            # 3. Close browser
            if _playwright_browser:
                try:
                    await asyncio.wait_for(_playwright_browser.close(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Browser close timeout")
                _playwright_browser = None

            # 4. Stop Playwright
            if _playwright:
                try:
                    await asyncio.wait_for(_playwright.stop(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Playwright stop timeout")
                _playwright = None

            self.is_initialized = False
            logger.info("✅ WebAgent closed")

        except Exception as e:
            logger.error(f"Error during close: {e}")

    async def _auto_cleanup_loop(self):
        """Auto-close browser after idle period."""
        global _last_activity

        while not self._shutdown_flag:
            try:
                await asyncio.sleep(30)

                if _last_activity and self.is_initialized:
                    idle = time.time() - _last_activity

                    if idle > self.auto_close_timeout and self.active_tasks == 0:
                        logger.info(f"⏰ Idle timeout ({idle:.0f}s) - closing browser")
                        await self.close()
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    # ========== RESOURCE CHECKING ==========

    def _check_resources(self) -> bool:
        """Check if system has capacity for browser tasks."""
        mem = psutil.virtual_memory()
        if mem.percent > 90:
            logger.warning(f"⚠️ RAM at {mem.percent}% - blocking browser task")
            return False
        return True

    # ========== SEARCH METHODS ==========

    async def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """
        Smart search: HTTP first, browser fallback.
        This is the recommended method to use.
        """
        # Try fast HTTP mode first
        if self.prefer_http or not self.is_initialized:
            results = await quick_search_http(query, num_results)
            if results:
                self.stats["http_searches"] += 1
                self.stats["tasks_completed"] += 1
                return results
            logger.info("🔄 HTTP search returned empty, trying browser...")

        # Fallback to browser
        return await self.search_browser(query, num_results)

    async def search_browser(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """
        Browser-based search (Playwright).
        Uses DuckDuckGo to avoid Google anti-bot.
        """
        if not await self.initialize():
            return []

        page = await self.navigate(f"https://duckduckgo.com/?q={query}")
        if not page:
            return []

        try:
            self.active_tasks += 1

            # Wait for results with proper selector
            await page.wait_for_selector('article[data-testid="result"]', timeout=10000)

            results = []
            articles = await page.query_selector_all('article[data-testid="result"]')

            for article in articles[:num_results]:
                try:
                    # DuckDuckGo structure (updated 2024)
                    link_elem = await article.query_selector('a[data-testid="result-title-a"]')
                    snippet_elem = await article.query_selector('div[data-result="snippet"]')

                    if link_elem:
                        title = await link_elem.inner_text()
                        url = await link_elem.get_attribute("href")
                        snippet = await snippet_elem.inner_text() if snippet_elem else ""

                        results.append({
                            "title": title.strip(),
                            "url": url,
                            "snippet": snippet.strip()[:200]
                        })
                except Exception as e:
                    logger.debug(f"Failed to parse result: {e}")
                    continue

            await page.close()
            self.stats["browser_searches"] += 1
            self.stats["tasks_completed"] += 1

            logger.info(f"✅ Browser search found {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Browser search failed: {e}")
            try:
                await page.close()
            except Exception:
                pass
            return []
        finally:
            self.active_tasks -= 1

    # ========== NAVIGATION & OTHER METHODS ==========

    @asynccontextmanager
    async def navigate(self, url: str):
        """
        Context manager for safe page navigation.
        Ensures page is always closed.
        """
        global _browser_context, _last_activity

        if not await self.initialize():
            yield None
            return

        if not self._check_resources():
            logger.warning("Resource check failed - skipping navigation")
            yield None
            return

        page = None
        try:
            self.active_tasks += 1
            _last_activity = time.time()

            page = await _browser_context.new_page()
            logger.info(f"🌐 Navigating to: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            yield page

        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            yield None
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            self.active_tasks -= 1

    async def take_screenshot(self, url: str, path: Optional[str] = None) -> Optional[str]:
        """Take screenshot of URL."""
        async with self.navigate(url) as page:
            if not page:
                return None

            try:
                if not path:
                    path = f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"

                await page.screenshot(path=path, full_page=False, type="png")
                self.stats["tasks_completed"] += 1
                return path

            except Exception as e:
                logger.error(f"Screenshot failed: {e}")
                return None

    async def search_amazon(self, query: str) -> Dict[str, Any]:
        """Search Amazon products."""
        async with self.navigate(f"https://www.amazon.com/s?k={query}") as page:
            if not page:
                return {"error": "Failed to load Amazon"}

            try:
                await page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10000)

                products = []
                items = await page.query_selector_all('[data-component-type="s-search-result"]')

                for item in items[:5]:
                    try:
                        title_elem = await item.query_selector("h2 a span")
                        price_elem = await item.query_selector(".a-price-whole")

                        if title_elem and price_elem:
                            title = await title_elem.inner_text()
                            price = await price_elem.inner_text()
                            products.append({
                                "title": title.strip(),
                                "price": f"${price.strip()}"
                            })
                    except (AttributeError, TypeError):
                        continue

                self.stats["tasks_completed"] += 1
                return {"products": products, "count": len(products)}

            except Exception as e:
                logger.error(f"Amazon search failed: {e}")
                return {"error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return {
            **self.stats,
            "mode": self.mode,
            "initialized": self.is_initialized,
            "active_tasks": self.active_tasks,
            "memory_mb": self._get_memory_usage() if self.is_initialized else 0,
            "ram_total_gb": round(self.total_ram_gb, 1),
        }

    def _get_memory_usage(self) -> int:
        """Current memory usage in MB."""
        import psutil
        return int(psutil.Process().memory_info().rss / (1024**2))

    async def upgrade_mode(self, new_mode: str) -> bool:
        """Switch performance mode."""
        if new_mode not in ["lightweight", "balanced", "full"]:
            return False

        if new_mode == "full" and self.total_ram_gb < 12:
            logger.warning("Cannot enable full mode with < 12GB RAM")
            return False

        self.mode = new_mode
        logger.info(f"🔄 Switched to {new_mode.upper()} mode")
        return True

# ========== SAFE CLEANUP HELPER ==========
async def safe_close_web_agent(agent: WebAgent):
    """
    Safe shutdown that prevents event loop errors.
    Use this in your main shutdown sequence.
    """
    try:
        await asyncio.wait_for(agent.close(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("WebAgent close timeout - forcing shutdown")
    except Exception as e:
        logger.error(f"Error during WebAgent close: {e}")
