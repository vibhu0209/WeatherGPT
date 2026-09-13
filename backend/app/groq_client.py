"""Groq client: circuit breaker, budget, OpenAI-compatible chat completions."""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

import httpx

from .metrics import metrics
from .models import Settings

_log = logging.getLogger('weathergpt.groq')
GROQ_CHAT_URL = 'https://api.groq.com/openai/v1/chat/completions'


def _log_groq(event: str, **fields: Any) -> None:
    """Structured Groq logs without secrets or user content."""
    parts = [f'{key}={value}' for key, value in fields.items() if value is not None]
    _log.info('%s %s', event, ' '.join(parts) if parts else '')


class GroqClient:
    """Provider-protection only — normal human chat should rarely hit these caps."""

    def __init__(self, settings: Settings | None = None, max_calls_per_minute: int = 45):
        self.settings = settings or Settings()
        self.max_calls_per_minute = max_calls_per_minute
        self._calls: deque[float] = deque()
        self._cooldown_until = 0.0
        self._quota_exhausted = False

    @property
    def enabled(self) -> bool:
        return bool(self.settings.groq_api_key.strip() and self.settings.groq_model.strip())

    @property
    def model(self) -> str:
        return self.settings.groq_model.strip()

    def _budget_available(self) -> bool:
        now = time.monotonic()
        while self._calls and self._calls[0] < now - 60:
            self._calls.popleft()
        return len(self._calls) < self.max_calls_per_minute

    def _circuit_open(self) -> bool:
        return time.monotonic() < self._cooldown_until

    def trip(self, seconds: float, *, quota: bool = False) -> None:
        self._cooldown_until = time.monotonic() + seconds
        if quota:
            self._quota_exhausted = True

    def available(self) -> bool:
        return self.enabled and not self._circuit_open() and self._budget_available()

    async def chat_completions(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = 'auto',
        temperature: float = 0.2,
        max_tokens: int = 1024,
        response_format: dict[str, Any] | None = None,
        timeout: float = 35,
    ) -> dict[str, Any] | None:
        """POST chat/completions. Returns parsed JSON or None on soft failure."""
        if not self.available():
            reason = 'not_configured'
            if self.enabled and self._circuit_open():
                reason = 'circuit_open'
            elif self.enabled:
                reason = 'budget'
            _log_groq(
                'GROQ_CALL_FAILED',
                MODEL_NAME=self.model or 'none',
                reason=reason,
                FALLBACK_USED=True,
            )
            metrics.inc('groq_skipped')
            return None

        self._calls.append(time.monotonic())
        metrics.inc('groq_calls')
        body: dict[str, Any] = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        if tools:
            body['tools'] = tools
            if tool_choice is not None:
                body['tool_choice'] = tool_choice
            # gpt-oss models do not support parallel tool calls; omit the flag on unknown models.
        if response_format:
            body['response_format'] = response_format

        started = time.monotonic()
        _log_groq('GROQ_CALL_STARTED', MODEL_NAME=self.model, reason_for_call='chat_orchestration')
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.post(
                    GROQ_CHAT_URL,
                    headers={
                        'Authorization': f'Bearer {self.settings.groq_api_key}',
                        'Content-Type': 'application/json',
                    },
                    json=body,
                )
            latency_ms = int((time.monotonic() - started) * 1000)
            if response.status_code == 429:
                self.trip(45, quota=True)
                _log_groq(
                    'GROQ_CALL_FAILED',
                    MODEL_NAME=self.model,
                    http_status=429,
                    latency_ms=latency_ms,
                    FALLBACK_USED=True,
                )
                metrics.inc('groq_errors')
                return None
            if response.status_code in {401, 403}:
                self.trip(120, quota=True)
                _log_groq(
                    'GROQ_CALL_FAILED',
                    MODEL_NAME=self.model,
                    http_status=response.status_code,
                    latency_ms=latency_ms,
                    FALLBACK_USED=True,
                )
                metrics.inc('groq_errors')
                return None
            if response.status_code in {500, 502, 503, 504}:
                self.trip(60)
                _log_groq(
                    'GROQ_CALL_FAILED',
                    MODEL_NAME=self.model,
                    http_status=response.status_code,
                    latency_ms=latency_ms,
                    FALLBACK_USED=True,
                )
                metrics.inc('groq_errors')
                return None
            response.raise_for_status()
            _log_groq(
                'GROQ_CALL_SUCCESS',
                MODEL_NAME=self.model,
                http_status=response.status_code,
                latency_ms=latency_ms,
            )
            return response.json()
        except httpx.TimeoutException:
            self.trip(60)
            _log_groq(
                'GROQ_CALL_FAILED',
                MODEL_NAME=self.model,
                reason='timeout',
                latency_ms=int((time.monotonic() - started) * 1000),
                FALLBACK_USED=True,
            )
            metrics.inc('groq_errors')
            return None
        except Exception as error:
            _log_groq(
                'GROQ_CALL_FAILED',
                MODEL_NAME=self.model,
                exception=type(error).__name__,
                latency_ms=int((time.monotonic() - started) * 1000),
                FALLBACK_USED=True,
            )
            metrics.inc('groq_errors')
            return None


groq_client = GroqClient()
