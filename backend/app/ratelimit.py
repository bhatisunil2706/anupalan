"""Fixed-window rate limiting and counters, shared through Redis (required in production).

Without REDIS_URL an in-process store is used, which is fine for development and tests but does not
coordinate between several API instances.
"""
import logging
import threading
import time
from functools import lru_cache

from fastapi import HTTPException, status

from app.config import get_settings

log = logging.getLogger("ratelimit")


class _MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def incr(self, key: str, window: int) -> int:
        now = time.monotonic()
        with self._lock:
            count, expires = self._data.get(key, (0, now + window))
            if now >= expires:
                count, expires = 0, now + window
            count += 1
            self._data[key] = (count, expires)
            return count

    def get(self, key: str) -> int:
        with self._lock:
            count, expires = self._data.get(key, (0, 0.0))
            return count if time.monotonic() < expires else 0

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class _RedisStore:
    def __init__(self, url: str) -> None:
        import redis

        self.r = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)

    def incr(self, key: str, window: int) -> int:
        pipe = self.r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window, nx=True)
        count, _ = pipe.execute()
        return int(count)

    def get(self, key: str) -> int:
        v = self.r.get(key)
        return int(v) if v else 0

    def delete(self, key: str) -> None:
        self.r.delete(key)

    def clear(self) -> None:  # tests only
        for k in self.r.scan_iter("rl:*"):
            self.r.delete(k)


@lru_cache
def store():
    url = get_settings().redis_url
    return _RedisStore(url) if url else _MemoryStore()


def hit(name: str, ident: str, limit: int, window_seconds: int) -> bool:
    """Count one event. Returns True if the caller is now over the limit."""
    try:
        return store().incr(f"rl:{name}:{ident}", window_seconds) > limit
    except Exception:  # noqa: BLE001 - a Redis outage must not take the app down; fail open but log loudly
        log.exception("rate limit store unavailable")
        return False


def increment(name: str, ident: str, window_seconds: int) -> int:
    try:
        return store().incr(f"rl:{name}:{ident}", window_seconds)
    except Exception:  # noqa: BLE001
        log.exception("rate limit store unavailable")
        return 0


def count(name: str, ident: str) -> int:
    try:
        return store().get(f"rl:{name}:{ident}")
    except Exception:  # noqa: BLE001
        return 0


def reset(name: str, ident: str) -> None:
    try:
        store().delete(f"rl:{name}:{ident}")
    except Exception:  # noqa: BLE001
        pass


def enforce(name: str, ident: str, limit: int, window_seconds: int, message: str = "") -> None:
    if hit(name, ident, limit, window_seconds):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            message or "Too many requests. Please wait a few minutes and try again.")
