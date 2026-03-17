"""
Rate limiting middleware — uses Redis when available, falls back to in-memory.
"""
import time
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

RATE_LIMITS = {
    "/auth/login":            (10, 60),
    "/auth/forgot-password":  (5, 60),
    "/auth/reset-password":   (10, 60),
    "/auth/register":         (5, 60),
    "/payroll/run":           (5, 60),
    "/payroll/preview":       (30, 60),
    "/payroll/calculate":     (30, 60),
    "/import/employees":      (10, 60),
    "/export/":               (20, 60),
    "default":                (120, 60),
}


def get_limit(path: str) -> tuple[int, int]:
    for pattern, limit in RATE_LIMITS.items():
        if pattern != "default" and path.startswith(pattern):
            return limit
    return RATE_LIMITS["default"]


def get_client_key(request: Request, path: str) -> str:
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.headers.get("x-real-ip", "")
        or (request.client.host if request.client else "unknown")
    )
    if path.startswith("/auth/") or path == "/payroll/calculate":
        return f"ip:{ip}:{path.split('?')[0]}"
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token_prefix = auth[7:27]
        return f"user:{token_prefix}:{path.split('?')[0]}"
    return f"ip:{ip}:{path.split('?')[0]}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path in ("/health", "/health/ready", "/", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        limit, window = get_limit(path)
        key = get_client_key(request, path)

        try:
            from services.redis_service import rate_limit_check
            allowed, retry_after = await rate_limit_check(key, limit, window)
        except Exception:
            allowed, retry_after = True, 0

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded. Retry in {retry_after}s.", "retry_after": retry_after},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Window"] = str(window)
        return response
