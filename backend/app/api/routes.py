import uuid
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.api.deps import get_db, get_current_user, apply_rate_limit
from app.db.models import User, Email, Draft, AgentLog, RagDocument
from app.schemas.request import RegisterRequest, LoginRequest, EmailTriageRequest, AddDocumentRequest
from app.schemas.response import (
    RegisterResponse, LoginResponse, EmailTriageResponse, UsageInfo,
    DraftHistoryResponse, DraftItem, MetricsResponse, HealthResponse,
    DocumentAddResponse, DocumentListResponse, DocumentResponse,
)
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.core.config import get_settings
from app.services.email_service import process_email
from app.rag.vector_store import add_document
from app.llm.model_loader import is_loaded
from app.cache import redis_client
from app.core.logger import logger

router = APIRouter()
_start_time = time.time()


@router.post("/auth/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.flush()
    return RegisterResponse(user_id=user.id, email=user.email, created_at=user.created_at)


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    settings = get_settings()
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/emails/triage", response_model=EmailTriageResponse, dependencies=[Depends(apply_rate_limit)])
async def triage_email(
    req: EmailTriageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await process_email(
            db=db,
            user_id=current_user.id,
            subject=req.subject,
            body=req.body,
            force_reflection=req.force_reflection,
            max_reflections=req.max_reflections,
        )
        return EmailTriageResponse(
            email_id=result["email_id"],
            classification=result["classification"],
            final_draft=result["final_draft"],
            reflection_count=result["reflection_count"],
            reflection_scores=result["reflection_scores"],
            approved=result["approved"],
            usage=UsageInfo(**result["usage"]),
        )
    except Exception as e:
        logger.error(f"Triage failed: {e}")
        raise HTTPException(status_code=500, detail=f"Email triage failed: {str(e)}")


@router.get("/emails/{email_id}/drafts", response_model=DraftHistoryResponse, dependencies=[Depends(apply_rate_limit)])
async def get_draft_history(
    email_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.user_id == current_user.id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    drafts_result = await db.execute(
        select(Draft).where(Draft.email_id == email_id).order_by(Draft.version)
    )
    drafts = drafts_result.scalars().all()
    return DraftHistoryResponse(
        email_id=email_id,
        drafts=[
            DraftItem(
                version=d.version,
                content=d.content,
                reflection_score=d.reflection_score,
                approved=d.approved,
                created_at=d.created_at,
            )
            for d in drafts
        ],
    )


@router.post("/rag/documents", response_model=DocumentAddResponse, dependencies=[Depends(apply_rate_limit)])
async def add_rag_document(
    req: AddDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        doc = await add_document(db, req.title, req.content)
        return DocumentAddResponse(
            document_id=doc.id,
            embedding_id=str(doc.id),
            created_at=doc.created_at,
        )
    except Exception as e:
        logger.error(f"Document add failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add document: {str(e)}")


@router.get("/rag/documents", response_model=DocumentListResponse, dependencies=[Depends(apply_rate_limit)])
async def list_rag_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(RagDocument).order_by(RagDocument.created_at.desc()))
    docs = result.scalars().all()
    return DocumentListResponse(
        documents=[
            DocumentResponse(document_id=d.id, title=d.title, created_at=d.created_at)
            for d in docs
        ],
    )


@router.get("/metrics", response_model=MetricsResponse, dependencies=[Depends(apply_rate_limit)])
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total_result = await db.execute(
        select(func.count()).select_from(Email).where(Email.status == "processed")
    )
    total_emails = total_result.scalar() or 0

    avg_reflection_result = await db.execute(
        select(func.avg(Draft.version)).select_from(Draft)
    )
    avg_reflection = avg_reflection_result.scalar() or 0.0

    avg_latency_result = await db.execute(
        select(func.avg(AgentLog.latency_ms)).select_from(AgentLog)
    )
    avg_latency = avg_latency_result.scalar() or 0.0

    avg_tokens_result = await db.execute(
        select(func.avg(AgentLog.input_tokens + AgentLog.output_tokens)).select_from(AgentLog)
    )
    avg_tokens = avg_tokens_result.scalar() or 0.0

    approved_result = await db.execute(
        select(func.count()).select_from(Draft).where(Draft.approved == True)
    )
    approved_count = approved_result.scalar() or 0
    total_drafts_result = await db.execute(
        select(func.count()).select_from(Draft)
    )
    total_drafts = total_drafts_result.scalar() or 1
    approval_rate = approved_count / total_drafts if total_drafts > 0 else 0.0

    return MetricsResponse(
        total_emails_processed=total_emails,
        average_reflection_count=float(avg_reflection),
        average_latency_ms=float(avg_latency),
        average_tokens_per_email=float(avg_tokens),
        approval_rate=float(approval_rate),
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    model_loaded = await is_loaded()
    vector_store_status = "healthy"
    uptime = int(time.time() - _start_time)
    return HealthResponse(
        status="ok",
        model_loaded=model_loaded,
        vector_store_status=vector_store_status,
        uptime_seconds=uptime,
    )
