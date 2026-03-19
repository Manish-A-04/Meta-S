import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, DateTime, Float, ARRAY, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    emails: Mapped[list["Email"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    fetched_emails: Mapped[list["FetchedEmail"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="emails")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="email", cascade="all, delete-orphan")
    agent_logs: Mapped[list["AgentLog"]] = relationship(back_populates="email", cascade="all, delete-orphan")


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reflection_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    email: Mapped["Email"] = relationship(back_populates="drafts")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    email: Mapped["Email"] = relationship(back_populates="agent_logs")


class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(ARRAY(Float), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── New tables for comprehensive email agent ────────────────────────────────────

class FetchedEmail(Base):
    """Emails pulled directly from the user's IMAP mail server. Deduplicated by message_id."""
    __tablename__ = "fetched_emails"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # RFC 2822 Message-ID header — globally unique, used for deduplication (never re-fetched)
    message_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    sender_email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    sender_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    # Priority fields populated by priority_service after fetch
    priority_score: Mapped[int] = mapped_column(Integer, default=0)
    priority_label: Mapped[str] = mapped_column(String(20), default="LOW")  # CRITICAL / HIGH / MEDIUM / LOW
    priority_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SentenceTransformer embedding for semantic search (CPU-side cosine similarity)
    embedding = mapped_column(ARRAY(Float), nullable=True)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="fetched_emails")
    inbox_drafts: Mapped[list["InboxDraft"]] = relationship(back_populates="fetched_email", cascade="all, delete-orphan")
    follow_ups: Mapped[list["FollowUpTracker"]] = relationship(back_populates="fetched_email", cascade="all, delete-orphan")


class InboxDraft(Base):
    """Draft responses generated for fetched emails. Supports per-draft feedback → redraft loop."""
    __tablename__ = "inbox_drafts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fetched_email_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fetched_emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)   # User feedback driving redraft
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | editing
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    fetched_email: Mapped["FetchedEmail"] = relationship(back_populates="inbox_drafts")


class EmailQueryLog(Base):
    """Audit log for every natural-language query — enables analytics and debugging."""
    __tablename__ = "email_query_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_intent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FollowUpTracker(Base):
    """Tracks emails that need a follow-up reply by a specific deadline."""
    __tablename__ = "follow_up_tracker"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fetched_email_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fetched_emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | snoozed | done
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    fetched_email: Mapped["FetchedEmail"] = relationship(back_populates="follow_ups")
