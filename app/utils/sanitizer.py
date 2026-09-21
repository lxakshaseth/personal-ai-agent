"""
Data sanitizer for redacting sensitive credentials, API keys, tokens, and cookies
before emitting events over WebSocket or writing to public logs.
"""
from __future__ import annotations

import re
from typing import Any

# Sensitive dictionary key patterns (case-insensitive)
SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"passwd", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
    re.compile(r"cookie", re.IGNORECASE),
    re.compile(r"auth[_-]?header", re.IGNORECASE),
    re.compile(r"session[_-]?id", re.IGNORECASE),
    re.compile(r"private[_-]?key", re.IGNORECASE),
    re.compile(r"access[_-]?token", re.IGNORECASE),
    re.compile(r"refresh[_-]?token", re.IGNORECASE),
]

# Sensitive value regexes inside strings
SENSITIVE_VALUE_REGEXES = [
    # Groq API keys (gsk_...)
    re.compile(r"gsk_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    # OpenAI API keys (sk-...)
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    # Bearer authorization tokens
    re.compile(r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*", re.IGNORECASE),
    # JSON Web Tokens (JWT)
    re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}", re.IGNORECASE),
    # Cookie strings
    re.compile(r"cookie:\s*[^;\r\n]+", re.IGNORECASE),
]

REDACTED = "[REDACTED]"


def sanitize_text(text: str) -> str:
    """Redact sensitive patterns from a raw string."""
    if not isinstance(text, str):
        return text

    sanitized = text
    for regex in SENSITIVE_VALUE_REGEXES:
        sanitized = regex.sub(REDACTED, sanitized)
    return sanitized


def sanitize_payload(data: Any) -> Any:
    """
    Recursively sanitize dictionaries, lists, and primitives,
    redacting sensitive keys and values.
    """
    if isinstance(data, dict):
        sanitized_dict: dict[str, Any] = {}
        for key, value in data.items():
            key_str = str(key)
            if any(pattern.search(key_str) for pattern in SENSITIVE_KEY_PATTERNS):
                sanitized_dict[key] = REDACTED
            else:
                sanitized_dict[key] = sanitize_payload(value)
        return sanitized_dict

    if isinstance(data, (list, tuple, set)):
        return [sanitize_payload(item) for item in data]

    if isinstance(data, str):
        return sanitize_text(data)

    return data


# Backward-compatible alias
sanitize_data = sanitize_payload
