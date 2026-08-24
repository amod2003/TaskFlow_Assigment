import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis

router = APIRouter(tags=["Operational"])


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check probe for API, Database, and Redis",
)
async def health_check(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """
    Performs deep health check probing PostgreSQL database and Redis connectivity.
    Returns 200 OK if all dependencies are responsive, or 503 Service Unavailable if degraded.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "services": {},
    }
    is_healthy = True

    # 1. Probe PostgreSQL
    try:
        t0 = time.perf_counter()
        await db.execute(text("SELECT 1"))
        db_latency = round((time.perf_counter() - t0) * 1000, 2)
        health_status["services"]["postgres"] = {
            "status": "healthy",
            "latency_ms": db_latency,
        }
    except Exception as e:
        is_healthy = False
        health_status["services"]["postgres"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # 2. Probe Redis
    try:
        t0 = time.perf_counter()
        ping_res = await redis.ping()
        redis_latency = round((time.perf_counter() - t0) * 1000, 2)
        if ping_res:
            health_status["services"]["redis"] = {
                "status": "healthy",
                "latency_ms": redis_latency,
            }
        else:
            is_healthy = False
            health_status["services"]["redis"] = {
                "status": "unhealthy",
                "error": "PING failed",
            }
    except Exception as e:
        is_healthy = False
        health_status["services"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    if not is_healthy:
        health_status["status"] = "unhealthy"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return health_status
