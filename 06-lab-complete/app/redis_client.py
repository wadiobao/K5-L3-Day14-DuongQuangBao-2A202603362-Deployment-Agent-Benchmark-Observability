"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import logging
import redis

from app.config import settings

logger = logging.getLogger(__name__)


def _create_client() -> redis.Redis | None:
    """Create Redis client lazily without pinging at import time."""
    if not settings.redis_url:
        return None
    try:
        return redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    except Exception as exc:
        logger.warning("Failed to initialize Redis client: %s", exc)
        return None


r: redis.Redis | None = _create_client()


def redis_healthy() -> bool:
    """Ping Redis to verify connectivity for /ready endpoint."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False
