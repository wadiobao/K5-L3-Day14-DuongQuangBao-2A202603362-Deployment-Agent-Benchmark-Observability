"""
Production AI Agent — Part 6 Final Project.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import time

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format every application log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            payload.update(record.extra_fields)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> logging.Logger:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    app_logger = logging.getLogger("agent")
    app_logger.setLevel(logging.INFO)
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    app_logger.propagate = False
    return app_logger


logger = _configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and graceful shutdown (SIGTERM) lifecycle."""
    logger.info(
        "agent_startup",
        extra={"extra_fields": {"event": "startup", "env": settings.environment}},
    )
    yield
    logger.info(
        "agent_shutdown",
        extra={"extra_fields": {"event": "shutdown", "env": settings.environment}},
    )
    if r is not None:
        try:
            r.close()
        except Exception:
            pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Emit structured JSON log for every HTTP request with latency."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "http_request",
        extra={
            "extra_fields": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Prevent leaking internal stack traces to API callers."""
    logger.error(
        "unhandled_error",
        extra={"extra_fields": {"event": "error", "path": request.url.path, "error": str(exc)}},
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.get("/health")
def health():
    """Liveness probe: always 200 when process is running."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness probe: 200 when Redis is reachable, 503 otherwise."""
    if redis_healthy():
        return {"status": "ready", "redis": "ok"}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "redis": "unavailable"},
    )


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    """Answer a question after API key auth, rate limiting, and budget checks."""
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    record_cost(input_tokens, output_tokens)

    return {"question": body.question, "answer": answer}
