"""
Cost guard (tiêu chí 8) — track token-based LLM spend in Redis.
"""
import logging
from datetime import date
from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _daily_key() -> str:
    return f"cost:daily:{date.today().isoformat()}"


def check_budget() -> None:
    """Verify accumulated spend has not reached daily or monthly budget."""
    if r is None:
        logger.warning("Redis unavailable; skipping budget check")
        return

    try:
        raw_total = r.get(_daily_key())
        total = float(raw_total) if raw_total is not None else 0.0
        limit = min(settings.daily_budget_usd, settings.monthly_budget_usd)
        if total >= limit:
            raise HTTPException(status_code=402, detail="Budget exceeded")
    except HTTPException:
        raise
    except RedisError as exc:
        logger.warning("Redis error during budget check: %s", exc)


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Accumulate request LLM cost in Redis and return the request cost in USD."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    if r is None:
        return cost

    try:
        key = _daily_key()
        pipe = r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, 86400)
        pipe.execute()
    except RedisError as exc:
        logger.warning("Redis error recording cost: %s", exc)
    return cost
