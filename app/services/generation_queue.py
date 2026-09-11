"""Fair in-process FIFO queue for full presentation generation jobs."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import threading
import uuid


class GenerationQueue:
    """Limits concurrent decks while preserving first-come, first-served order."""

    def __init__(self, max_active_jobs: int = 1):
        self.max_active_jobs=max(1,max_active_jobs)
        self._pending: deque[str]=deque()
        self._active=0
        self._condition=threading.Condition()

    def snapshot(self, job_id: str | None = None) -> dict[str, int | None]:
        """Return a lock-consistent view for the user-facing queue indicator."""
        with self._condition:
            pending=[ticket.split(":",1)[0] for ticket in self._pending]
            pending_position=(pending.index(job_id)+1) if job_id in pending else None
            # An active job occupies a worker slot before queued tickets can
            # start, so it is included in the count of jobs ahead.
            jobs_ahead=(self._active + (pending_position-1)) if pending_position else 0
            return {
                "queue_depth": self._active+len(pending),
                "waiting_jobs": len(pending),
                "active_jobs": self._active,
                "max_active_jobs": self.max_active_jobs,
                "position": pending_position,
                "jobs_ahead": jobs_ahead,
            }

    @contextmanager
    def slot(self, job_id: str):
        ticket=f"{job_id}:{uuid.uuid4().hex}"
        with self._condition:
            self._pending.append(ticket)
            while self._pending[0] != ticket or self._active >= self.max_active_jobs:
                self._condition.wait()
            self._pending.popleft(); self._active+=1
        try:
            yield
        finally:
            with self._condition:
                self._active-=1
                self._condition.notify_all()


_queue: GenerationQueue | None=None
_queue_lock=threading.Lock()


def shared_generation_queue(max_active_jobs: int) -> GenerationQueue:
    global _queue
    with _queue_lock:
        if _queue is None or _queue.max_active_jobs != max_active_jobs:
            _queue=GenerationQueue(max_active_jobs)
        return _queue
