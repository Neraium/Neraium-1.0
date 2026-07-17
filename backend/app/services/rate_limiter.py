from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque

_LOCK = threading.Lock()
_BUCKETS: dict[tuple[str, str], Deque[float]] = defaultdict(deque)
_BUCKET_WINDOWS: dict[tuple[str, str], int] = {}
_SWEEP_INTERVAL = 256
_MAX_BUCKETS_BEFORE_SWEEP = 10_000
_CALL_COUNT = 0


def _sweep_expired_buckets(now: float) -> None:
    for bucket_key, bucket in list(_BUCKETS.items()):
        cutoff = now - _BUCKET_WINDOWS.get(bucket_key, 1)
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if not bucket:
            _BUCKETS.pop(bucket_key, None)
            _BUCKET_WINDOWS.pop(bucket_key, None)


def consume_rate_limit(
    scope: str,
    key: str,
    *,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    global _CALL_COUNT
    now = time.monotonic()
    bucket_key = (str(scope or ""), str(key or ""))
    with _LOCK:
        _CALL_COUNT += 1
        if _CALL_COUNT % _SWEEP_INTERVAL == 0 or len(_BUCKETS) >= _MAX_BUCKETS_BEFORE_SWEEP:
            _sweep_expired_buckets(now)
        bucket = _BUCKETS[bucket_key]
        effective_window = max(int(window_seconds), 1)
        _BUCKET_WINDOWS[bucket_key] = effective_window
        cutoff = now - effective_window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= max(int(limit), 1):
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
        return True, 0


def reset_rate_limit(scope: str, key: str) -> None:
    bucket_key = (str(scope or ""), str(key or ""))
    with _LOCK:
        _BUCKETS.pop(bucket_key, None)
        _BUCKET_WINDOWS.pop(bucket_key, None)


def rate_limit_bucket_count() -> int:
    with _LOCK:
        return len(_BUCKETS)


def clear_rate_limits() -> None:
    global _CALL_COUNT
    with _LOCK:
        _BUCKETS.clear()
        _BUCKET_WINDOWS.clear()
        _CALL_COUNT = 0
