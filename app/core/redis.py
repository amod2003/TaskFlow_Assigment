from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings
from app.core.logging import logger

_redis_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    """Returns singleton Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=20,
            decode_responses=True,
        )
    return _redis_pool


async def get_redis_client() -> Redis:
    """Returns a Redis client instance from the pool."""
    pool = get_redis_pool()
    return aioredis.Redis(connection_pool=pool)


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding an async Redis client."""
    client = await get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


async def close_redis() -> None:
    """Closes Redis connection pool cleanly."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Closed Redis connection pool.")
