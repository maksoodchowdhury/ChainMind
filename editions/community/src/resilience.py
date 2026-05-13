"""Resilience primitives: circuit breaker + retry budget."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    pass


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float = 0.0


class CircuitBreaker:
    """Simple in-process circuit breaker."""

    def __init__(self, fail_threshold: int = 5, recovery_seconds: int = 30) -> None:
        self._threshold = max(1, int(fail_threshold))
        self._recovery = max(1, int(recovery_seconds))
        self._state = CircuitState()
        self._lock = Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._state.failures < self._threshold:
                return True
            elapsed = time.time() - self._state.opened_at
            if elapsed >= self._recovery:
                self._state.failures = 0
                self._state.opened_at = 0.0
                return True
            return False

    def mark_success(self) -> None:
        with self._lock:
            self._state.failures = 0
            self._state.opened_at = 0.0

    def mark_failure(self) -> None:
        with self._lock:
            self._state.failures += 1
            if self._state.failures >= self._threshold and self._state.opened_at == 0.0:
                self._state.opened_at = time.time()


def call_with_retry_budget(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    backoff_seconds: float = 0.3,
) -> T:
    """Retry wrapper with bounded attempts and exponential backoff."""
    attempts = max(1, int(max_attempts))
    base = max(0.0, float(backoff_seconds))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # pragma: no cover - exact exceptions vary by backend
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(base * (2 ** (attempt - 1)))
    raise RuntimeError(f"Operation failed after {attempts} attempt(s): {last_error}")
