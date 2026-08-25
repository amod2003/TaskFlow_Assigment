from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings
from app.core.logging import logger

_redis_pool: ConnectionPool | None = None
_fallback_fake_redis = None


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
    """Returns a Redis client instance from the pool with seamless fallback."""
    global _fallback_fake_redis
    try:
        pool = get_redis_pool()
        client = aioredis.Redis(connection_pool=pool)
        # Test connection quickly
        await client.ping()
        return client
    except Exception:
        # Fallback to in-memory fake redis for seamless local dev without Docker
        if _fallback_fake_redis is None:
            import fakeredis.aioredis as fakeredis

            _fallback_fake_redis = fakeredis.FakeRedis(decode_responses=True)
            logger.info("Using in-memory Redis cache fallback for local development.")
        return _fallback_fake_redis


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding an async Redis client."""
    client = await get_redis_client()
    try:
        yield client
    finally:
        # Only close if it's not the shared fallback instance
        if client != _fallback_fake_redis:
            await client.aclose()


async def close_redis() -> None:
    """Closes Redis connection pool cleanly."""
    global _redis_pool, _fallback_fake_redis
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Closed Redis connection pool.")
    if _fallback_fake_redis is not None:
        await _fallback_fake_redis.aclose()
        _fallback_fake_redis = None
