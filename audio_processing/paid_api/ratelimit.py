"""
Fixed-window rate limits on the Django cache. Production needs a shared
cache (REDIS_URL) for the limits and the payment replay lock to hold across
workers; the local-memory cache only limits per process.
"""

import time

from django.core.cache import cache


def hit(bucket, key, limit, window=60):
    """
    Count one request for `key`. Returns (allowed, retry_after_seconds).
    """
    now = int(time.time())
    window_start = now - (now % window)
    cache_key = f"paid_api:rl:{bucket}:{key}:{window_start}"
    if cache.add(cache_key, 1, timeout=window + 5):
        count = 1
    else:
        try:
            count = cache.incr(cache_key)
        except ValueError:  # expired between add and incr
            cache.add(cache_key, 1, timeout=window + 5)
            count = 1
    if count > limit:
        return False, window_start + window - now
    return True, 0
