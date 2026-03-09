import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.db.session import init_db, close_db
from app.llm.model_loader import check_model_available, close_client
from app.cache.redis_client import connect_redis, disconnect_redis
from app.core.config import get_settings
from app.core.logger import logger


async def _run_startup_email_pipeline() -> None:
    """
    Background task: fetch new emails → index embeddings → score priority → detect follow-ups.
    Only runs if IMAP_AUTO_LOAD_ON_STARTUP=True and credentials are configured.
    Runs after the server is ready so it doesn't block startup.
    """
    settings = get_settings()
    if not settings.IMAP_AUTO_LOAD_ON_STARTUP:
        logger.info(
            "[Startup] IMAP auto-load is OFF. "
            "Set IMAP_AUTO_LOAD_ON_STARTUP=True in .env or call POST /api/v1/emails/fetch manually."
        )
        return

    if not settings.IMAP_USER or not settings.IMAP_PASSWORD:
        logger.warning(
            "[Startup] IMAP credentials not configured — skipping auto-load. "
            "Add IMAP_USER and IMAP_PASSWORD to .env to enable automatic fetching."
        )
        return

    # Import here to avoid circular imports at module load time
    from app.db.session import async_session_factory
    from app.services.imap_service import fetch_and_store_emails
    from app.rag.email_vector_store import index_unindexed_emails
    from app.services import priority_service, followup_service

    # Use the first active user as the fetch owner — for multi-user scenarios,
    # extend this to iterate over all active users
    from sqlalchemy import select
    from app.db.models import User

    try:
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.is_active == True).limit(1))  # noqa: E712
            user = result.scalar_one_or_none()
            if not user:
                logger.warning("[Startup] No active users found — skipping IMAP auto-load")
                return

            logger.info(f"[Startup] Auto-loading emails for user: {user.email}")
            fetch_result = await fetch_and_store_emails(
                db=db, user_id=user.id, incremental=True
            )
            logger.info(f"[Startup] Fetch complete: {fetch_result}")

            indexed = await index_unindexed_emails(db)
            logger.info(f"[Startup] Indexed {indexed} email embeddings")

            scored = await priority_service.batch_score_emails(db)
            logger.info(f"[Startup] Scored {scored} emails")

            detected = await followup_service.auto_detect_followups(db)
            logger.info(f"[Startup] Auto-detected {detected} follow-ups")

            await db.commit()
    except Exception as e:
        logger.error(f"[Startup] Background email pipeline failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting META-S application")
    await init_db()
    await check_model_available()
    await connect_redis()
    logger.info("META-S application started — server is ready")

    # Launch email pipeline in background (non-blocking)
    asyncio.create_task(_run_startup_email_pipeline())

    yield

    logger.info("Shutting down META-S application")
    await close_client()
    await disconnect_redis()
    await close_db()
    logger.info("META-S application stopped")


app = FastAPI(
    title="META-S",
    description="Resource-Constrained Multi-Agent Email Intelligence System",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "details": str(exc),
            }
        },
    )


app.include_router(router, prefix="/api/v1")
