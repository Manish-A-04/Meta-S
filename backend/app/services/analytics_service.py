"""
Email Analytics Service
──────────────────────────────────────────────────────────────────────────────
Returns aggregated statistics about the user's email corpus:
  - Volume by day (last 7 days)
  - Top senders by email count
  - Priority distribution breakdown
  - Average response time (emails with drafts)
  - Draft approval rate
  - Busiest email hours
"""

import uuid
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.db.models import FetchedEmail, InboxDraft, EmailQueryLog


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_email_analytics(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """
    Generate comprehensive email analytics for the dashboard.
    All computations are done in Python from SQLAlchemy results (no raw SQL).
    """
    now = _now()
    seven_days_ago = now - timedelta(days=7)

    # ── Fetch all needed data ───────────────────────────────────────────────────

    emails_result = await db.execute(
        select(FetchedEmail)
        .where(FetchedEmail.user_id == user_id)
        .order_by(desc(FetchedEmail.received_at))
    )
    all_emails = emails_result.scalars().all()

    drafts_result = await db.execute(
        select(InboxDraft, FetchedEmail)
        .join(FetchedEmail, InboxDraft.fetched_email_id == FetchedEmail.id)
        .where(FetchedEmail.user_id == user_id)
    )
    all_drafts_rows = drafts_result.all()

    # ── Volume by day (last 7 days) ─────────────────────────────────────────────
    recent_emails = [e for e in all_emails if e.received_at and e.received_at >= seven_days_ago]
    volume_by_day: dict[str, int] = defaultdict(int)
    for e in recent_emails:
        day_key = e.received_at.strftime("%Y-%m-%d")
        volume_by_day[day_key] += 1

    # Fill in days with 0 count
    for i in range(7):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        volume_by_day.setdefault(day, 0)
    volume_by_day_sorted = dict(sorted(volume_by_day.items()))

    # ── Top senders ─────────────────────────────────────────────────────────────
    sender_counts: Counter = Counter(e.sender_email for e in all_emails)
    top_senders = [
        {"sender": s, "count": c}
        for s, c in sender_counts.most_common(10)
    ]

    # ── Priority distribution ───────────────────────────────────────────────────
    priority_dist = Counter(e.priority_label for e in all_emails)
    priority_distribution = {
        "CRITICAL": priority_dist.get("CRITICAL", 0),
        "HIGH": priority_dist.get("HIGH", 0),
        "MEDIUM": priority_dist.get("MEDIUM", 0),
        "LOW": priority_dist.get("LOW", 0),
    }

    # ── Draft approval rate ─────────────────────────────────────────────────────
    total_drafts = len(all_drafts_rows)
    approved_drafts = sum(1 for d, _ in all_drafts_rows if d.status == "approved")
    approval_rate = round(approved_drafts / total_drafts, 3) if total_drafts > 0 else 0.0

    # ── Busiest email hours ─────────────────────────────────────────────────────
    hour_counts: Counter = Counter()
    for e in all_emails:
        if e.received_at:
            hour_counts[e.received_at.hour] += 1
    busiest_hours = [
        {"hour": h, "count": c}
        for h, c in sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    # ── NL Query counts ─────────────────────────────────────────────────────────
    query_result = await db.execute(
        select(func.count()).select_from(EmailQueryLog).where(EmailQueryLog.user_id == user_id)
    )
    total_queries = query_result.scalar() or 0

    return {
        "generated_at": now.isoformat(),
        "total_emails": len(all_emails),
        "emails_last_7_days": len(recent_emails),
        "volume_by_day": volume_by_day_sorted,
        "top_senders": top_senders,
        "priority_distribution": priority_distribution,
        "draft_stats": {
            "total_drafts": total_drafts,
            "approved_drafts": approved_drafts,
            "approval_rate": approval_rate,
            "pending_drafts": sum(1 for d, _ in all_drafts_rows if d.status == "pending"),
        },
        "busiest_hours": busiest_hours,
        "total_nl_queries": total_queries,
    }
