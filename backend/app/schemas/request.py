from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class EmailTriageRequest(BaseModel):
    subject: str | None = None
    body: str = Field(..., min_length=1)
    force_reflection: bool = False
    max_reflections: int = Field(default=2, ge=0, le=2)


class AddDocumentRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


# ── New email agent request schemas ───────────────────────────────────────────

class FetchEmailsRequest(BaseModel):
    """Trigger an IMAP fetch. max_emails overrides INITIAL_FETCH_COUNT if provided."""
    max_emails: int | None = Field(default=None, ge=1, le=500)


class QueryRequest(BaseModel):
    """Natural language query against the fetched email store."""
    query: str = Field(..., min_length=3, max_length=500)


class BulkDraftRequest(BaseModel):
    """Generate draft responses for the N most recent fetched emails."""
    count: int = Field(default=3, ge=1, le=20)


class DraftFeedbackRequest(BaseModel):
    """User feedback on a draft that triggers a redraft of that specific email."""
    feedback: str = Field(..., min_length=5, max_length=2000)


class DraftEditRequest(BaseModel):
    """Direct user edit of a draft's content — auto-approved on save."""
    content: str = Field(..., min_length=1, max_length=10000)


class FollowUpStatusRequest(BaseModel):
    """Update a follow-up's status."""
    status: str = Field(..., pattern="^(pending|snoozed|done)$")


class ManualFollowUpRequest(BaseModel):
    """Manually create a follow-up for a fetched email."""
    due_date: str | None = Field(default=None, description="ISO 8601 date, e.g. 2025-03-15")
    reminder_text: str = Field(..., min_length=5, max_length=500)
