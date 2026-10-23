"""Global rate limiter: a minimum gap between any two outgoing Codeforces requests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class RateLimiter:
    """Ensures at least `min_interval` seconds between consecutive `acquire()` returns.

    The clock and sleep functions are injectable so tests can run without real waiting.
    A single instance is shared by the whole worker process, and only one worker runs
    (enforced with a Postgres advisory lock), which makes it global for the server.
    """

    def __init__(
        self,
        min_interval: float,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request may be sent, then reserve that slot."""
        async with self._lock:
            if self._last is not None:
                wait = self._last + self.min_interval - self._clock()
                if wait > 0:
                    await self._sleep(wait)
            self._last = self._clock()
