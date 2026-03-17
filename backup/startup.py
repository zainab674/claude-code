"""
Startup configuration validation.
Called during FastAPI lifespan — crashes the app on startup if critical
config is missing or insecure, rather than failing at runtime.
"""
import os
import sys
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger("payrollos.startup")

REQUIRED_IN_PRODUCTION = [
    ("DATABASE_URL", "PostgreSQL connection string"),
    ("JWT_SECRET", "JWT signing secret"),
]

INSECURE_DEFAULTS = {
    "JWT_SECRET": [
        "change_this_to_a_long_random_string_in_production",
        "change_this_in_production",
        "super_secret_jwt_key",
        "secret",
        "changeme",
    ],
    "DB_PASSWORD": ["payroll_secret", "password", "postgres"],
}

MINIMUM_JWT_SECRET_LENGTH = 32


def validate_config():
    env = os.getenv("APP_ENV", "development").lower()
    errors = []
    warnings = []

    # Check required variables
    for var, desc in REQUIRED_IN_PRODUCTION:
        val = os.getenv(var, "")
        if not val:
            if env == "production":
                errors.append(f"  ✗ {var} is not set ({desc})")
            else:
                warnings.append(f"  ⚠ {var} not set — using default (OK for development)")

    # Check insecure defaults
    for var, bad_values in INSECURE_DEFAULTS.items():
        val = os.getenv(var, "")
        if val.lower() in [b.lower() for b in bad_values]:
            if env == "production":
                errors.append(f"  ✗ {var} is using an insecure default value")
            else:
                warnings.append(f"  ⚠ {var} is using an insecure default (change before deploying)")

    # JWT secret length
    jwt = os.getenv("JWT_SECRET", "")
    if jwt and len(jwt) < MINIMUM_JWT_SECRET_LENGTH:
        if env == "production":
            errors.append(f"  ✗ JWT_SECRET must be at least {MINIMUM_JWT_SECRET_LENGTH} characters")
        else:
            warnings.append(f"  ⚠ JWT_SECRET is too short ({len(jwt)} chars, need {MINIMUM_JWT_SECRET_LENGTH}+)")

    # SSN encryption key
    if not os.getenv("SSN_ENCRYPTION_KEY"):
        warnings.append("  ⚠ SSN_ENCRYPTION_KEY not set — SSNs will not be encrypted")

    # Redis
    if not os.getenv("REDIS_URL"):
        warnings.append("  ⚠ REDIS_URL not set — using in-memory fallback (not suitable for multi-instance)")

    # Report
    if warnings:
        logger.warning("Configuration warnings:\n" + "\n".join(warnings))

    if errors:
        logger.critical("FATAL: Configuration errors (fix before running in production):\n" + "\n".join(errors))
        if env == "production":
            sys.exit(1)
        else:
            logger.warning("Running in development mode despite config errors — would fail in production")

    logger.info(f"✓ Config validated (env={env})")
    return len(errors) == 0


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan — startup validation + cleanup."""
    logger.info("PayrollOS starting up...")
    validate_config()

    # Warm up database connection pool
    try:
        from database import engine
        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        logger.info("✓ Database connection pool ready")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

    # Redis ping
    try:
        from services.redis_service import ping
        result = await ping()
        logger.info(f"✓ Cache backend: {result['backend']} ({result.get('latency_ms', 'N/A')}ms)")
    except Exception as e:
        logger.warning(f"Cache backend unavailable: {e}")

    logger.info("✓ PayrollOS ready")
    yield
    logger.info("PayrollOS shutting down...")
