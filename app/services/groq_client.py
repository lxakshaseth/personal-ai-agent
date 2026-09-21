"""
Groq API client — async wrapper with structured error handling.

Catches and classifies every Groq / network error into typed exceptions
so the agent layer can handle them gracefully.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, AsyncGenerator

import groq
from groq import AsyncGroq

from app.agent.schemas import GroqErrorDetail, GroqErrorType
from app.config.settings import get_settings
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.utils.exceptions import PlannerError

logger = logging.getLogger(__name__)


def _classify_groq_error(exc: Exception) -> GroqErrorDetail:
    """
    Map a raw Groq/httpx exception to a structured GroqErrorDetail.

    Returns a GroqErrorDetail that callers can inspect for error type,
    retryability, and HTTP status code.
    """
    exc_str = str(exc).lower()

    # ── Groq SDK typed errors ─────────────────────────────────────────────────
    if isinstance(exc, groq.AuthenticationError):
        return GroqErrorDetail(
            error_type=GroqErrorType.INVALID_API_KEY,
            message="Invalid or expired Groq API key. Check GROQ_API_KEY in your .env file.",
            retryable=False,
            status_code=401,
        )

    if isinstance(exc, groq.RateLimitError):
        return GroqErrorDetail(
            error_type=GroqErrorType.RATE_LIMIT,
            message="Groq rate limit exceeded. The request will be retried after a delay.",
            retryable=True,
            status_code=429,
        )

    if isinstance(exc, groq.APITimeoutError):
        return GroqErrorDetail(
            error_type=GroqErrorType.TIMEOUT,
            message="Groq API request timed out.",
            retryable=True,
            status_code=None,
        )

    if isinstance(exc, groq.APIConnectionError):
        return GroqErrorDetail(
            error_type=GroqErrorType.NETWORK,
            message=f"Network error contacting Groq API: {exc}",
            retryable=True,
            status_code=None,
        )

    if isinstance(exc, groq.BadRequestError):
        return GroqErrorDetail(
            error_type=GroqErrorType.MALFORMED_RESPONSE,
            message=f"Groq rejected the request (400): {exc}",
            retryable=False,
            status_code=400,
        )

    if isinstance(exc, groq.APIStatusError):
        status = getattr(exc, "status_code", None)
        return GroqErrorDetail(
            error_type=GroqErrorType.UNKNOWN,
            message=f"Groq API error (HTTP {status}): {exc}",
            retryable=status is not None and status >= 500,
            status_code=status,
        )

    # ── asyncio / network fallbacks ───────────────────────────────────────────
    if isinstance(exc, asyncio.TimeoutError):
        return GroqErrorDetail(
            error_type=GroqErrorType.TIMEOUT,
            message="Request timed out (asyncio).",
            retryable=True,
        )

    if "timeout" in exc_str:
        return GroqErrorDetail(
            error_type=GroqErrorType.TIMEOUT,
            message=f"Timeout: {exc}",
            retryable=True,
        )

    if any(kw in exc_str for kw in ("connection", "network", "unreachable")):
        return GroqErrorDetail(
            error_type=GroqErrorType.NETWORK,
            message=f"Network failure: {exc}",
            retryable=True,
        )

    return GroqErrorDetail(
        error_type=GroqErrorType.UNKNOWN,
        message=str(exc),
        retryable=False,
    )


class GroqClient:
    """
    Async wrapper around the Groq Python SDK.

    Features:
    - Reads all config from Settings (no hardcoded credentials).
    - Structured error classification via _classify_groq_error().
    - chat_completion()            — plain text response
    - chat_completion_with_tools() — function-calling response
    """

    def __init__(self) -> None:
        self._circuit_breaker = CircuitBreaker("groq_api", failure_threshold=5, cooldown_seconds=20.0)
        self.max_retries = 3
        self.request_timeout = 25.0
        self._refresh_client()

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    def _refresh_client(self) -> None:
        settings = get_settings()
        self._current_key = settings.groq_api_key
        self._client = AsyncGroq(api_key=settings.groq_api_key, max_retries=0)
        self._model = settings.groq_model
        self._max_tokens = settings.groq_max_tokens
        self._temperature = settings.groq_temperature
        self._fast_model = settings.groq_fast_model
        logger.debug("GroqClient initialised (model=%s, fast_model=%s)", self._model, self._fast_model)

    @property
    def fast_model(self) -> str:
        return getattr(self, "_fast_model", "llama-3.1-8b-instant")

    def _get_client(self) -> AsyncGroq:
        settings = get_settings()
        if getattr(self, "_current_key", None) != settings.groq_api_key:
            self._refresh_client()
        return self._client

    async def close(self) -> None:
        """Gracefully close AsyncGroq HTTP client connection pools."""
        if hasattr(self, "_client") and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception:
                pass

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        _retried: bool = False,
    ) -> str:
        """
        Plain text chat completion guarded by CircuitBreaker, timeouts, and exponential backoff retries.

        Returns:
            The assistant's reply as a string.

        Raises:
            PlannerError with a GroqErrorDetail attached on any API failure.
        """
        client = self._get_client()
        target_model = model or self._model

        response = None
        for attempt in range(self.max_retries):
            # 1. Circuit breaker availability check
            if not await self._circuit_breaker.is_available():
                detail = GroqErrorDetail(
                    error_type=GroqErrorType.NETWORK,
                    message="Circuit breaker OPEN: Groq API temporarily unavailable due to repeated failures. Please try again shortly.",
                    retryable=True,
                )
                err = PlannerError(detail.message, detail=detail.model_dump_json())
                err.groq_error = detail
                raise err

            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=target_model,
                        messages=messages,
                        temperature=temperature if temperature is not None else self._temperature,
                        max_tokens=max_tokens or self._max_tokens,
                    ),
                    timeout=self.request_timeout,
                )
                await self._circuit_breaker.record_success()
                break
            except groq.AuthenticationError as exc:
                if not _retried:
                    from app.config.settings import reload_settings
                    new_settings = reload_settings()
                    if new_settings.groq_api_key and new_settings.groq_api_key != self._current_key:
                        logger.info("Detected updated GROQ_API_KEY from .env; retrying...")
                        self._refresh_client()
                        return await self.chat_completion(
                            messages,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            _retried=True,
                        )
                detail = _classify_groq_error(exc)
                err = PlannerError(detail.message, detail=detail.model_dump_json())
                err.groq_error = detail
                raise err from exc
            except Exception as exc:
                exc_str = str(exc).lower()
                is_rate_limit = "rate_limit" in exc_str or "429" in exc_str or isinstance(exc, groq.RateLimitError)
                is_not_found = "model_not_found" in exc_str or "does not exist" in exc_str

                if not _retried and (is_rate_limit or is_not_found):
                    fallback = "openai/gpt-oss-20b" if target_model != "openai/gpt-oss-20b" else "openai/gpt-oss-120b"
                    reason = "Rate limit reached" if is_rate_limit else "Model not available"
                    logger.warning("%s on %s. Instantly falling back to %s", reason, target_model, fallback)
                    return await self.chat_completion(
                        messages,
                        model=fallback,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        _retried=True,
                    )

                detail = _classify_groq_error(exc)
                if attempt == self.max_retries - 1:
                    await self._circuit_breaker.record_failure(exc)

                if detail.retryable and attempt < self.max_retries - 1:
                    backoff = (0.5 * (2 ** attempt)) + random.uniform(0.1, 0.3)
                    logger.warning(
                        "Groq chat_completion error [%s]: %s. Retrying in %0.2fs (attempt %d/%d)...",
                        detail.error_type.value,
                        detail.message,
                        backoff,
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(backoff)
                    continue

                logger.error(
                    "Groq chat_completion failed [%s]: %s",
                    detail.error_type.value,
                    detail.message,
                )
                err = PlannerError(detail.message, detail=detail.model_dump_json())
                err.groq_error = detail
                raise err from exc

        if response is None:
            detail = GroqErrorDetail(
                error_type=GroqErrorType.UNKNOWN,
                message="No response received from Groq API after retries.",
            )
            err = PlannerError(detail.message, detail=detail.model_dump_json())
            err.groq_error = detail
            raise err

        try:
            content = response.choices[0].message.content or ""
        except (IndexError, AttributeError) as exc:
            detail = GroqErrorDetail(
                error_type=GroqErrorType.MALFORMED_RESPONSE,
                message=f"Groq returned an unexpected response shape: {exc}",
            )
            err = PlannerError(detail.message, detail=detail.model_dump_json())
            err.groq_error = detail
            raise err from exc

        logger.debug(
            "Groq chat_completion OK: %d chars, tokens=%s",
            len(content),
            response.usage.total_tokens if response.usage else "?",
        )
        return content

    async def stream_chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        _retried: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming chat completion yielding text token deltas as they arrive from Groq.
        Supports instant model failover on 429 rate limit or missing model.
        """
        client = self._get_client()
        target_model = model or self._model

        try:
            stream = await client.chat.completions.create(
                model=target_model,
                messages=messages,
                stream=True,
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens or self._max_tokens,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

            await self._circuit_breaker.record_success()

        except Exception as exc:
            exc_str = str(exc).lower()
            is_rate_limit = "rate_limit" in exc_str or "429" in exc_str or isinstance(exc, groq.RateLimitError)
            is_not_found = "model_not_found" in exc_str or "does not exist" in exc_str

            if not _retried and (is_rate_limit or is_not_found):
                fallback = "openai/gpt-oss-20b" if target_model != "openai/gpt-oss-20b" else "openai/gpt-oss-120b"
                logger.warning("Streaming failover from %s to %s (reason: %s)", target_model, fallback, exc)
                async for token in self.stream_chat_completion(
                    messages,
                    model=fallback,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    _retried=True,
                ):
                    yield token
                return

            detail = _classify_groq_error(exc)
            await self._circuit_breaker.record_failure(exc)
            err = PlannerError(detail.message, detail=detail.model_dump_json())
            err.groq_error = detail
            raise err from exc


    async def chat_completion_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tool_choice: str = "auto",
        _retried: bool = False,
    ) -> Any:
        """
        Function-calling chat completion guarded by CircuitBreaker, timeouts, and retries.
        """
        client = self._get_client()
        target_model = model or self._model

        response = None
        for attempt in range(self.max_retries):
            if not await self._circuit_breaker.is_available():
                detail = GroqErrorDetail(
                    error_type=GroqErrorType.NETWORK,
                    message="Circuit breaker OPEN: Groq API temporarily unavailable due to repeated failures. Please try again shortly.",
                    retryable=True,
                )
                err = PlannerError(detail.message, detail=detail.model_dump_json())
                err.groq_error = detail
                raise err

            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=target_model,
                        messages=messages,
                        tools=tools,
                        tool_choice=tool_choice,
                        temperature=temperature if temperature is not None else self._temperature,
                        max_tokens=max_tokens or self._max_tokens,
                    ),
                    timeout=self.request_timeout,
                )
                await self._circuit_breaker.record_success()
                break
            except groq.AuthenticationError as exc:
                if not _retried:
                    from app.config.settings import reload_settings
                    new_settings = reload_settings()
                    if new_settings.groq_api_key and new_settings.groq_api_key != self._current_key:
                        logger.info("Detected updated GROQ_API_KEY from .env; retrying...")
                        self._refresh_client()
                        return await self.chat_completion_with_tools(
                            messages,
                            tools,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            tool_choice=tool_choice,
                            _retried=True,
                        )
                detail = _classify_groq_error(exc)
                err = PlannerError(detail.message, detail=detail.model_dump_json())
                err.groq_error = detail
                raise err from exc
            except Exception as exc:
                exc_str = str(exc).lower()
                is_rate_limit = "rate_limit" in exc_str or "429" in exc_str or isinstance(exc, groq.RateLimitError)
                is_not_found = "model_not_found" in exc_str or "does not exist" in exc_str

                if not _retried and (is_rate_limit or is_not_found):
                    fallback = "openai/gpt-oss-20b" if target_model != "openai/gpt-oss-20b" else "openai/gpt-oss-120b"
                    reason = "Rate limit reached" if is_rate_limit else "Model not available"
                    logger.warning("%s on %s. Instantly falling back to %s", reason, target_model, fallback)
                    return await self.chat_completion_with_tools(
                        messages,
                        tools,
                        model=fallback,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        tool_choice=tool_choice,
                        _retried=True,
                    )

                detail = _classify_groq_error(exc)
                if attempt == self.max_retries - 1:
                    await self._circuit_breaker.record_failure(exc)

                if detail.retryable and attempt < self.max_retries - 1:
                    backoff = (0.5 * (2 ** attempt)) + random.uniform(0.1, 0.3)
                    logger.warning(
                        "Groq tool completion error [%s]: %s. Retrying in %0.2fs (attempt %d/%d)...",
                        detail.error_type.value,
                        detail.message,
                        backoff,
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(backoff)
                    continue

                logger.error(
                    "Groq chat_completion_with_tools failed [%s]: %s",
                    detail.error_type.value,
                    detail.message,
                )
                err = PlannerError(detail.message, detail=detail.model_dump_json())
                err.groq_error = detail
                raise err from exc

        if response is None:
            detail = GroqErrorDetail(
                error_type=GroqErrorType.UNKNOWN,
                message="No response received from Groq API after retries.",
            )
            err = PlannerError(detail.message, detail=detail.model_dump_json())
            err.groq_error = detail
            raise err

        try:
            message = response.choices[0].message
        except (IndexError, AttributeError) as exc:
            detail = GroqErrorDetail(
                error_type=GroqErrorType.MALFORMED_RESPONSE,
                message=f"Groq returned an unexpected response shape: {exc}",
            )
            err = PlannerError(detail.message, detail=detail.model_dump_json())
            err.groq_error = detail
            raise err from exc

        logger.debug(
            "Groq tool completion OK: tool_calls=%d, tokens=%s",
            len(message.tool_calls or []),
            response.usage.total_tokens if response.usage else "?",
        )
        return message



# ── Singleton ─────────────────────────────────────────────────────────────────

_groq_client: GroqClient | None = None


def get_groq_client() -> GroqClient:
    global _groq_client
    if _groq_client is None:
        _groq_client = GroqClient()
    return _groq_client
