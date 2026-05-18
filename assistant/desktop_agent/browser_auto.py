"""
Browser Automation Module

Provides browser automation capabilities using Playwright or native control.
Integrates with existing browser_skill but adds desktop-level control.
"""

import logging

logger = logging.getLogger(__name__)

# Try to import playwright
try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not available - browser automation limited")


class BrowserAutomation:
    """
    Browser automation wrapper.

    Provides browser control at desktop level (separate from browser_skill).
    Uses Playwright when available for more control.
    """

    def __init__(
        self,
        headless: bool = False,
        user_agent: str | None = None,
    ):
        """
        Initialize BrowserAutomation.

        Args:
            headless: Run browser in headless mode
            user_agent: Custom user agent string
        """
        self._headless = headless
        self._user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._default_timeout = 15000

        logger.info(
            f"BrowserAutomation initialized (playwright={PLAYWRIGHT_AVAILABLE})"
        )

    async def _ensure_browser(self):
        """Ensure browser is launched."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not available")

        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=self._user_agent,
            )
            self._page = await self._context.new_page()
            logger.info("Browser launched")

    async def open_url(self, url: str, wait_until: str = "networkidle") -> bool:
        """
        Open a URL in browser.

        Args:
            url: URL to open
            wait_until: Wait condition

        Returns:
            bool: True if successful
        """
        try:
            await self._ensure_browser()

            if not url.startswith("http"):
                url = "https://" + url

            await self._page.goto(
                url, wait_until=wait_until, timeout=self._default_timeout
            )
            logger.info(f"Opened {url}")
            return True

        except Exception as e:
            logger.error(f"open_url failed: {e}")
            return False

    async def search_google(self, query: str) -> bool:
        """
        Search Google for query.

        Args:
            query: Search query

        Returns:
            bool: True if successful
        """
        from urllib.parse import quote_plus

        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return await self.open_url(url)

    async def search_duckduckgo(self, query: str) -> bool:
        """Search DuckDuckGo for query."""
        from urllib.parse import quote_plus

        url = f"https://duckduckgo.com/?q={quote_plus(query)}"
        return await self.open_url(url)

    async def fill_form(
        self,
        selector: str,
        text: str,
        submit: bool = False,
    ) -> bool:
        """
        Fill a form field.

        Args:
            selector: CSS selector
            text: Text to fill
            submit: Submit the form after filling

        Returns:
            bool: True if successful
        """
        try:
            await self._ensure_browser()

            await self._page.fill(selector, text)

            if submit:
                await self._page.click(selector)
                await self._page.wait_for_load_state("networkidle")

            return True

        except Exception as e:
            logger.error(f"fill_form failed: {e}")
            return False

    async def click_element(
        self,
        selector: str,
        wait_nav: bool = True,
    ) -> bool:
        """
        Click an element.

        Args:
            selector: CSS selector
            wait_nav: Wait for navigation after click

        Returns:
            bool: True if successful
        """
        try:
            await self._ensure_browser()

            if wait_nav:
                async with self._page.expect_navigation(timeout=self._default_timeout):
                    await self._page.click(selector)
            else:
                await self._page.click(selector)

            return True

        except Exception as e:
            logger.error(f"click_element failed: {e}")
            return False

    async def type_text(
        self,
        selector: str,
        text: str,
        delay: int = 50,
    ) -> bool:
        """
        Type text into element.

        Args:
            selector: CSS selector
            text: Text to type
            delay: Delay between keystrokes

        Returns:
            bool: True if successful
        """
        try:
            await self._ensure_browser()

            await self._page.type(selector, text, delay=delay)
            return True

        except Exception as e:
            logger.error(f"type_text failed: {e}")
            return False

    async def get_text(self, selector: str) -> str | None:
        """Get text from element."""
        try:
            await self._ensure_browser()

            return await self._page.text_content(selector)

        except Exception as e:
            logger.error(f"get_text failed: {e}")
            return None

    async def get_attribute(
        self,
        selector: str,
        attr: str,
    ) -> str | None:
        """Get attribute from element."""
        try:
            await self._ensure_browser()

            return await self._page.get_attribute(selector, attr)

        except Exception as e:
            logger.error(f"get_attribute failed: {e}")
            return None

    async def wait_for_selector(
        self,
        selector: str,
        timeout: int = 10000,
    ) -> bool:
        """Wait for selector to appear."""
        try:
            await self._ensure_browser()

            await self._page.wait_for_selector(selector, timeout=timeout)
            return True

        except Exception as e:
            logger.error(f"wait_for_selector failed: {e}")
            return False

    async def screenshot(
        self,
        path: str = "screenshots/browser.png",
        full_page: bool = False,
    ) -> bool:
        """Take screenshot of current page."""
        try:
            await self._ensure_browser()

            await self._page.screenshot(path=path, full_page=full_page)
            return True

        except Exception as e:
            logger.error(f"screenshot failed: {e}")
            return False

    async def get_page_title(self) -> str | None:
        """Get current page title."""
        try:
            if self._page:
                return await self._page.title()
        except Exception as e:
            logger.error(f"get_page_title failed: {e}")
        return None

    async def get_url(self) -> str | None:
        """Get current URL."""
        try:
            if self._page:
                return self._page.url
        except Exception as e:
            logger.error(f"get_url failed: {e}")
        return None

    async def go_back(self) -> bool:
        """Go back in history."""
        try:
            await self._ensure_browser()
            await self._page.go_back()
            return True
        except Exception as e:
            logger.error(f"go_back failed: {e}")
            return False

    async def go_forward(self) -> bool:
        """Go forward in history."""
        try:
            await self._ensure_browser()
            await self._page.go_forward()
            return True
        except Exception as e:
            logger.error(f"go_forward failed: {e}")
            return False

    async def reload(self) -> bool:
        """Reload current page."""
        try:
            await self._ensure_browser()
            await self._page.reload()
            return True
        except Exception as e:
            logger.error(f"reload failed: {e}")
            return False

    async def close(self):
        """Close browser."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.error(f"close failed: {e}")

        self._browser = None
        self._playwright = None
        self._page = None

    async def __aenter__(self):
        await self._ensure_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# ==================== DESKTOP BROWSER CONTROL ====================
