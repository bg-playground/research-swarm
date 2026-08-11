"""Simple in-process circuit breaker for protecting external calls."""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"       # normal operation
    OPEN = "open"           # failing fast
    HALF_OPEN = "half_open" # trial request allowed


class CircuitBreaker:
    """
    Lightweight circuit breaker.

    - CLOSED: calls pass through. Consecutive failures increment a counter.
    - OPEN: calls fail immediately until the cool-down expires.
    - HALF_OPEN: one trial call is allowed. Success → CLOSED, failure → OPEN again.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        name: str = "default",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            # Check whether cool-down has elapsed
            if self._opened_at is not None and (time.monotonic() - self._opened_at) >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("CircuitBreaker[%s] → HALF_OPEN (cool-down elapsed)", self.name)
        return self._state

    def allow_request(self) -> bool:
        """Return True if a request is permitted in the current state."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True  # allow the trial
        return False  # OPEN

    def record_success(self) -> None:
        if self._state != CircuitState.CLOSED:
            logger.info("CircuitBreaker[%s] → CLOSED (success)", self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._state == CircuitState.HALF_OPEN:
            # Trial failed → open again
            self._trip()
            return
        if self._failure_count >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        logger.warning(
            "CircuitBreaker[%s] → OPEN after %d consecutive failure(s). "
            "Cooling down for %.0fs",
            self.name,
            self._failure_count,
            self.recovery_timeout,
        )

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name!r}, state={self.state.value}, "
            f"failures={self._failure_count})"
        )


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, breaker: CircuitBreaker) -> None:
        remaining = 0.0
        if breaker._opened_at is not None:
            elapsed = time.monotonic() - breaker._opened_at
            remaining = max(0.0, breaker.recovery_timeout - elapsed)
        super().__init__(
            f"CircuitBreaker[{breaker.name}] is OPEN. "
            f"Rejecting call. Retry in ~{remaining:.0f}s."
        )
        self.breaker = breaker
