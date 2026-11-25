"""
Rate limiting (tiêu chí 7) — sliding window 60s backed by Redis sorted set.
"""
import logging
import secrets
import time
from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)
WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Enforce RATE_LIMIT_PER_MINUTE per API key using a Redis sliding window."""
    if r is None:
        logger.warning("Redis unavailable; skipping rate limit check")
        return

    now = time.time()
    window_start = now - WINDOW_SECONDS
    redis_key = f"rate_limit:{key}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= settings.rate_limit_per_minute:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = WINDOW_SECONDS
            if oldest:
                retry_after = max(1, int(WINDOW_SECONDS - (now - oldest[0][1])) + 1)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{secrets.token_hex(4)}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS)
        pipe.execute()
    except HTTPException:
        raise
    except RedisError as exc:
        logger.warning("Redis error during rate limit check: %s", exc)
