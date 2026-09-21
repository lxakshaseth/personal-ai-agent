"""
Windows tools package.

Exports:
1. open_url
2. lock_computer
3. shutdown_computer
4. restart_computer
5. take_screenshot
"""
from app.tools.windows.tools import (
    LockComputerTool,
    OpenURLTool,
    RestartComputerTool,
    ShutdownComputerTool,
    TakeScreenshotTool,
)

__all__ = [
    "OpenURLTool",
    "LockComputerTool",
    "ShutdownComputerTool",
    "RestartComputerTool",
    "TakeScreenshotTool",
]
