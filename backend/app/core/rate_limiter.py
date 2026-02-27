import time
from collections import defaultdict
from fastapi import HTTPException, Request
from app.core.config import get_settings


class RateLimiter:
    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str, window: int):
        now = time.time()
        self._requests[key] = [t for t in self._requests[key] if now - t < window]

    async def check(self, request: Request):
        settings = get_settings()
        client_ip = request.client.host if request.client else "unknown"
        key = client_ip
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        max_requests = settings.RATE_LIMIT_REQUESTS
        self._cleanup(key, window)
        if len(self._requests[key]) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {max_requests} requests per {window}s.",
            )
        self._requests[key].append(time.time())


rate_limiter = RateLimiter()
