"""
Email Priority Engine
──────────────────────────────────────────────────────────────────────────────
Scores emails 0–100 based on urgency signals. Two-pass approach:
  1. Fast rule-based pre-score (zero LLM tokens)
  2. LLM verification only when rule-score ≥ 30 (conserves VRAM budget)

Score labels:
  90–100 → CRITICAL   (e.g., "Meeting today at 7pm", "urgent action required")
  70–89  → HIGH       (e.g., "Please review by EOD", deadline this week)
  40–69  → MEDIUM     (e.g., FWDs, action verbs without deadline)
  0–39   → LOW        (informational, newsletters, no action needed)
"""

import re
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logger import logger
from app.db.models import FetchedEmail
from app.llm.model_loader import generate
from app.llm.prompt_templates import PRIORITY_SYSTEM, PRIORITY_PROMPT
from app.llm.token_manager import truncate_to_budget


# ── Rule-based signals ─────────────────────────────────────────────────────────

# Today / very-soon time references (high urgency)
_TODAY_TIME_RE = re.compile(
    r"\b(today|tonight|this\s+evening|this\s+morning|right\s+now|immediately)\b"
    r".*?\b(\d{1,2}(:\d{2})?\s*(am|pm|AM|PM))\b",
    re.IGNORECASE | re.DOTALL,
)
_TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)

# Explicit urgency keywords
_URGENT_KW_RE = re.compile(
    r"\b(urgent|asap|as\s+soon\s+as\s+possible|critical|emergency|immediate(ly)?|"
    r"by\s+eod|by\s+end\s+of\s+day|by\s+close\s+of\s+business|by\s+cob|"
    r"time[- ]sensitive|overdue|past\s+due)\b",
    re.IGNORECASE,
)

# Deadline patterns — "by [date]", "due [date]", "before [date]"
_DEADLINE_RE = re.compile(
    r"\b(deadline|due\s+(by|on|date)|by\s+(monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|"
    r"respond\s+by|reply\s+by|complete\s+by|submit\s+by)\b",
    re.IGNORECASE,
)

# Action required phrases
_ACTION_RE = re.compile(
    r"\b(please\s+(review|confirm|approve|sign|respond|reply|action)|"
    r"action\s+required|your\s+(approval|sign-off|confirmation)\s+(is\s+)?needed|"
    r"kindly\s+(review|confirm|send)|waiting\s+for\s+your|requires?\s+your)\b",
    re.IGNORECASE,
)

# Meeting references
_MEETING_RE = re.compile(
    r"\b(meeting|call|conference|interview|demo|presentation|stand-?up|sync)\b",
    re.IGNORECASE,
)

# Low-priority signals (reduce score)
_LOW_PRIORITY_RE = re.compile(
    r"\b(newsletter|unsubscribe|no\s+reply|noreply|promotional|offer|sale|discount|"
    r"subscription|weekly\s+digest|monthly\s+summary|automated\s+message|"
    r"do\s+not\s+reply)\b",
    re.IGNORECASE,
)


def _rule_based_score(subject: str, body: str, received_at: datetime | None) -> tuple[int, list[str]]:
    """
    Fast rule-based pre-scoring. Returns (score, list_of_triggered_reasons).
    No LLM calls — completes in microseconds.
    """
    score = 10  # baseline
    reasons = []
    combined = f"{subject or ''} {body or ''}"

    # ── Positive signals ───────────────────────────────────────────────────────
    if _TODAY_TIME_RE.search(combined):
        score += 45
        reasons.append("Meeting/event referenced for today")

    if _URGENT_KW_RE.search(combined):
        score += 35
        reasons.append("Explicit urgency keyword found")

    if _DEADLINE_RE.search(combined):
        score += 25
        reasons.append("Deadline mentioned")

    if _ACTION_RE.search(combined):
        score += 20
        reasons.append("Action required from recipient")

    if _MEETING_RE.search(combined):
        score += 15
        reasons.append("Meeting/call referenced")

    if _TOMORROW_RE.search(combined):
        score += 12
        reasons.append("Tomorrow's deadline or event")

    if subject and re.search(r"^(re:|fwd?:)", subject.strip(), re.IGNORECASE):
        score += 8
        reasons.append("Forwarded or replied email thread")

    # ── Recency bonus ──────────────────────────────────────────────────────────
    if received_at:
        now = datetime.now(timezone.utc)
        hours_old = (now - received_at).total_seconds() / 3600
        if hours_old < 2:
            score += 10
            reasons.append("Received within last 2 hours")
        elif hours_old < 24:
            score += 5
            reasons.append("Received today")

    # ── Low-priority penalty ───────────────────────────────────────────────────
    if _LOW_PRIORITY_RE.search(combined):
        score = max(0, score - 30)
        reasons.append("[Reduced] Promotional/automated email detected")

    return min(score, 100), reasons


