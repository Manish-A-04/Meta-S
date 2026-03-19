"""
Smart Daily Digest Service
──────────────────────────────────────────────────────────────────────────────
Generates a concise email briefing: CRITICAL + HIGH priority emails,
overdue follow-ups, old unread emails, and pending drafts count.
"""

import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.db.models import FetchedEmail, InboxDraft, FollowUpTracker
from app.llm.model_loader import generate
from app.llm.prompt_templates import DIGEST_SYSTEM, DIGEST_PROMPT
from app.llm.token_manager import truncate_to_budget


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def generate_digest(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """
    Build a structured daily email digest for the user.
    Returns a dict with sections for urgent emails, follow-ups, stats, and an LLM briefing.
    """
    now = _now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. CRITICAL + HIGH priority emails (top 5)
    urgent_result = await db.execute(
        select(FetchedEmail)
        .where(
            and_(
                FetchedEmail.user_id == user_id,
                FetchedEmail.priority_label.in_(["CRITICAL", "HIGH"]),
            )
        )
        .order_by(desc(FetchedEmail.priority_score))
        .limit(5)
    )
    urgent_emails = urgent_result.scalars().all()

    # 2. Pending follow-ups (overdue or due today)
    followup_result = await db.execute(
        select(FollowUpTracker, FetchedEmail)
        .join(FetchedEmail, FollowUpTracker.fetched_email_id == FetchedEmail.id)
        .where(
            and_(
                FetchedEmail.user_id == user_id,
                FollowUpTracker.status == "pending",
            )
        )
        .order_by(FollowUpTracker.due_date.asc().nullslast())
        .limit(5)
    )
    followups = followup_result.all()

    # 3. Emails > 48 hours old with no draft response
    drafted_ids_result = await db.execute(select(InboxDraft.fetched_email_id))
    drafted_ids = {row[0] for row in drafted_ids_result.fetchall()}

    stale_cutoff = now - timedelta(hours=48)
    stale_result = await db.execute(
        select(FetchedEmail)
        .where(
            and_(
                FetchedEmail.user_id == user_id,
                FetchedEmail.received_at < stale_cutoff,
                ~FetchedEmail.id.in_(drafted_ids) if drafted_ids else True,
            )
        )
        .limit(5)
    )
    stale_emails = stale_result.scalars().all()

    # 4. Pending draft count
    pending_drafts_result = await db.execute(
        select(func.count()).select_from(InboxDraft).where(InboxDraft.status == "pending")
    )
    pending_drafts_count = pending_drafts_result.scalar() or 0

    # 5. Total email count today
    today_count_result = await db.execute(
        select(func.count()).select_from(FetchedEmail).where(
            and_(FetchedEmail.user_id == user_id, FetchedEmail.received_at >= today_start)
        )
    )
    today_count = today_count_result.scalar() or 0

    # Build LLM briefing from all data
    briefing_parts = []
    if urgent_emails:
        briefing_parts.append(
            "Urgent emails:\n" + "\n".join(
                f"- [{e.priority_label}] From {e.sender_email}: {e.subject}" for e in urgent_emails
            )
        )
    if followups:
        briefing_parts.append(
            "Pending follow-ups:\n" + "\n".join(
                f"- {em.sender_email}: {fu.reminder_text or 'Reply needed'}" for fu, em in followups
            )
        )
    if stale_emails:
        briefing_parts.append(
            f"{len(stale_emails)} emails waiting >48hr without a draft response"
        )

    briefing_context = truncate_to_budget("\n\n".join(briefing_parts), 400)
    digest_prompt = DIGEST_PROMPT.format(context=briefing_context, date=now.strftime("%Y-%m-%d"))

    try:
        llm_result = await generate(digest_prompt, system_prompt=DIGEST_SYSTEM, max_tokens=200)
        briefing_text = llm_result["response"].strip()
    except Exception as e:
        logger.error(f"[Digest] LLM briefing failed: {e}")
        briefing_text = "Could not generate AI briefing. Please check email sections below."

    return {
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(),
        "ai_briefing": briefing_text,
        "stats": {
            "emails_today": today_count,
            "pending_drafts": pending_drafts_count,
            "urgent_count": len(urgent_emails),
            "followup_count": len(followups),
        },
        "urgent_emails": [
            {
                "id": str(e.id),
                "sender": e.sender_email,
                "subject": e.subject,
                "priority_label": e.priority_label,
                "priority_score": e.priority_score,
                "priority_reason": e.priority_reason,
                "received_at": e.received_at.isoformat() if e.received_at else None,
            }
            for e in urgent_emails
        ],
        "pending_followups": [
            {
                "followup_id": str(fu.id),
                "sender": em.sender_email,
                "subject": em.subject,
                "due_date": fu.due_date.isoformat() if fu.due_date else None,
                "reminder": fu.reminder_text,
                "is_overdue": bool(fu.due_date and fu.due_date < now),
            }
            for fu, em in followups
        ],
        "emails_needing_response": [
            {
                "id": str(e.id),
                "sender": e.sender_email,
                "subject": e.subject,
                "received_at": e.received_at.isoformat() if e.received_at else None,
            }
            for e in stale_emails
        ],
    }
