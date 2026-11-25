"""
API Key authentication (tiêu chí 6).
"""
import hmac
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Validate X-API-Key header against AGENT_API_KEY using constant-time comparison."""
    expected = settings.agent_api_key
    if not expected or not api_key or not hmac.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
