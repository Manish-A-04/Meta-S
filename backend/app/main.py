from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.db.session import init_db, close_db
from app.llm.model_loader import check_model_available, close_client
from app.cache.redis_client import connect_redis, disconnect_redis
from app.core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting META-S application")
    await init_db()
    await check_model_available()
    await connect_redis()
    logger.info("META-S application started")
    yield
    logger.info("Shutting down META-S application")
    await close_client()
    await disconnect_redis()
    await close_db()
    logger.info("META-S application stopped")


app = FastAPI(
    title="META-S",
    description="Resource-Constrained Multi-Agent Email Triage System",
    version="1.0.0",
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
