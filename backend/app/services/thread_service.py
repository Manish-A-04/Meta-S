"""Thread summarization service — groups emails by thread_id and summarizes."""

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.db.models import FetchedEmail
from app.llm.model_loader import generate
from app.llm.prompt_templates import THREAD_SUMMARY_SYSTEM, THREAD_SUMMARY_PROMPT
from app.llm.token_manager import truncate_to_budget


async def get_thread_emails(db: AsyncSession, thread_id: str) -> list[FetchedEmail]:
    """Return all emails in a thread, ordered chronologically."""
    result = await db.execute(
        select(FetchedEmail)
        .where(FetchedEmail.thread_id == thread_id)
        .order_by(FetchedEmail.received_at.asc())
    )
    return result.scalars().all()


async def summarize_thread(db: AsyncSession, thread_id: str) -> dict:
    """
    Summarize an email thread — returns a concise narrative of the conversation.
    """
    emails = await get_thread_emails(db, thread_id)
    if not emails:
        return {
            "thread_id": thread_id, 
            "email_count": 0, 
            "participants": [],
            "date_range": {"from": None, "to": None},
            "summary": "No emails found in this thread.",
            "emails": []
        }

    # Build chronological thread context (tight token budget)
    thread_text_parts = []
    for em in emails:
        date_str = em.received_at.strftime("%Y-%m-%d %H:%M") if em.received_at else "?"
        body_snippet = truncate_to_budget(em.body, 80)
        thread_text_parts.append(
            f"[{date_str}] {em.sender_name or em.sender_email}: {body_snippet}"
        )
    thread_context = "\n\n".join(thread_text_parts)
    thread_context = truncate_to_budget(thread_context, 500)  # Hard cap for context budget

    prompt = THREAD_SUMMARY_PROMPT.format(
        subject=emails[0].subject or "(no subject)",
        thread=thread_context,
    )
    try:
        result = await generate(prompt, system_prompt=THREAD_SUMMARY_SYSTEM, max_tokens=200)
        summary = result["response"].strip()
    except Exception as e:
        logger.error(f"[Thread] Summarization failed: {e}")
        summary = "Summarization failed. Please try again."

    return {
        "thread_id": thread_id,
        "email_count": len(emails),
        "participants": list({em.sender_email for em in emails}),
        "date_range": {
            "from": emails[0].received_at.isoformat() if emails[0].received_at else None,
            "to": emails[-1].received_at.isoformat() if emails[-1].received_at else None,
        },
        "summary": summary,
        "emails": [{"id": str(e.id), "sender": e.sender_email, "subject": e.subject} for e in emails],
    }
