import hashlib
import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger


class CacheService:
    """Service providing query caching and targeted cache invalidation for tasks."""

    KEY_PREFIX = "taskflow:cache"

    @classmethod
    def generate_task_cache_key(cls, user_id: int, filter_params: dict[str, Any]) -> str:
        """
        Generates a deterministic cache key based on user ID and sorted query parameters.
        Format: taskflow:cache:user:<user_id>:tasks:<hash>
        """
        # Filter out None values and convert all values to string for stable hashing
        cleaned_params = {
            k: str(v) for k, v in sorted(filter_params.items()) if v is not None and v != ""
        }
        serialized = json.dumps(cleaned_params, sort_keys=True)
        param_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return f"{cls.KEY_PREFIX}:user:{user_id}:tasks:{param_hash}"

    @classmethod
    async def get_cached_tasks(cls, redis_client: Redis, cache_key: str) -> dict[str, Any] | None:
        """Retrieve and deserialize cached tasks data. Returns None on cache miss or error."""
        try:
            raw_data = await redis_client.get(cache_key)
            if raw_data:
                return json.loads(raw_data)
        except Exception as e:
            logger.warning(f"Failed to read from cache key '{cache_key}': {e}")
        return None

    @classmethod
    async def set_cached_tasks(
        cls,
        redis_client: Redis,
        cache_key: str,
        data: dict[str, Any],
        ttl_seconds: int = settings.CACHE_TTL_SECONDS,
    ) -> bool:
        """Serialize and write tasks query result to Redis with TTL."""
        try:
            serialized = json.dumps(data, default=str)
            await redis_client.set(cache_key, serialized, ex=ttl_seconds)
            return True
        except Exception as e:
            logger.warning(f"Failed to set cache key '{cache_key}': {e}")
            return False

    @classmethod
    async def invalidate_user_tasks_cache(cls, redis_client: Redis, user_id: int) -> int:
        """
        Invalidates all cached task queries for a specific user.
        Ensures zero stale reads upon task creation, update, or deletion.
        """
        pattern = f"{cls.KEY_PREFIX}:user:{user_id}:tasks:*"
        try:
            keys = []
            async for key in redis_client.scan_iter(match=pattern, count=100):
                keys.append(key)

            if keys:
                deleted_count = await redis_client.delete(*keys)
                logger.info(
                    f"Invalidated {deleted_count} cached task queries for user_id={user_id}."
                )
                return deleted_count
            return 0
        except Exception as e:
            logger.warning(f"Failed to invalidate task cache for user_id={user_id}: {e}")
            return 0
