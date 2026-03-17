"""
Startup configuration validation.
Called during FastAPI lifespan — crashes the app on startup if critical
config is missing or insecure, rather than failing at runtime.
"""
import os
import sys
import logging
import inspect
from contextlib import asynccontextmanager
from config import settings

logger = logging.getLogger("payrollos.startup")

def patch_beanie_aggregation():
    """
    Motor 3.4+ changed aggregate() to return a cursor syncly, but Beanie 2.x awaits it.
    This patch detects if it's awaitable or not.
    """
    try:
        from beanie.odm.queries.aggregation import AggregationQuery
        
        original_get_cursor = AggregationQuery.get_cursor
        
        async def patched_get_cursor(self):
            # This is roughly what Beanie does, but with a check
            collection = self.document_model.get_pymongo_collection()
            cursor_or_coro = collection.aggregate(
                self.aggregation_pipeline, session=self.session, **self.pymongo_kwargs
            )
            if inspect.isawaitable(cursor_or_coro):
                return await cursor_or_coro
            return cursor_or_coro
            
        AggregationQuery.get_cursor = patched_get_cursor
        logger.info("  ✓ Applied Beanie aggregation monkey-patch for Motor 3.x")
    except Exception as e:
        logger.warning(f"Could not apply Beanie monkey-patch: {e}")

REQUIRED_IN_PRODUCTION = [
    ("MONGODB_URL", "MongoDB connection string"),
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
}

MINIMUM_JWT_SECRET_LENGTH = 32


def validate_config():
    env = os.getenv("APP_ENV", "development").lower()
    errors = []
    warnings = []

    # Check required variables
    for var, desc in REQUIRED_IN_PRODUCTION:
        val = getattr(settings, var, "")
        if not val or val == "change_this_in_production":
            if env == "production":
                errors.append(f"  ✗ {var} is not set ({desc})")
            else:
                warnings.append(f"  ⚠ {var} not set — using default (OK for development)")

    # Check insecure defaults
    for var, bad_values in INSECURE_DEFAULTS.items():
        val = getattr(settings, var, "")
        if val.lower() in [b.lower() for b in bad_values]:
            if env == "production":
                errors.append(f"  ✗ {var} is using an insecure default value")
            else:
                warnings.append(f"  ⚠ {var} is using an insecure default (change before deploying)")

    # JWT secret length
    jwt = settings.JWT_SECRET
    if jwt and len(jwt) < MINIMUM_JWT_SECRET_LENGTH:
        if env == "production":
            errors.append(f"  ✗ JWT_SECRET must be at least {MINIMUM_JWT_SECRET_LENGTH} characters")
        else:
            warnings.append(f"  ⚠ JWT_SECRET is too short ({len(jwt)} chars, need {MINIMUM_JWT_SECRET_LENGTH}+)")

    # SSN encryption key
    if not settings.SSN_ENCRYPTION_KEY:
        warnings.append("  ⚠ SSN_ENCRYPTION_KEY not set — SSNs will not be encrypted")


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
    patch_beanie_aggregation()
    validate_config()

    # Initialize Beanie database
    try:
        from database import init_db
        await init_db()
        logger.info("✓ MongoDB connection and Beanie models initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    logger.info("✓ PayrollOS ready")
    yield
    logger.info("PayrollOS shutting down...")
