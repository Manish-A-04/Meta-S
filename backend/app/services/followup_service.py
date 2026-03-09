"""
Follow-up Tracker Service
──────────────────────────────────────────────────────────────────────────────
Detects emails that need a reply by a deadline and tracks them in follow_up_tracker.
"""

import uuid
import re
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.db.models import FetchedEmail, FollowUpTracker
from app.llm.model_loader import generate
from app.llm.prompt_templates import FOLLOWUP_DETECT_SYSTEM, FOLLOWUP_DETECT_PROMPT
from app.llm.token_manager import truncate_to_budget


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def extract_followup_info(subject: str | None, body: str) -> dict:
    """
    Use LLM to detect whether an email needs a follow-up, and by when.
    Returns: {needs_followup: bool, due_date_str: str|None, reminder: str}
    """
    truncated_body = truncate_to_budget(body, 150)
    prompt = FOLLOWUP_DETECT_PROMPT.format(
        subject=subject or "(no subject)",
        body=truncated_body,
        current_date=_now().strftime("%Y-%m-%d"),
    )
    try:
        result = await generate(prompt, system_prompt=FOLLOWUP_DETECT_SYSTEM, max_tokens=80)
        response = result["response"].strip()

        needs = bool(re.search(r"\b(yes|true|1)\b", response, re.IGNORECASE))
        due_match = re.search(r"Due:\s*(\d{4}-\d{2}-\d{2})", response)
        reminder_match = re.search(r"Reminder:\s*(.+)", response)

        return {
            "needs_followup": needs,
            "due_date_str": due_match.group(1) if due_match else None,
            "reminder": reminder_match.group(1).strip() if reminder_match else "Reply required",
        }
    except Exception as e:
        logger.warning(f"[FollowUp] Detection failed: {e}")
        return {"needs_followup": False, "due_date_str": None, "reminder": ""}


async def create_followup(
    db: AsyncSession,
    fetched_email_id: uuid.UUID,
    due_date: datetime | None,
    reminder_text: str,
) -> FollowUpTracker:
    """Manually create a follow-up for an email."""
    fu = FollowUpTracker(
        id=uuid.uuid4(),
        fetched_email_id=fetched_email_id,
        due_date=due_date,
        reminder_text=reminder_text,
        status="pending",
    )
    db.add(fu)
    await db.flush()
    return fu


async def auto_detect_followups(db: AsyncSession) -> int:
    """
    Scan HIGH and CRITICAL priority emails that don't have a follow-up yet.
    Creates follow-up records for those detected by LLM as needing replies.
    Returns count of new follow-ups created.
    """
    # Get high-priority emails without existing follow-ups
    existing_fids_result = await db.execute(select(FollowUpTracker.fetched_email_id))
    existing_fids = {row[0] for row in existing_fids_result.fetchall()}

    result = await db.execute(
        select(FetchedEmail)
        .where(
            and_(
                FetchedEmail.priority_label.in_(["CRITICAL", "HIGH"]),
                ~FetchedEmail.id.in_(existing_fids) if existing_fids else True
            )
        )
        .order_by(desc(FetchedEmail.received_at))
        .limit(20)  # Process up to 20 per call
    )
    emails = result.scalars().all()

    created = 0
    for em in emails:
        try:
            info = await extract_followup_info(em.subject, em.body)
            if info["needs_followup"]:
                due_date = None
                if info["due_date_str"]:
                    try:
                        due_date = datetime.fromisoformat(info["due_date_str"]).replace(tzinfo=timezone.utc)
                    except ValueError:
                        due_date = _now() + timedelta(days=2)  # Default 2-day window

                await create_followup(db, em.id, due_date, info["reminder"])
                created += 1
        except Exception as e:
            logger.warning(f"[FollowUp] Auto-detect failed for email {em.id}: {e}")

    if created:
        await db.flush()
        logger.info(f"[FollowUp] Auto-created {created} follow-up records")
    return created


async def get_pending_followups(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Return all pending follow-ups for the user, sorted by due_date ascending."""
    result = await db.execute(
        select(FollowUpTracker, FetchedEmail)
        .join(FetchedEmail, FollowUpTracker.fetched_email_id == FetchedEmail.id)
        .where(
            and_(
                FetchedEmail.user_id == user_id,
                FollowUpTracker.status == "pending",
            )
        )
        .order_by(FollowUpTracker.due_date.asc().nullslast())
    )
    rows = result.all()

    items = []
    now = _now()
    for fu, em in rows:
        is_overdue = fu.due_date and fu.due_date < now
        items.append({
            "followup_id": str(fu.id),
            "fetched_email_id": str(em.id),
            "sender": em.sender_email,
            "subject": em.subject,
            "reminder": fu.reminder_text,
            "due_date": fu.due_date.isoformat() if fu.due_date else None,
            "is_overdue": is_overdue,
            "status": fu.status,
        })
    return items


async def update_followup_status(
    db: AsyncSession,
    followup_id: uuid.UUID,
    status: str,
) -> dict:
    """Update a follow-up status: pending | snoozed | done."""
    result = await db.execute(select(FollowUpTracker).where(FollowUpTracker.id == followup_id))
    fu = result.scalar_one_or_none()
    if not fu:
        raise ValueError(f"Follow-up {followup_id} not found")
    if status not in ("pending", "snoozed", "done"):
        raise ValueError("Status must be: pending | snoozed | done")
    fu.status = status
    await db.flush()
    return {"followup_id": str(fu.id), "status": fu.status}
