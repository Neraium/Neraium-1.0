from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque

_LOCK = threading.Lock()
_BUCKETS: dict[tuple[str, str], Deque[float]] = defaultdict(deque)


def consume_rate_limit(scope: str, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
    now = time.monotonic()
    bucket_key = (str(scope or ""), str(key or ""))
    with _LOCK:
        bucket = _BUCKETS[bucket_key]
        cutoff = now - max(int(window_seconds), 1)
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


def clear_rate_limits() -> None:
    with _LOCK:
        _BUCKETS.clear()
