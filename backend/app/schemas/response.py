import uuid
from datetime import datetime
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
