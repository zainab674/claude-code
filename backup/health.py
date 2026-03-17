"""
Health monitoring endpoint.
GET /health          → basic ok/fail
GET /health/detailed → database ping, disk, memory, uptime, version

Used by load balancers, uptime monitors, and k8s readiness probes.
"""
import os
import time
import platform
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/health", tags=["health"])

_start_time = time.time()


@router.get("")
async def health_basic():
    """Minimal health check — returns 200 if the app is running."""
    return {"status": "ok", "service": "PayrollOS", "version": "1.0.0"}


@router.get("/ready")
async def health_ready(db: AsyncSession = Depends(get_db)):
    """Readiness probe — returns 200 only if DB is reachable."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(503, f"Database not ready: {e}")


@router.get("/detailed")
async def health_detailed(db: AsyncSession = Depends(get_db)):
    """Full health check with component status."""
    checks = {}
    overall = "healthy"

    # ── Database ──────────────────────────────────────────────
    try:
        t0 = time.perf_counter()
        await db.execute(text("SELECT 1"))
        db_ms = round((time.perf_counter() - t0) * 1000, 1)
        checks["database"] = {"status": "ok", "latency_ms": db_ms}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}
        overall = "degraded"

    # ── Disk space ────────────────────────────────────────────
    try:
        stat = os.statvfs("/")
        total_gb = stat.f_blocks * stat.f_frsize / 1e9
        free_gb = stat.f_bavail * stat.f_frsize / 1e9
        used_pct = round((1 - free_gb / total_gb) * 100, 1)
        disk_status = "warning" if used_pct > 85 else "ok"
        if used_pct > 95:
            disk_status = "critical"
            overall = "degraded"
        checks["disk"] = {
            "status": disk_status,
            "total_gb": round(total_gb, 1),
            "free_gb": round(free_gb, 1),
            "used_pct": used_pct,
        }
    except Exception as e:
        checks["disk"] = {"status": "unknown", "error": str(e)}

    # ── Memory ────────────────────────────────────────────────
    try:
        import resource
        mem_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux: bytes, macOS: bytes too (usually)
        mem_mb = round(mem_bytes / 1024 / 1024, 1)
        checks["memory"] = {"status": "ok", "rss_mb": mem_mb}
    except Exception:
        checks["memory"] = {"status": "unknown"}

    # ── Paystub storage ───────────────────────────────────────
    paystub_dir = os.getenv("PAYSTUB_DIR", "./paystubs")
    if os.path.exists(paystub_dir):
        count = len([f for f in os.listdir(paystub_dir) if f.endswith(".pdf")])
        checks["paystub_storage"] = {"status": "ok", "pdf_count": count, "path": paystub_dir}
    else:
        checks["paystub_storage"] = {"status": "warning", "error": "Directory not found"}

    uptime_s = int(time.time() - _start_time)
    uptime_str = f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m {uptime_s % 60}s"

    return {
        "status": overall,
        "version": "1.0.0",
        "uptime": uptime_str,
        "uptime_seconds": uptime_s,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "python": platform.python_version(),
        "os": platform.system(),
        "checks": checks,
    }
