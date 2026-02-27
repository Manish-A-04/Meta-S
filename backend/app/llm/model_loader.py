import httpx
import time
from app.core.config import get_settings
from app.core.logger import logger

_client: httpx.AsyncClient | None = None
_loaded: bool = False


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=120.0)
    return _client


async def check_model_available() -> bool:
    global _loaded
    try:
        settings = get_settings()
        client = await get_client()
        resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            _loaded = any(settings.OLLAMA_MODEL in name for name in model_names)
            return _loaded
        return False
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        return False


async def generate(prompt: str, system_prompt: str = "", max_tokens: int = 512) -> dict:
    settings = get_settings()
    client = await get_client()
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.7,
            "num_ctx": settings.MAX_CONTEXT_TOKENS,
        },
    }
    start = time.perf_counter()
    try:
        resp = await client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {
            "response": data.get("response", ""),
            "input_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
            "latency_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.error(f"Ollama generate failed: {e}")
        return {
            "response": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": elapsed_ms,
            "error": str(e),
        }


async def is_loaded() -> bool:
    global _loaded
    return _loaded


async def close_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None
