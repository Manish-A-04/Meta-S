from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/metas"

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    REDIS_URL: str = "redis://localhost:6379/0"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "phi3.5:3.8b"

    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    MAX_CONTEXT_TOKENS: int = 2048
    MAX_REFLECTION_LOOPS: int = 2

    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── IMAP Settings ──────────────────────────────────────────────────────────
    IMAP_HOST: str = "imap.gmail.com"
    IMAP_PORT: int = 993
    IMAP_USER: str = ""
    IMAP_PASSWORD: str = ""
    IMAP_MAILBOX: str = "INBOX"
    # Number of most-recent emails to fetch in the initial load
    INITIAL_FETCH_COUNT: int = 100
    # Max emails fetched per IMAP batch (Gmail: avoid large single fetches)
    IMAP_BATCH_SIZE: int = 50
    # Whether to automatically fetch emails on server startup.
    # Set to False to require a manual POST /emails/fetch trigger.
    IMAP_AUTO_LOAD_ON_STARTUP: bool = False

    # ── Priority Engine Thresholds ─────────────────────────────────────────────
    PRIORITY_CRITICAL_THRESHOLD: int = 90
    PRIORITY_HIGH_THRESHOLD: int = 70
    PRIORITY_MEDIUM_THRESHOLD: int = 40

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
