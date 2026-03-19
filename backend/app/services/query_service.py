"""
Natural Language Query Service
──────────────────────────────────────────────────────────────────────────────
Parses user intent from a natural language query, dispatches to the correct
retrieval strategy (SQL-exact vs semantic), and returns an LLM answer.

Intent types:
  get_emails_by_date     → "emails from last 5 days", "emails today"
  get_last_from_sender   → "last email from john", "latest mail from alice"
  list_priority          → "important emails", "urgent mails", "critical items"
  search_semantic        → "emails about project X"
  answer_question        → "what did john say in his last email?"
  list_all               → "show all emails", "list everything"
"""

import re
import uuid
import time
import json
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.config import get_settings
from app.core.logger import logger
from app.db.models import FetchedEmail, EmailQueryLog
from app.llm.model_loader import generate
from app.llm.prompt_templates import INTENT_PARSER_SYSTEM, INTENT_PARSER_PROMPT, QUERY_ANSWER_SYSTEM, QUERY_ANSWER_PROMPT
from app.llm.token_manager import truncate_to_budget
from app.rag.email_vector_store import search_emails_hybrid, get_sender_emails_ordered


# ── Current datetime for intent resolution ─────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Intent parser ──────────────────────────────────────────────────────────────

async def parse_intent(query: str) -> dict:
    """
    Use LLM to extract structured intent from the NL query.
    Falls back to safe defaults if LLM output is unparseable.

    Returns a dict like:
    {
        "type": "get_emails_by_date",
        "sender_filter": null,
        "days_back": 5,
        "count": 10,
        "action": "list"
    }
    """
    now_str = _now_utc().strftime("%Y-%m-%d %H:%M UTC")
    prompt = INTENT_PARSER_PROMPT.format(query=query, current_datetime=now_str)
    try:
        result = await generate(prompt, system_prompt=INTENT_PARSER_SYSTEM, max_tokens=120)
        response = result["response"].strip()

        # Extract JSON from the response (LLM sometimes adds extra text)
        json_match = re.search(r"\{.*?\}", response, re.DOTALL)
        if json_match:
            intent = json.loads(json_match.group())
            # Enforce known intent types
            valid_types = {
                "get_emails_by_date", "get_last_from_sender", "list_priority",
                "search_semantic", "answer_question", "list_all",
            }
            if intent.get("type") not in valid_types:
                intent["type"] = "search_semantic"
            return intent
    except Exception as e:
        logger.warning(f"[Query] Intent parse failed: {e}")

    # Safe default: treat as semantic search
    return {"type": "search_semantic", "sender_filter": None, "days_back": None, "count": 10, "action": "list"}


# ── Retrieval dispatcher ───────────────────────────────────────────────────────

async def _retrieve_for_intent(db: AsyncSession, user_id: uuid.UUID, intent: dict) -> list[FetchedEmail]:
    """Route intent to the correct retrieval strategy."""
    itype = intent.get("type", "search_semantic")
    count = int(intent.get("count") or 10)

    # ── Exact SQL strategies (never use cosine for factual metadata) ────────────

    if itype == "get_last_from_sender":
        sender = intent.get("sender_filter", "")
        if not sender:
            return []
        return await get_sender_emails_ordered(db, sender, limit=count)

    if itype == "get_emails_by_date":
        days_back = int(intent.get("days_back") or 7)
        date_from = _now_utc() - timedelta(days=days_back)
        result = await db.execute(
            select(FetchedEmail)
            .where(FetchedEmail.received_at >= date_from)
            .order_by(desc(FetchedEmail.received_at))
            .limit(count)
        )
        return result.scalars().all()

    if itype == "list_priority":
        result = await db.execute(
            select(FetchedEmail)
            .order_by(desc(FetchedEmail.priority_score))
            .limit(count)
        )
        return result.scalars().all()

    if itype == "list_all":
        result = await db.execute(
            select(FetchedEmail)
            .order_by(desc(FetchedEmail.received_at))
            .limit(count)
        )
        return result.scalars().all()

    # ── Hybrid strategy (semantic + optional sender/date filters) ───────────────

    sender_filter = intent.get("sender_filter")
    days_back = intent.get("days_back")
    date_from = (_now_utc() - timedelta(days=int(days_back))) if days_back else None

    original_query = intent.get("_original_query", "")
    return await search_emails_hybrid(
        db,
        query=original_query,
        sender_filter=sender_filter,
        date_from=date_from,
        top_k=count,
    )


# ── LLM answer generation ──────────────────────────────────────────────────────

async def _generate_answer(query: str, emails: list[FetchedEmail]) -> str:
    """Generate a natural language answer from retrieved email context."""
    if not emails:
        return "No emails found matching your query."

    # Build compact context from retrieved emails
    context_parts = []
    for i, em in enumerate(emails[:5], 1):  # Max 5 emails in context
        date_str = em.received_at.strftime("%Y-%m-%d %H:%M UTC") if em.received_at else "Unknown date"
        body_excerpt = truncate_to_budget(em.body, 100)
        context_parts.append(
            f"[Email {i}]\n"
            f"From: {em.sender_name or em.sender_email} <{em.sender_email}>\n"
            f"Date: {date_str}\n"
            f"Subject: {em.subject or '(no subject)'}\n"
            f"Body: {body_excerpt}"
        )
    context = "\n\n".join(context_parts)

    prompt = QUERY_ANSWER_PROMPT.format(query=query, context=context)
    try:
        result = await generate(prompt, system_prompt=QUERY_ANSWER_SYSTEM, max_tokens=300)
        return result["response"].strip() or "Unable to generate answer."
    except Exception as e:
        logger.error(f"[Query] Answer generation failed: {e}")
        return f"Found {len(emails)} matching emails but could not generate answer."


# ── Public entry point ─────────────────────────────────────────────────────────

async def execute_nl_query(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
) -> dict:
    """
    Full pipeline: parse intent → retrieve emails → generate answer → log query.

    Returns:
        {
          "answer": str,
          "emails": list[FetchedEmail],
          "intent": dict,
          "result_count": int,
          "latency_ms": int,
        }
    """
    start = time.perf_counter()
    intent = await parse_intent(query)
    intent["_original_query"] = query  # Pass original query for semantic search

    emails = await _retrieve_for_intent(db, user_id, intent)
    answer = await _generate_answer(query, emails)

    latency_ms = int((time.perf_counter() - start) * 1000)

    # Log the query for analytics
    log_entry = EmailQueryLog(
        user_id=user_id,
        query_text=query,
        parsed_intent={k: v for k, v in intent.items() if k != "_original_query"},
        result_count=len(emails),
        latency_ms=latency_ms,
    )
    db.add(log_entry)
    await db.flush()

    return {
        "answer": answer,
        "emails": emails,
        "intent": {k: v for k, v in intent.items() if k != "_original_query"},
        "result_count": len(emails),
        "latency_ms": latency_ms,
    }
