"""
API Authentication Module
Provides API key authentication via Bearer token.

If the WEBUI_API_KEY environment variable is not set, authentication is disabled
for backward compatibility.
"""
import os
import secrets
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


API_KEY = os.getenv("WEBUI_API_KEY", "")


def is_auth_enabled() -> bool:
    """Whether API authentication is enabled"""
    return bool(API_KEY)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware for API key authentication.
    Skips authentication for open paths (health check, frontend, docs).
    """

    OPEN_PATHS = {
        "/",
        "/api/health",
        "/api/env/check",
        "/api/config/platforms",
        "/api/config/options",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/feishu",
    }

    async def dispatch(self, request: Request, call_next):
        if not is_auth_enabled():
            return await call_next(request)

        path = request.url.path

        # Allow open paths without authentication
        if path in self.OPEN_PATHS:
            return await call_next(request)

        # Allow static file access
        if path.startswith(("/assets/", "/logos/", "/static/")):
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

        token = auth_header[7:]  # Strip "Bearer "
        if not secrets.compare_digest(token, API_KEY):
            raise HTTPException(status_code=401, detail="Invalid API key")

        return await call_next(request)
