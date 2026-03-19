import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UsageInfo(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int


class EmailTriageResponse(BaseModel):
    email_id: uuid.UUID
    classification: str
    final_draft: str
    reflection_count: int
    reflection_scores: list[int]
    approved: bool
    usage: UsageInfo


class DraftItem(BaseModel):
    version: int
    content: str
    reflection_score: int | None
    approved: bool
    created_at: datetime


class DraftHistoryResponse(BaseModel):
    email_id: uuid.UUID
    drafts: list[DraftItem]


class MetricsResponse(BaseModel):
    total_emails_processed: int
    average_reflection_count: float
    average_latency_ms: float
    average_tokens_per_email: float
    approval_rate: float


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    vector_store_status: str
    uptime_seconds: int


class DocumentResponse(BaseModel):
    document_id: uuid.UUID
    title: str
    created_at: datetime


class DocumentAddResponse(BaseModel):
    document_id: uuid.UUID
    embedding_id: str
    created_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class ErrorDetail(BaseModel):
    code: int
    message: str
    details: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ── New email agent response schemas ──────────────────────────────────────────

class FetchEmailsResponse(BaseModel):
    fetched: int          # Total emails checked from server
    stored: int           # Newly stored emails
    skipped: int          # Duplicates skipped (already in DB)
    message: str


class FetchedEmailItem(BaseModel):
    id: uuid.UUID
    sender_email: str
    sender_name: str | None
    subject: str | None
    received_at: datetime | None
    priority_label: str
    priority_score: int
    priority_reason: str | None
    is_indexed: bool


class FetchedEmailsListResponse(BaseModel):
    total: int
    emails: list[FetchedEmailItem]


class QueryResponse(BaseModel):
    query: str
    answer: str
    intent: dict[str, Any]
    result_count: int
    latency_ms: int
    emails: list[FetchedEmailItem]


class DraftBlock(BaseModel):
    """One draft block in a bulk draft response — one per email."""
    draft_id: uuid.UUID | None
    fetched_email_id: uuid.UUID
    sender: str
    subject: str
    received_at: str | None
    priority_label: str
    priority_score: int
    draft_content: str
    version: int
    status: str
    error: str | None = None


class BulkDraftResponse(BaseModel):
    total: int
    drafts: list[DraftBlock]


class DraftFeedbackResponse(BaseModel):
    draft_id: uuid.UUID
    fetched_email_id: uuid.UUID
    version: int
    draft_content: str
    status: str
    previous_version: int
    feedback_applied: str


class DraftEditResponse(BaseModel):
    draft_id: uuid.UUID
    version: int
    draft_content: str
    status: str


class InboxDraftItem(BaseModel):
    id: uuid.UUID
    fetched_email_id: uuid.UUID
    version: int
    content: str
    feedback: str | None
    status: str
    created_at: datetime


class PriorityEmailItem(BaseModel):
    id: uuid.UUID
    sender_email: str
    sender_name: str | None
    subject: str | None
    body_excerpt: str
    received_at: datetime | None
    priority_score: int
    priority_label: str
    priority_reason: str | None


class PriorityEmailsResponse(BaseModel):
    total: int
    emails: list[PriorityEmailItem]


class FollowUpItem(BaseModel):
    followup_id: str
    fetched_email_id: str
    sender: str
    subject: str | None
    reminder: str | None
    due_date: str | None
    is_overdue: bool
    status: str


class FollowUpListResponse(BaseModel):
    total: int
    followups: list[FollowUpItem]


class FollowUpStatusResponse(BaseModel):
    followup_id: str
    status: str


class ThreadSummaryResponse(BaseModel):
    thread_id: str
    email_count: int
    participants: list[str]
    date_range: dict[str, str | None]
    summary: str
    emails: list[dict]


class DigestStatsItem(BaseModel):
    emails_today: int
    pending_drafts: int
    urgent_count: int
    followup_count: int


class DigestResponse(BaseModel):
    date: str
    generated_at: str
    ai_briefing: str
    stats: DigestStatsItem
    urgent_emails: list[dict]
    pending_followups: list[dict]
    emails_needing_response: list[dict]


class AnalyticsResponse(BaseModel):
    generated_at: str
    total_emails: int
    emails_last_7_days: int
    volume_by_day: dict[str, int]
    top_senders: list[dict]
    priority_distribution: dict[str, int]
    draft_stats: dict[str, Any]
    busiest_hours: list[dict]
    total_nl_queries: int


class IndexingResponse(BaseModel):
    indexed: int
    message: str


class PriorityRefreshResponse(BaseModel):
    updated: int
    message: str
