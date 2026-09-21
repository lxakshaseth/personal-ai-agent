"""
Browser tools — Playwright-based web automation.

Registered tools:
  - browser_search      : Search a site (YouTube, Google, etc.) for a query
  - browser_open_url    : Navigate to an explicit URL
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from app.tools.base import AbstractTool, PermissionLevel, ToolResult
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)

# Site-specific search URL templates
_SEARCH_URLS: dict[str, str] = {
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "google": "https://www.google.com/search?q={query}",
    "github": "https://github.com/search?q={query}",
    "stackoverflow": "https://stackoverflow.com/search?q={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",
    "twitter": "https://twitter.com/search?q={query}",
    "amazon": "https://www.amazon.in/s?k={query}",
    "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search={query}",
}


@register_tool
class BrowserSearchTool(AbstractTool):
    """Search a website for a query and open the results in the default browser."""

    @property
    def name(self) -> str:
        return "browser_search"

    @property
    def description(self) -> str:
        return (
            "Search a website (YouTube, Google, GitHub, etc.) for a query and open the results page. "
            "Use this for commands like 'search YouTube for React tutorials' or "
            "'Google how to use FastAPI'."
        )

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.LOW

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "site": {
                    "type": "string",
                    "description": "Website to search (youtube, google, github, stackoverflow, etc.)",
                    "enum": list(_SEARCH_URLS.keys()),
                },
                "query": {
                    "type": "string",
                    "description": "Search query string",
                },
            },
            "required": ["site", "query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from urllib.parse import quote_plus

        site: str = kwargs.get("site", "").strip().lower()
        query: str = kwargs.get("query", "").strip()

        if not site or not query:
            return ToolResult(
                success=False, output="", error="Both 'site' and 'query' are required."
            )

        template = _SEARCH_URLS.get(site)
        if not template:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported site: {site!r}. Supported: {list(_SEARCH_URLS.keys())}",
            )

        url = template.format(query=quote_plus(query))

        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return ToolResult(
                success=True,
                output=f"Opened search results for '{query}' on {site.capitalize()}.",
                data={"url": url},
            )
        except Exception as exc:
            logger.exception("Failed to open browser search URL %r", url)
            return ToolResult(success=False, output="", error=str(exc))


@register_tool
class BrowserOpenURLTool(AbstractTool):
    """Navigate to an explicit URL in the default browser."""

    @property
    def name(self) -> str:
        return "browser_open_url"

    @property
    def description(self) -> str:
        return "Open a specific URL in the default web browser."

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.LOW

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL to open, including scheme (https://...)",
                }
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        url: str = kwargs.get("url", "").strip()
        if not url:
            return ToolResult(success=False, output="", error="url is required")

        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return ToolResult(success=True, output=f"Opened: {url}", data={"url": url})
        except Exception as exc:
            logger.exception("Failed to open URL %r", url)
            return ToolResult(success=False, output="", error=str(exc))
