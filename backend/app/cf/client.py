"""Codeforces API client. Every request goes through the shared RateLimiter and retries on transient errors."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app import config
from app.cf.ratelimit import RateLimiter, Sleep

log = logging.getLogger(__name__)


class CFError(Exception):
    """Codeforces answered FAILED (non-retryable). `comment` is the API's message."""

    def __init__(self, comment: str) -> None:
        super().__init__(comment)
        self.comment = comment


class CFNotFound(CFError):
    """The requested handle does not exist."""


class CFUnavailable(CFError):
    """Retries exhausted on rate limiting, timeouts, or server errors."""


class _Retryable(Exception):
    pass


def backoff_delay(attempt: int) -> float:
    """Exponential backoff for retry number `attempt` (0-based)."""
    return min(config.CF_BACKOFF_BASE_S * (2**attempt), config.CF_BACKOFF_MAX_S)


class CodeforcesClient:
    """Thin typed wrapper over the four API methods CF Coach uses."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        base_url: str = "https://codeforces.com/api",
        sleep: Sleep = asyncio.sleep,
        max_retries: int = config.CF_MAX_RETRIES,
    ) -> None:
        self._http = http
        self._limiter = limiter
        self._base = base_url.rstrip("/")
        self._sleep = sleep
        self._max_retries = max_retries

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Call `method` and return its `result`, retrying transient failures."""
        last_reason = "unknown error"
        for attempt in range(self._max_retries + 1):
            await self._limiter.acquire()
            try:
                return await self._attempt(method, params or {})
            except _Retryable as exc:
                last_reason = str(exc)
                if attempt == self._max_retries:
                    break
                delay = backoff_delay(attempt)
                log.warning("CF %s failed (%s); retry %d in %.1fs", method, exc, attempt + 1, delay)
                await self._sleep(delay)
        raise CFUnavailable(f"Codeforces is unavailable right now ({last_reason})")

    async def _attempt(self, method: str, params: dict[str, Any]) -> Any:
        try:
            resp = await self._http.get(f"{self._base}/{method}", params=params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise _Retryable(type(exc).__name__) from exc

        try:
            body = resp.json()
        except ValueError:
            body = None

        if isinstance(body, dict) and body.get("status") == "OK":
            return body.get("result")

        comment = str(body.get("comment") or "") if isinstance(body, dict) else ""
        if "call limit exceeded" in comment.lower():
            raise _Retryable("call limit exceeded")
        if resp.status_code >= 500 or body is None:
            raise _Retryable(f"HTTP {resp.status_code}")
        if "not found" in comment.lower():
            raise CFNotFound(comment)
        raise CFError(comment or f"HTTP {resp.status_code}")

    async def user_info(self, handles: list[str]) -> list[dict[str, Any]]:
        """Users for up to CF_USER_INFO_BATCH handles (canonical casing in `handle`)."""
        out: list[dict[str, Any]] = []
        for i in range(0, len(handles), config.CF_USER_INFO_BATCH):
            batch = handles[i : i + config.CF_USER_INFO_BATCH]
            out.extend(await self.call("user.info", {"handles": ";".join(batch)}))
        return out

    async def user_status(self, handle: str, from_: int, count: int) -> list[dict[str, Any]]:
        """Submissions, newest first. `from_` is 1-based."""
        return await self.call("user.status", {"handle": handle, "from": from_, "count": count})

    async def user_rating(self, handle: str) -> list[dict[str, Any]]:
        return await self.call("user.rating", {"handle": handle})

    async def problemset_problems(self) -> dict[str, Any]:
        """{'problems': [...], 'problemStatistics': [...]}."""
        return await self.call("problemset.problems")


def make_http_client(user_agent: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=config.CF_TIMEOUT_S,
    )
