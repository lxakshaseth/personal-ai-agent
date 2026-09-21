"""
Centralized configuration using Pydantic Settings.
All values come from environment variables / .env file — no hardcoded credentials.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always locate the project root .env file regardless of current working directory
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BASE_DIR / ".env"
if _ENV_FILE.exists():
    load_dotenv(dotenv_path=_ENV_FILE, override=False)


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), ".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


    # ── Application ───────────────────────────────────────────────────────────
    app_name: str = Field(default="personal-ai-agent")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)
    reload: bool = Field(default=False)

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: LogLevel = Field(default=LogLevel.INFO)
    log_dir: str = Field(default="logs")
    audit_log_file: str = Field(default="logs/audit.jsonl")

    # ── Groq ──────────────────────────────────────────────────────────────────
    groq_api_key: str = Field(..., description="Groq API key — set via GROQ_API_KEY env var")
    groq_model: str = Field(
        default="openai/gpt-oss-120b",
        description="Groq model name — set via GROQ_MODEL env var",
    )
    groq_fast_model: str = Field(
        default="qwen/qwen3.8-27b",
        validation_alias=AliasChoices("groq_fast_model", "fast_model"),
        description="Fast model for intent classification, short responses, and greetings",
    )
    groq_reasoning_model: str = Field(
        default="openai/gpt-oss-120b",
        validation_alias=AliasChoices("groq_reasoning_model", "reasoning_model"),
        description="Reasoning model for complex planning and tool use",
    )

    groq_max_tokens: int = Field(default=1024)
    groq_temperature: float = Field(default=0.0)
    debug_performance: bool = Field(
        default=False,
        validation_alias=AliasChoices("debug_performance", "perf_debug"),
        description="Emit detailed latency metrics in logs",
    )

    # ── Agent ─────────────────────────────────────────────────────────────────
    agent_max_iterations: int = Field(default=10)
    agent_require_confirmation: bool = Field(default=True)

    # ── Security: filesystem paths ────────────────────────────────────────────
    allowed_base_paths: list[str] | str = Field(
        default_factory=lambda: ["C:\\Users", "C:\\Temp"],
        validation_alias=AliasChoices("allowed_paths", "allowed_base_paths"),
        description=(
            "Comma-separated list of root directories the agent may operate in. "
            "Set via ALLOWED_PATHS or ALLOWED_BASE_PATHS env var."
        ),
    )


    # ── Security: terminal commands & granular controls ───────────────────────
    allow_shell_commands: bool = Field(
        default=False,
        description=(
            "When false (default), all terminal tool calls are rejected. "
            "Set ALLOW_SHELL_COMMANDS=true to enable. "
            "Only commands in ALLOWED_COMMANDS may then be used."
        ),
    )
    allowed_commands: list[str] | str = Field(
        default_factory=lambda: ["python", "node", "npm", "git", "docker"],
        description=(
            "Allowlist of executable names that the terminal tool may run. "
            "Set via ALLOWED_COMMANDS env var (comma-separated)."
        ),
    )
    allow_file_deletion: bool = Field(
        default=True,
        description="Allow deleting files and folders (requires confirmation if HIGH risk).",
    )
    allow_browser_automation: bool = Field(
        default=True,
        description="Allow browser open URL and web search tools.",
    )
    allow_whatsapp_messaging: bool = Field(
        default=True,
        description="Allow sending WhatsApp messages through desktop app.",
    )
    allow_system_controls: bool = Field(
        default=True,
        description="Allow computer shutdown, restart, and lock actions.",
    )
    disabled_tools: list[str] = Field(
        default_factory=list,
        description="List of individual tool names that are explicitly disabled.",
    )

    # ── Voice Configuration ───────────────────────────────────────────────────
    voice_enabled: bool = Field(
        default=True,
        description="Enable voice interface (STT/TTS)",
    )
    stt_provider: str = Field(
        default="groq",
        description="Speech-to-text provider (groq, openai, whisper, mock)",
    )
    tts_provider: str = Field(
        default="system",
        description="Text-to-speech provider (system, pyttsx3, mock)",
    )
    wake_word_enabled: bool = Field(
        default=False,
        description="Require wake word before processing voice commands",
    )
    wake_word: str = Field(
        default="Jarvis",
        description="Wake word string, e.g. Jarvis",
    )

    # ── Real-Time Streaming Voice Settings ────────────────────────────────────
    voice_mode: str = Field(default="fast", description="Voice pipeline mode: 'fast' or 'standard'")
    voice_vad_aggressiveness: int = Field(default=3, ge=0, le=3, description="WebRTC VAD filter level (0-3)")
    voice_silence_threshold_ms: int = Field(default=450, ge=200, le=3000, description="Silence timeout before STT finalization")
    voice_chunk_min_words: int = Field(default=4, ge=2, le=15, description="Min words before chunk boundary split")
    voice_max_history: int = Field(default=8, ge=2, le=30, description="Max conversation turns in sliding history")
    debug_voice_latency: bool = Field(default=True, description="Log detailed TTFA pipeline latency metrics")

    # ── Storage (future) ──────────────────────────────────────────────────────
    database_url: Optional[str] = Field(default=None)
    redis_url: Optional[str] = Field(default=None)


    # ── Validators ────────────────────────────────────────────────────
    @field_validator("groq_api_key")
    @classmethod
    def groq_key_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("GROQ_API_KEY must not be empty")
        return v.strip()

    @field_validator("groq_temperature")
    @classmethod
    def temperature_range(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("groq_temperature must be between 0.0 and 2.0")
        return v

    @field_validator("allowed_commands", mode="after")
    @classmethod
    def parse_allowed_commands(cls, v: list[str] | str) -> list[str]:
        """Accept comma-separated string from env or a list."""
        if isinstance(v, str):
            return [cmd.strip().lower() for cmd in v.split(",") if cmd.strip()]
        return [str(item).lower() for item in v]

    @field_validator("allowed_base_paths", mode="after")
    @classmethod
    def parse_allowed_base_paths(cls, v: list[str] | str) -> list[str]:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return [str(item) for item in v]



@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton (created once per process)."""
    return Settings()  # type: ignore[call-arg]


def reload_settings() -> Settings:
    """Clear cached settings and force reload from .env."""
    get_settings.cache_clear()
    if _ENV_FILE.exists():
        load_dotenv(dotenv_path=_ENV_FILE, override=True)
    return get_settings()

