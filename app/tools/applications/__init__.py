"""
Applications tools package.

Exports:
1. open_application
2. close_application
And application mapping configuration:
- APP_DEFINITIONS, find_app, resolve_executable
"""
from app.tools.applications.app_config import (
    APP_DEFINITIONS,
    AppDefinition,
    find_app,
    resolve_executable,
)
from app.tools.applications.tools import (
    CloseApplicationTool,
    OpenApplicationTool,
    SendWhatsAppMessageTool,
)

__all__ = [
    "OpenApplicationTool",
    "CloseApplicationTool",
    "SendWhatsAppMessageTool",
    "APP_DEFINITIONS",
    "AppDefinition",
    "find_app",
    "resolve_executable",
]

