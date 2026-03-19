"""
META-S API Routes
─────────────────────────────────────────────────────────────────────────────
All API endpoints — original triage + comprehensive new email agent features.
"""

import uuid
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.api.deps import get_db, get_current_user, apply_rate_limit
from app.db.models import (
    User, Email, Draft, AgentLog, RagDocument,
    FetchedEmail, InboxDraft, FollowUpTracker,
)
from app.schemas.request import (
    RegisterRequest, LoginRequest, EmailTriageRequest, AddDocumentRequest,
    FetchEmailsRequest, QueryRequest, BulkDraftRequest,
    DraftFeedbackRequest, DraftEditRequest,
    FollowUpStatusRequest, ManualFollowUpRequest,
)
from app.schemas.response import (
    RegisterResponse, LoginResponse, EmailTriageResponse, UsageInfo,
    DraftHistoryResponse, DraftItem, MetricsResponse, HealthResponse,
    DocumentAddResponse, DocumentListResponse, DocumentResponse,
    FetchEmailsResponse, FetchedEmailItem, FetchedEmailsListResponse,
    QueryResponse, DraftBlock, BulkDraftResponse,
    DraftFeedbackResponse, DraftEditResponse, InboxDraftItem,
    PriorityEmailItem, PriorityEmailsResponse,
    FollowUpItem, FollowUpListResponse, FollowUpStatusResponse,
    ThreadSummaryResponse, DigestResponse, AnalyticsResponse,
    IndexingResponse, PriorityRefreshResponse,
)
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.core.config import get_settings
from app.services.email_service import process_email
from app.services.imap_service import fetch_and_store_emails
from app.services.query_service import execute_nl_query
from app.services.bulk_draft_service import (
    generate_bulk_drafts, redraft_with_feedback,
    approve_draft, edit_draft_directly,
)
from app.services import priority_service, thread_service, followup_service, digest_service, analytics_service
from app.rag.vector_store import add_document
from app.rag.email_vector_store import index_unindexed_emails
from app.llm.model_loader import is_loaded
from app.cache import redis_client
from app.core.logger import logger

router = APIRouter()
_start_time = time.time()


# ════════════════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════════════════

@router.post("/auth/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=req.email, password_hash=hash_password(req.password))
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


# ════════════════════════════════════════════════════════════════════════════
# EMAIL TRIAGE (original pipeline)
# ════════════════════════════════════════════════════════════════════════════

@router.post("/emails/triage", response_model=EmailTriageResponse, dependencies=[Depends(apply_rate_limit)])
async def triage_email(
    req: EmailTriageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await process_email(
            db=db, user_id=current_user.id,
            subject=req.subject, body=req.body,
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
                version=d.version, content=d.content,
                reflection_score=d.reflection_score,
                approved=d.approved, created_at=d.created_at,
            )
            for d in drafts
        ],
    )


# ════════════════════════════════════════════════════════════════════════════
# IMAP FETCH
# ════════════════════════════════════════════════════════════════════════════