# These methods work without launching a browser - control existing browser
# ============================================================================


class DesktopBrowserControl:
    """
    Control existing browser on desktop using keystrokes.

    Works with already-open browser windows.
    """

    def __init__(self):
        """Initialize desktop browser control."""
        self._imports_ok = True

        # Import common automation tools
        try:
            import pyautogui

            self._pyautogui = pyautogui
        except ImportError:
            self._imports_ok = False
            logger.warning("pyautogui not available for desktop browser control")

    def is_available(self) -> bool:
        """Check if desktop browser control is available."""
        return self._imports_ok

    def focus_browser(self, name: str = "chrome") -> bool:
        """
        Focus browser window.

        Args:
            name: Browser name (chrome, firefox, edge, etc.)

        Returns:
            bool: True if successful
        """
        import pygetwindow as gw

        try:
            windows = gw.getWindowsWithTitle(name)
            if windows:
                win = windows[0]
                if win.isMinimized:
                    win.restore()
                win.activate()
                return True
            return False

        except Exception as e:
            logger.error(f"focus_browser failed: {e}")
            return False

    def address_bar(self) -> bool:
        """Focus address bar (Ctrl+L)."""
        if not self._imports_ok:
            return False

        try:
            self._pyautogui.hotkey("ctrl", "l")
            return True
        except Exception as e:
            logger.error(f"address_bar failed: {e}")
            return False

    def new_tab(self) -> bool:
        """Open new tab (Ctrl+T)."""
        if not self._imports_ok:
            return False

        try:
            self._pyautogui.hotkey("ctrl", "t")
            return True
        except Exception as e:
            logger.error(f"new_tab failed: {e}")
            return False

    def close_tab(self) -> bool:
        """Close tab (Ctrl+W)."""
        if not self._imports_ok:
            return False

        try:
            self._pyautogui.hotkey("ctrl", "w")
            return True
        except Exception as e:
            logger.error(f"close_tab failed: {e}")
            return False

    def reopen_tab(self) -> bool:
        """Reopen closed tab (Ctrl+Shift+T)."""
        if not self._imports_ok:
            return False

        try:
            self._pyautogui.hotkey("ctrl", "shift", "t")
            return True
        except Exception as e:
            logger.error(f"reopen_tab failed: {e}")
            return False

    def switch_tab(self, num: int) -> bool:
        """Switch to tab number (Ctrl+1-9)."""
        if not self._imports_ok:
            return False

        if num < 1 or num > 9:
            return False

        try:
            self._pyautogui.hotkey("ctrl", str(num))
            return True
        except Exception as e:
            logger.error(f"switch_tab failed: {e}")
            return False

    def refresh(self) -> bool:
        """Refresh page (Ctrl+R or F5)."""
        if not self._imports_ok:
            return False

        try:
            self._pyautogui.hotkey("ctrl", "r")
            return True
        except Exception as e:
            logger.error(f"refresh failed: {e}")
            return False

    def scroll_down(self, amount: int = 3) -> bool:
        """Scroll down."""
        if not self._imports_ok:
            return False

        try:
            for _ in range(amount):
                self._pyautogui.press("pagedown")
            return True
        except Exception as e:
            logger.error(f"scroll_down failed: {e}")
            return False

    def scroll_up(self, amount: int = 3) -> bool:
        """Scroll up."""
        if not self._imports_ok:
            return False

        try:
            for _ in range(amount):
                self._pyautogui.press("pageup")
            return True
        except Exception as e:
            logger.error(f"scroll_up failed: {e}")
            return False

    def go_home(self) -> bool:
        """Go to home page (Alt+Home)."""
        if not self._imports_ok:
            return False

        try:
            self._pyautogui.hotkey("alt", "home")
            return True
        except Exception as e:
            logger.error(f"go_home failed: {e}")
            return False


def create_browser_automation(headless: bool = False) -> BrowserAutomation:
    """Factory to create BrowserAutomation."""
    return BrowserAutomation(headless=headless)


def get_desktop_browser_control() -> DesktopBrowserControl:
    """Get desktop browser control instance."""
    return DesktopBrowserControl()
