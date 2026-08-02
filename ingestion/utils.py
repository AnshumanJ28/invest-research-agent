"""Shared helpers for ingestion agents: retry, rate limiting, TTL caching."""

from __future__ import annotations

import functools
import time
import threading
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger("ingestion")
T = TypeVar("T")


# --------------------------------------------------------------------------- #
# Retry with exponential backoff
# --------------------------------------------------------------------------- #

def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """Retry a call with exponential backoff. Raises the last exception if
    every attempt fails -- callers decide whether that should crash the whole
    ingestion run or be caught into a graceful 'unavailable' result."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "%s failed (attempt %d/%d): %s -- retrying in %.1fs",
                        fn.__name__, attempt, max_attempts, exc, delay,
                    )
                    time.sleep(delay)
            assert last_exc is not None
            raise last_exc
        return wrapper
    return decorator


# --------------------------------------------------------------------------- #
# Token-bucket rate limiter (SEC EDGAR: max 10 req/sec, be conservative)
# --------------------------------------------------------------------------- #

class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: float):
        self.max_calls = max_calls
        self.period = period_seconds
        self._lock = threading.Lock()
        self._timestamps: list[float] = []

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._timestamps = [t for t in self._timestamps if now - t < self.period]
            if len(self._timestamps) >= self.max_calls:
                sleep_for = self.period - (now - self._timestamps[0])
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.monotonic()
                self._timestamps = [t for t in self._timestamps if now - t < self.period]
            self._timestamps.append(now)


# Conservative vs. SEC's documented 10 req/sec ceiling
SEC_EDGAR_RATE_LIMITER = RateLimiter(max_calls=5, period_seconds=1.0)
# NewsAPI free tier / most free news APIs: ~50-100 req/day, throttle hard
NEWS_API_RATE_LIMITER = RateLimiter(max_calls=1, period_seconds=1.0)


# --------------------------------------------------------------------------- #
# Simple in-memory TTL cache (swap for Redis in production; interface matches)
# --------------------------------------------------------------------------- #

class TTLCache:
    def __init__(self, ttl_seconds: float = 3600):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            ts, value = item
            if time.monotonic() - ts > self.ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), value)


# Separate caches per source so a slow news feed doesn't evict fresh filing data
FILING_CACHE = TTLCache(ttl_seconds=6 * 3600)      # filings change rarely intraday
PRICE_CACHE = TTLCache(ttl_seconds=15 * 60)         # quotes/stats, short TTL
TRANSCRIPT_CACHE = TTLCache(ttl_seconds=24 * 3600)  # transcripts are static once posted
NEWS_CACHE = TTLCache(ttl_seconds=30 * 60)
BSE_ANNOUNCEMENTS_CACHE = TTLCache(ttl_seconds=5 * 60)  # 5 minutes cache for announcements



def safe_get(d: dict, key: str, default: Any = None) -> Any:
    """dict.get that also treats NaN as missing (yfinance loves returning NaN)."""
    val = d.get(key, default)
    try:
        import math
        if isinstance(val, float) and math.isnan(val):
            return default
    except TypeError:
        pass
    return val
