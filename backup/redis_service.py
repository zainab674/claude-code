"""
Redis service — replaces in-memory rate limiter, reset tokens, and session cache.
Falls back gracefully to in-memory when Redis is not configured.

Set REDIS_URL in .env to enable: redis://localhost:6379/0
"""
import os
import time
import json
import hashlib
from typing import Optional, Any

REDIS_URL = os.getenv("REDIS_URL", "")

_redis_client = None
_memory_store: dict = {}        # fallback in-memory store
_memory_expiry: dict = {}       # key -> expiry timestamp


def _get_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not REDIS_URL:
        return None
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        return _redis_client
    except ImportError:
        return None
    except Exception:
        return None


# ── Generic get/set/delete/expire ─────────────────────────────

async def get(key: str) -> Optional[str]:
    client = _get_client()
    if client:
        try:
            return await client.get(key)
        except Exception:
            pass
    # Fallback
    exp = _memory_expiry.get(key)
    if exp and time.time() > exp:
        _memory_store.pop(key, None)
        _memory_expiry.pop(key, None)
        return None
    return _memory_store.get(key)


async def set(key: str, value: str, ttl_seconds: Optional[int] = None) -> bool:
    client = _get_client()
    if client:
        try:
            if ttl_seconds:
                await client.setex(key, ttl_seconds, value)
            else:
                await client.set(key, value)
            return True
        except Exception:
            pass
    # Fallback
    _memory_store[key] = value
    if ttl_seconds:
        _memory_expiry[key] = time.time() + ttl_seconds
    return True


async def delete(key: str) -> bool:
    client = _get_client()
    if client:
        try:
            await client.delete(key)
            return True
        except Exception:
            pass
    _memory_store.pop(key, None)
    _memory_expiry.pop(key, None)
    return True


async def exists(key: str) -> bool:
    return await get(key) is not None


async def set_json(key: str, data: Any, ttl_seconds: Optional[int] = None) -> bool:
    return await set(key, json.dumps(data), ttl_seconds)


async def get_json(key: str) -> Optional[Any]:
    val = await get(key)
    if val is None:
        return None
    try:
        return json.loads(val)
    except Exception:
        return None


# ── Rate limiter using Redis sorted sets ──────────────────────

async def rate_limit_check(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """
    Sliding window rate limiter using Redis sorted sets.
    Returns (allowed, retry_after_seconds).
    """
    client = _get_client()
    now = time.time()

    if client:
        try:
            pipe = client.pipeline()
            # Remove old entries outside window
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            # Count remaining in window
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {str(now): now})
            # Set key expiry
            pipe.expire(key, window_seconds + 1)
            results = await pipe.execute()
            count = results[1]

            if count >= limit:
                # Get oldest entry to calculate retry_after
                oldest = await client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(window_seconds - (now - oldest[0][1])) + 1
                else:
                    retry_after = window_seconds
                return False, retry_after
            return True, 0
        except Exception:
            pass

    # Fallback: simple in-memory sliding window
    wkey = f"rl:{key}"
    window = _memory_store.get(wkey, [])
    cutoff = now - window_seconds
    window = [t for t in window if t >= cutoff]

    if len(window) >= limit:
        retry_after = int(window_seconds - (now - min(window))) + 1
        return False, retry_after

    window.append(now)
    _memory_store[wkey] = window
    return True, 0


# ── Password reset tokens ──────────────────────────────────────

async def store_reset_token(token: str, user_id: str, ttl_seconds: int = 3600) -> bool:
    key = f"reset:{hashlib.sha256(token.encode()).hexdigest()}"
    return await set_json(key, {"user_id": user_id}, ttl_seconds)


async def consume_reset_token(token: str) -> Optional[str]:
    """Returns user_id if token is valid, deletes it (one-time use)."""
    key = f"reset:{hashlib.sha256(token.encode()).hexdigest()}"
    data = await get_json(key)
    if not data:
        return None
    await delete(key)
    return data.get("user_id")


# ── Session cache ──────────────────────────────────────────────

async def cache_user_session(user_id: str, payload: dict, ttl_seconds: int = 3600 * 8) -> bool:
    return await set_json(f"session:{user_id}", payload, ttl_seconds)


async def get_cached_session(user_id: str) -> Optional[dict]:
    return await get_json(f"session:{user_id}")


async def invalidate_session(user_id: str) -> bool:
    return await delete(f"session:{user_id}")


# ── Health check ───────────────────────────────────────────────

async def ping() -> dict:
    client = _get_client()
    if not client:
        return {"status": "fallback", "backend": "in-memory", "redis_url": bool(REDIS_URL)}
    try:
        t0 = time.perf_counter()
        await client.ping()
        latency = round((time.perf_counter() - t0) * 1000, 1)
        return {"status": "ok", "backend": "redis", "latency_ms": latency}
    except Exception as e:
        return {"status": "error", "error": str(e), "backend": "fallback"}
