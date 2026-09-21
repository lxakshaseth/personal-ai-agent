"""
Playwright browser controller — higher-level automation wrapper.

Usage pattern:
    async with BrowserController() as browser:
        await browser.navigate("https://youtube.com")
        await browser.search("React tutorials")
"""
from __future__ import annotations

import logging
from typing import Any

from app.utils.exceptions import BrowserError

logger = logging.getLogger(__name__)


class BrowserController:
    """
    Async context manager wrapping a Playwright browser instance.

    Playwright must be installed and browsers downloaded:
        pip install playwright
        playwright install chromium
    """

    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._playwright = None
        self._browser = None
        self._page = None

    async def __aenter__(self) -> "BrowserController":
        await self._start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._stop()

    async def _start(self) -> None:
        try:
            from playwright.async_api import async_playwright  # type: ignore

            self._playwright = await async_playwright().__aenter__()
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
            self._page = await self._browser.new_page()
            logger.info("Browser started (headless=%s).", self._headless)
        except ImportError as exc:
            raise BrowserError(
                "playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from exc
        except Exception as exc:
            raise BrowserError(f"Failed to start browser: {exc}") from exc

    async def _stop(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.__aexit__(None, None, None)
            logger.info("Browser stopped.")
        except Exception:
            logger.exception("Error stopping browser.")

    async def navigate(self, url: str) -> None:
        """Navigate to *url*."""
        if not self._page:
            raise BrowserError("Browser is not started.")
        await self._page.goto(url, wait_until="domcontentloaded")
        logger.debug("Navigated to: %s", url)

    async def get_text(self, selector: str) -> str:
        """Return inner text of the first element matching *selector*."""
        if not self._page:
            raise BrowserError("Browser is not started.")
        element = await self._page.query_selector(selector)
        if element is None:
            return ""
        return await element.inner_text()

    async def click(self, selector: str) -> None:
        """Click the first element matching *selector*."""
        if not self._page:
            raise BrowserError("Browser is not started.")
        await self._page.click(selector)

    async def type_text(self, selector: str, text: str) -> None:
        """Focus *selector* and type *text*."""
        if not self._page:
            raise BrowserError("Browser is not started.")
        await self._page.fill(selector, text)

    async def screenshot(self, path: str) -> None:
        """Save a screenshot to *path*."""
        if not self._page:
            raise BrowserError("Browser is not started.")
        await self._page.screenshot(path=path)

    @property
    def page(self):
        """Direct access to the Playwright page for advanced usage."""
        return self._page
