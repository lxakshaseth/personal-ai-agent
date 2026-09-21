"""
Custom exception hierarchy for the personal-ai-agent.
"""
from __future__ import annotations


class AgentBaseError(Exception):
    """Root exception for all agent errors."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        return f"{cls}(message={self.message!r}, detail={self.detail!r})"


# ── Configuration ──────────────────────────────────────────────────────────────

class ConfigurationError(AgentBaseError):
    """Raised when required configuration is missing or invalid."""


# ── Tool errors ────────────────────────────────────────────────────────────────

class ToolError(AgentBaseError):
    """Raised when a tool fails to execute."""

    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.tool_name = tool_name


class ToolNotFoundError(ToolError):
    """Raised when a requested tool is not registered."""


class ToolValidationError(ToolError):
    """Raised when tool arguments fail validation."""


# ── Permission errors ──────────────────────────────────────────────────────────

class PermissionDeniedError(AgentBaseError):
    """Raised when an action is blocked by the permission layer."""

    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        required_level: str | None = None,
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.required_level = required_level


class ConfirmationRequiredError(AgentBaseError):
    """Raised when a high-risk action needs explicit user confirmation."""

    def __init__(self, message: str, *, tool_name: str | None = None) -> None:
        super().__init__(message)
        self.tool_name = tool_name


# ── Agent / Planner errors ──────────────────────────────────────────────────────

class PlannerError(AgentBaseError):
    """Raised when the LLM planner fails."""


class ExecutorError(AgentBaseError):
    """Raised when the tool executor encounters an unrecoverable error."""


class MaxIterationsExceededError(AgentBaseError):
    """Raised when the agent exceeds its maximum tool-call iterations."""


# ── Voice errors ───────────────────────────────────────────────────────────────

class VoiceError(AgentBaseError):
    """Base exception for all voice interface errors."""


class SpeechRecognitionError(VoiceError):
    """Raised when STT fails to transcribe audio."""


class NoSpeechDetectedError(SpeechRecognitionError):
    """Raised when no speech was detected in the audio input."""


class TextToSpeechError(VoiceError):
    """Raised when TTS fails to synthesize speech."""


class MicrophoneError(VoiceError):
    """Raised when an audio recording or device error occurs."""


class MicrophoneUnavailableError(MicrophoneError):
    """Raised when no microphone is detected or access is denied."""


class VoiceTimeoutError(VoiceError):
    """Raised when listening for voice input times out."""


# ── Browser errors ─────────────────────────────────────────────────────────────

class BrowserError(AgentBaseError):
    """Raised when browser automation encounters an error."""
