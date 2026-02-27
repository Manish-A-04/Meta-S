import redis.asyncio as redis
from app.core.config import get_settings
from app.core.logger import logger

_redis_client: redis.Redis | None = None
_available: bool = False


async def connect_redis():
    global _redis_client, _available
    try:
        settings = get_settings()
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis_client.ping()
        _available = True
        logger.info("Redis connected")
    except Exception as e:
        _available = False
        logger.warning(f"Redis unavailable, running without cache: {e}")


async def disconnect_redis():
    global _redis_client, _available
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        _available = False
        logger.info("Redis disconnected")


async def cache_get(key: str) -> str | None:
    if not _available or not _redis_client:
        return None
    try:
        return await _redis_client.get(key)
    except Exception:
        return None


async def cache_set(key: str, value: str, ttl: int = 300):
    if not _available or not _redis_client:
        return
    try:
        await _redis_client.set(key, value, ex=ttl)
    except Exception:
        pass


def is_available() -> bool:
    return _available