@router.post("/emails/fetch", response_model=FetchEmailsResponse, dependencies=[Depends(apply_rate_limit)])
async def fetch_emails(
    req: FetchEmailsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger IMAP email fetch. Only pulls emails NOT already in the database
    (deduplicates by RFC-2822 Message-ID). Then indexes new embeddings and
    runs priority scoring on all unscored emails.
    """
    try:
        result = await fetch_and_store_emails(
            db=db,
            user_id=current_user.id,
            max_emails=req.max_emails,
            incremental=True,
        )
        # Index embeddings for newly fetched emails
        indexed = await index_unindexed_emails(db)
        # Score unscored emails
        scored = await priority_service.batch_score_emails(db)

        return FetchEmailsResponse(
            fetched=result["fetched"],
            stored=result["stored"],
            skipped=result["skipped"],
            message=(
                f"Fetched {result['stored']} new emails "
                f"(skipped {result['skipped']} already in DB). "
                f"Indexed {indexed} embeddings, scored {scored} emails."
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"IMAP fetch failed: {e}")
        raise HTTPException(status_code=500, detail=f"IMAP fetch failed: {str(e)}")


@router.get("/emails/fetched", response_model=FetchedEmailsListResponse, dependencies=[Depends(apply_rate_limit)])
async def list_fetched_emails(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sender: str | None = Query(default=None, description="Filter by sender email (partial match)"),
    priority: str | None = Query(default=None, description="Filter by priority label: CRITICAL|HIGH|MEDIUM|LOW"),
    days: int | None = Query(default=None, ge=1, le=365, description="Only emails from last N days"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List fetched emails with optional filtering by sender, priority, and date range."""
    from sqlalchemy import and_
    from datetime import timedelta
    conditions = [FetchedEmail.user_id == current_user.id]
    if sender:
        conditions.append(FetchedEmail.sender_email.ilike(f"%{sender}%"))
    if priority:
        conditions.append(FetchedEmail.priority_label == priority.upper())
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        conditions.append(FetchedEmail.received_at >= cutoff)

    result = await db.execute(
        select(FetchedEmail)
        .where(and_(*conditions))
        .order_by(desc(FetchedEmail.received_at))
        .limit(limit)
    )
    emails = result.scalars().all()
    return FetchedEmailsListResponse(
        total=len(emails),
        emails=[
            FetchedEmailItem(
                id=e.id, sender_email=e.sender_email, sender_name=e.sender_name,
                subject=e.subject, received_at=e.received_at,
                priority_label=e.priority_label, priority_score=e.priority_score,
                priority_reason=e.priority_reason, is_indexed=e.is_indexed,
            )
            for e in emails
        ],
    )


# ════════════════════════════════════════════════════════════════════════════
# NATURAL LANGUAGE QUERY
# ════════════════════════════════════════════════════════════════════════════

@router.post("/query", response_model=QueryResponse, dependencies=[Depends(apply_rate_limit)])
async def nl_query(
    req: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ask anything about your emails in plain English.
    Examples:
      - "Show me all emails from the last 5 days"
      - "What was the last email from alice@example.com?"
      - "List urgent emails about the project deadline"
      - "Did anyone email me about the meeting today?"
    """
    try:
        result = await execute_nl_query(db=db, user_id=current_user.id, query=req.query)
        return QueryResponse(
            query=req.query,
            answer=result["answer"],
            intent=result["intent"],
            result_count=result["result_count"],
            latency_ms=result["latency_ms"],
            emails=[
                FetchedEmailItem(
                    id=e.id, sender_email=e.sender_email, sender_name=e.sender_name,
                    subject=e.subject, received_at=e.received_at,
                    priority_label=e.priority_label, priority_score=e.priority_score,
                    priority_reason=e.priority_reason, is_indexed=e.is_indexed,
                )
                for e in result["emails"]
            ],
        )
    except Exception as e:
        logger.error(f"NL query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# BULK DRAFT GENERATION + FEEDBACK LOOP
# ════════════════════════════════════════════════════════════════════════════

@router.post("/emails/bulk-draft", response_model=BulkDraftResponse, dependencies=[Depends(apply_rate_limit)])
async def bulk_draft(
    req: BulkDraftRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate draft responses for the N most recent fetched emails.
    Returns one DraftBlock per email. Each draft is independent.
    Use POST /drafts/{draft_id}/feedback to refine a specific draft.
    """
    try:
        draft_blocks = await generate_bulk_drafts(db=db, user_id=current_user.id, count=req.count)
        return BulkDraftResponse(
            total=len(draft_blocks),
            drafts=[
                DraftBlock(
                    draft_id=b["draft_id"],
                    fetched_email_id=b["fetched_email_id"],
                    sender=b["sender"],
                    subject=b["subject"],
                    received_at=b.get("received_at"),
                    priority_label=b.get("priority_label", "LOW"),
                    priority_score=b.get("priority_score", 0),
                    draft_content=b["draft_content"],
                    version=b["version"],
                    status=b["status"],
                    error=b.get("error"),
                )
                for b in draft_blocks
            ],
        )
    except Exception as e:
        logger.error(f"Bulk draft failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk draft failed: {str(e)}")


@router.post("/drafts/{draft_id}/feedback", response_model=DraftFeedbackResponse, dependencies=[Depends(apply_rate_limit)])
async def submit_draft_feedback(
    draft_id: uuid.UUID,
    req: DraftFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit feedback on a specific draft. The agent will redraft ONLY this email
    incorporating your feedback. Previous version is preserved in history.
    """
    try:
        result = await redraft_with_feedback(db=db, draft_id=draft_id, feedback=req.feedback)
        return DraftFeedbackResponse(
            draft_id=result["draft_id"],
            fetched_email_id=result["fetched_email_id"],
            version=result["version"],
            draft_content=result["draft_content"],
            status=result["status"],
            previous_version=result["previous_version"],
            feedback_applied=result["feedback_applied"],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/drafts/{draft_id}", response_model=DraftEditResponse, dependencies=[Depends(apply_rate_limit)])
async def edit_draft(
    draft_id: uuid.UUID,
    req: DraftEditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Directly edit a draft's content. Auto-saved as an approved new version."""
    try:
        result = await edit_draft_directly(db=db, draft_id=draft_id, new_content=req.content)
        return DraftEditResponse(
            draft_id=result["draft_id"],
            version=result["version"],
            draft_content=result["draft_content"],
            status=result["status"],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/drafts/{draft_id}/approve", dependencies=[Depends(apply_rate_limit)])
async def approve_draft_endpoint(
    draft_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a draft as approved."""
    try:
        result = await approve_draft(db=db, draft_id=draft_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ════════════════════════════════════════════════════════════════════════════
# PRIORITY
# ════════════════════════════════════════════════════════════════════════════

@router.get("/emails/priority", response_model=PriorityEmailsResponse, dependencies=[Depends(apply_rate_limit)])
async def get_priority_emails(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    label: str | None = Query(default=None, description="Filter: CRITICAL|HIGH|MEDIUM|LOW"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Get emails ranked by priority score. Optionally filter by priority label."""
    from sqlalchemy import and_
    conditions = [FetchedEmail.user_id == current_user.id]
    if label:
        conditions.append(FetchedEmail.priority_label == label.upper())

    result = await db.execute(
        select(FetchedEmail)
        .where(and_(*conditions))
        .order_by(desc(FetchedEmail.priority_score))
        .limit(limit)
    )
    emails = result.scalars().all()
    return PriorityEmailsResponse(
        total=len(emails),
        emails=[
            PriorityEmailItem(
                id=e.id, sender_email=e.sender_email, sender_name=e.sender_name,
                subject=e.subject, body_excerpt=e.body[:200],
                received_at=e.received_at,
                priority_score=e.priority_score, priority_label=e.priority_label,
                priority_reason=e.priority_reason,
            )
            for e in emails
        ],
    )


@router.post("/emails/priority/refresh", response_model=PriorityRefreshResponse, dependencies=[Depends(apply_rate_limit)])
async def refresh_priority(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-score ALL fetched emails with the priority engine."""
    try:
        updated = await priority_service.refresh_all_scores(db)
        return PriorityRefreshResponse(updated=updated, message=f"Re-scored {updated} emails")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emails/index", response_model=IndexingResponse, dependencies=[Depends(apply_rate_limit)])
async def index_emails(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate embeddings for all unindexed fetched emails."""
    try:
        indexed = await index_unindexed_emails(db)
        return IndexingResponse(indexed=indexed, message=f"Indexed {indexed} emails")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════════════════════
# THREAD SUMMARIZER
# ════════════════════════════════════════════════════════════════════════════

@router.get("/emails/threads/{thread_id}", response_model=ThreadSummaryResponse, dependencies=[Depends(apply_rate_limit)])
async def get_thread_summary(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Summarize an email conversation thread by its thread_id."""
    try:
        result = await thread_service.summarize_thread(db, thread_id)
        return ThreadSummaryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════════════════════
# FOLLOW-UP TRACKER
# ════════════════════════════════════════════════════════════════════════════

@router.get("/followups", response_model=FollowUpListResponse, dependencies=[Depends(apply_rate_limit)])
async def get_followups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all pending follow-ups for the current user."""
    items = await followup_service.get_pending_followups(db, current_user.id)
    return FollowUpListResponse(total=len(items), followups=[FollowUpItem(**i) for i in items])


@router.post("/followups/detect", dependencies=[Depends(apply_rate_limit)])
async def auto_detect_followups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auto-detect follow-up requirements from HIGH and CRITICAL priority emails."""
    try:
        created = await followup_service.auto_detect_followups(db)
        return {"created": created, "message": f"Created {created} follow-up records"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/followups/{email_id}", dependencies=[Depends(apply_rate_limit)])
async def create_manual_followup(
    email_id: uuid.UUID,
    req: ManualFollowUpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually create a follow-up for a specific fetched email."""
    due_date = None
    if req.due_date:
        try:
            due_date = datetime.fromisoformat(req.due_date).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid due_date format. Use YYYY-MM-DD")
    fu = await followup_service.create_followup(db, email_id, due_date, req.reminder_text)
    return {"followup_id": str(fu.id), "status": fu.status}


@router.patch("/followups/{followup_id}/status", response_model=FollowUpStatusResponse, dependencies=[Depends(apply_rate_limit)])
async def update_followup_status(
    followup_id: uuid.UUID,
    req: FollowUpStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a follow-up status: pending | snoozed | done."""
    try:
        result = await followup_service.update_followup_status(db, followup_id, req.status)
        return FollowUpStatusResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ════════════════════════════════════════════════════════════════════════════
# DAILY DIGEST
# ════════════════════════════════════════════════════════════════════════════

@router.get("/digest", response_model=DigestResponse, dependencies=[Depends(apply_rate_limit)])
async def get_digest(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a smart daily email digest with AI briefing."""
    try:
        result = await digest_service.generate_digest(db, current_user.id)
        return DigestResponse(**result)
    except Exception as e:
        logger.error(f"Digest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ════════════════════════════════════════════════════════════════════════════

@router.get("/analytics", response_model=AnalyticsResponse, dependencies=[Depends(apply_rate_limit)])
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Email analytics dashboard data: volume, senders, priority distribution, draft stats."""
    try:
        result = await analytics_service.get_email_analytics(db, current_user.id)
        return AnalyticsResponse(**result)
    except Exception as e:
        logger.error(f"Analytics failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════════════════════
# RAG DOCUMENTS (original)
# ════════════════════════════════════════════════════════════════════════════

@router.post("/rag/documents", response_model=DocumentAddResponse, dependencies=[Depends(apply_rate_limit)])
async def add_rag_document(
    req: AddDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        doc = await add_document(db, req.title, req.content)
        return DocumentAddResponse(document_id=doc.id, embedding_id=str(doc.id), created_at=doc.created_at)
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
        documents=[DocumentResponse(document_id=d.id, title=d.title, created_at=d.created_at) for d in docs]
    )


# ════════════════════════════════════════════════════════════════════════════
# METRICS & HEALTH (original)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/metrics", response_model=MetricsResponse, dependencies=[Depends(apply_rate_limit)])
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total_result = await db.execute(
        select(func.count()).select_from(Email).where(Email.status == "processed")
    )
    total_emails = total_result.scalar() or 0
    avg_reflection_result = await db.execute(select(func.avg(Draft.version)).select_from(Draft))
    avg_reflection = avg_reflection_result.scalar() or 0.0
    avg_latency_result = await db.execute(select(func.avg(AgentLog.latency_ms)).select_from(AgentLog))
    avg_latency = avg_latency_result.scalar() or 0.0
    avg_tokens_result = await db.execute(
        select(func.avg(AgentLog.input_tokens + AgentLog.output_tokens)).select_from(AgentLog)
    )
    avg_tokens = avg_tokens_result.scalar() or 0.0
    approved_result = await db.execute(
        select(func.count()).select_from(Draft).where(Draft.approved == True)  # noqa: E712
    )
    approved_count = approved_result.scalar() or 0
    total_drafts_result = await db.execute(select(func.count()).select_from(Draft))
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
    uptime = int(time.time() - _start_time)
    return HealthResponse(
        status="ok",
        model_loaded=model_loaded,
        vector_store_status="healthy",
        uptime_seconds=uptime,
    )