def _label_from_score(score: int) -> str:
    settings = get_settings()
    if score >= settings.PRIORITY_CRITICAL_THRESHOLD:
        return "CRITICAL"
    if score >= settings.PRIORITY_HIGH_THRESHOLD:
        return "HIGH"
    if score >= settings.PRIORITY_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


# ── LLM verification ──────────────────────────────────────────────────────────

async def _llm_verify_score(subject: str, body: str, rule_score: int) -> tuple[int, str]:
    """
    Ask the LLM to validate and refine the priority score.
    Only called when rule_score >= 30 to save tokens.
    Returns (final_score, reason_text).
    """
    try:
        truncated_body = truncate_to_budget(body, 200)  # Tight budget — 200 words max
        prompt = PRIORITY_PROMPT.format(
            subject=subject or "(no subject)",
            body=truncated_body,
            rule_score=rule_score,
        )
        result = await generate(prompt, system_prompt=PRIORITY_SYSTEM, max_tokens=80)
        response = result["response"].strip()

        # Parse "Score: XX\nReason: ..." format
        score_match = re.search(r"Score:\s*(\d+)", response)
        reason_match = re.search(r"Reason:\s*(.+)", response, re.DOTALL)

        final_score = rule_score  # fallback to rule score
        if score_match:
            final_score = min(100, max(0, int(score_match.group(1))))
        reason = reason_match.group(1).strip() if reason_match else response[:200]
        return final_score, reason
    except Exception as e:
        logger.warning(f"[Priority] LLM verify failed: {e}, using rule score")
        return rule_score, "Rule-based scoring (LLM unavailable)"


# ── Public API ─────────────────────────────────────────────────────────────────

async def score_single_email(
    subject: str | None,
    body: str,
    received_at: datetime | None,
    sender_email: str | None = None,
) -> dict:
    """
    Score a single email. Returns {score, label, reason}.
    """
    rule_score, rule_reasons = _rule_based_score(subject or "", body, received_at)
    rule_reason_text = "; ".join(rule_reasons) if rule_reasons else "No strong signals detected"

    # Only invoke LLM when worth the tokens
    if rule_score >= 30:
        final_score, llm_reason = await _llm_verify_score(subject or "", body, rule_score)
        reason = llm_reason or rule_reason_text
    else:
        final_score = rule_score
        reason = rule_reason_text

    return {
        "score": final_score,
        "label": _label_from_score(final_score),
        "reason": reason,
    }


async def batch_score_emails(db: AsyncSession) -> int:
    """
    Score all FetchedEmails that have priority_score == 0 (unscored).
    Returns the count of emails scored.
    """
    result = await db.execute(
        select(FetchedEmail).where(FetchedEmail.priority_score == 0)
    )
    emails = result.scalars().all()

    if not emails:
        logger.info("[Priority] No unscored emails to process")
        return 0

    scored_count = 0
    for em in emails:
        try:
            priority = await score_single_email(
                subject=em.subject,
                body=em.body,
                received_at=em.received_at,
                sender_email=em.sender_email,
            )
            em.priority_score = priority["score"]
            em.priority_label = priority["label"]
            em.priority_reason = priority["reason"]
            scored_count += 1
        except Exception as e:
            logger.warning(f"[Priority] Failed to score email {em.id}: {e}")

    if scored_count:
        await db.flush()
        logger.info(f"[Priority] Scored {scored_count} emails")

    return scored_count


async def refresh_all_scores(db: AsyncSession) -> int:
    """Force re-score of ALL fetched emails (ignores existing scores)."""
    result = await db.execute(select(FetchedEmail))
    emails = result.scalars().all()

    updated = 0
    for em in emails:
        try:
            priority = await score_single_email(em.subject, em.body, em.received_at, em.sender_email)
            em.priority_score = priority["score"]
            em.priority_label = priority["label"]
            em.priority_reason = priority["reason"]
            updated += 1
        except Exception as e:
            logger.warning(f"[Priority] Re-score failed for {em.id}: {e}")

    if updated:
        await db.flush()
    return updated
