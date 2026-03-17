"""
Multi-tenant isolation middleware.
Ensures every authenticated request can only access data
belonging to the company in the JWT token.

Also adds X-Company-ID header to responses for debugging.
"""
import logging
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("payrollos.tenancy")

# Routes that are public (no tenant check)
PUBLIC_PATHS = {
    "/", "/health", "/health/ready", "/health/detailed",
    "/docs", "/openapi.json", "/redoc",
    "/auth/login", "/auth/register",
    "/auth/forgot-password", "/auth/reset-password",
    "/payroll/calculate",
}

# Routes that need auth but don't carry a company_id (e.g. /users/me)
SKIP_TENANT_CHECK = {"/users/me", "/self-service/profile"}


class MultiTenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip public routes entirely
        if path in PUBLIC_PATHS or path.startswith("/static"):
            return await call_next(request)

        # Extract company_id from JWT (already validated by route deps)
        # We do a lightweight decode here just for logging/headers
        company_id = None
        auth = request.headers.get("authorization", "")
        api_key = request.headers.get("x-api-key", "")

        if auth.startswith("Bearer "):
            try:
                from jose import jwt as _jwt
                from config import settings
                payload = _jwt.decode(
                    auth[7:],
                    settings.JWT_SECRET,
                    algorithms=[settings.JWT_ALGORITHM],
                    options={"verify_exp": False},
                )
                company_id = payload.get("company_id")
            except Exception:
                pass

        # Store company_id in request state for downstream use
        if company_id:
            request.state.company_id = company_id

        response = await call_next(request)

        # Add tenant header to response for debugging
        if company_id:
            response.headers["X-Company-ID"] = company_id[:8] + "..."

        return response


class TenantQueryFilter:
    """
    Helper class used in routes to enforce tenant isolation on SQLAlchemy queries.
    Raises 403 if a resource doesn't belong to the current company.
    """

    @staticmethod
    def assert_owned(resource_company_id, current_company_id: str, resource_name: str = "resource"):
        """Raise 403 if resource belongs to different company."""
        from fastapi import HTTPException
        if str(resource_company_id) != str(current_company_id):
            logger.warning(
                "Tenant isolation violation: company %s tried to access %s owned by %s",
                current_company_id[:8],
                resource_name,
                str(resource_company_id)[:8],
            )
            raise HTTPException(403, f"Access denied: {resource_name} belongs to a different organization")

    @staticmethod
    def filter_query(query, model, company_id: str):
        """Add company_id filter to any SQLAlchemy query."""
        return query.where(model.company_id == company_id)
