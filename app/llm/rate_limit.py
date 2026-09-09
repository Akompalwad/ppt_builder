"""Thread-safe rolling request/token budget for hosted LLM providers."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
import time
import uuid


class RateLimitWaitExceeded(RuntimeError):
    pass


@dataclass
class _Reservation:
    identifier: str
    created_at: float
    tokens: int


class RollingRateGate:
    """Reserve capacity before a request, then settle against actual usage."""

    def __init__(self, *, tokens_per_minute: int, requests_per_minute: int, max_wait_seconds: float):
        self.tokens_per_minute=tokens_per_minute
        self.requests_per_minute=requests_per_minute
        self.max_wait_seconds=max_wait_seconds
        self._entries: deque[_Reservation]=deque()
        self._condition=threading.Condition()

    def _purge(self, now: float) -> None:
        while self._entries and now-self._entries[0].created_at >= 60:
            self._entries.popleft()

    def reserve(self, estimated_tokens: int) -> str:
        estimated_tokens=max(1, estimated_tokens)
        if estimated_tokens > self.tokens_per_minute:
            raise ValueError("One LLM request exceeds the configured tokens-per-minute limit.")
        deadline=time.monotonic()+self.max_wait_seconds
        with self._condition:
            while True:
                now=time.monotonic(); self._purge(now)
                used_tokens=sum(entry.tokens for entry in self._entries)
                if len(self._entries) < self.requests_per_minute and used_tokens+estimated_tokens <= self.tokens_per_minute:
                    identifier=uuid.uuid4().hex
                    self._entries.append(_Reservation(identifier,now,estimated_tokens))
                    return identifier
                if now >= deadline:
                    raise RateLimitWaitExceeded("LLM rate limit queue exceeded its maximum wait time.")
                # Capacity changes at the oldest reservation expiry, or when a
                # completed request settles with its actual lower usage.
                until_expiry=max(.05, 60-(now-self._entries[0].created_at)) if self._entries else .05
                self._condition.wait(timeout=min(until_expiry,deadline-now))

    def settle(self, identifier: str, actual_tokens: int) -> None:
        with self._condition:
            for entry in self._entries:
                if entry.identifier == identifier:
                    entry.tokens=max(0, actual_tokens)
                    break
            self._condition.notify_all()


_gates: dict[str, RollingRateGate]={}
_gates_lock=threading.Lock()


def shared_rate_gate(key: str, *, tokens_per_minute: int, requests_per_minute: int, max_wait_seconds: float) -> RollingRateGate:
    with _gates_lock:
        gate=_gates.get(key)
        if gate is None:
            gate=RollingRateGate(tokens_per_minute=tokens_per_minute,requests_per_minute=requests_per_minute,max_wait_seconds=max_wait_seconds)
            _gates[key]=gate
        return gate


def estimate_request_tokens(prompt: str, max_output_tokens: int) -> int:
    """Conservative, dependency-free estimate used only before a request."""
    return max(1, (len(prompt)+3)//4) + max(1, max_output_tokens)
