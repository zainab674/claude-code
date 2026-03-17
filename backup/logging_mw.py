"""
Request logging middleware.
Logs every request with method, path, status, duration, and user.
"""
import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("payrollos.access")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        path = request.url.path

        # Extract user email from JWT for logging (best-effort, no validation here)
        user_email = "anon"
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                from jose import jwt as _jwt
                from config import settings
                payload = _jwt.decode(
                    auth[7:], settings.JWT_SECRET,
                    algorithms=[settings.JWT_ALGORITHM],
                    options={"verify_exp": False},
                )
                user_email = payload.get("email", "anon")
            except Exception:
                pass

        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            level,
            "%s %s %s %.1fms [%s]",
            request.method,
            path,
            response.status_code,
            duration_ms,
            user_email,
        )
        return response
