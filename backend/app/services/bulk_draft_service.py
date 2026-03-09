"""
Bulk Draft Service
──────────────────────────────────────────────────────────────────────────────
Generates email reply drafts for multiple fetched emails at once, stores them
as InboxDraft records, and supports per-draft feedback-driven redrafting.

Each draft is independently editable — feedback on draft A does NOT affect draft B.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.db.models import FetchedEmail, InboxDraft
from app.orchestrator.graph import run_graph
from app.orchestrator.state import GraphState
from app.llm.model_loader import generate
from app.llm.prompt_templates import FEEDBACK_SCRIBE_SYSTEM, FEEDBACK_SCRIBE_PROMPT
from app.llm.token_manager import prepare_input


async def _draft_single_email(fetched_email: FetchedEmail) -> str:
    """Run the existing LangGraph orchestrator on a single fetched email."""
    initial_state: GraphState = {
        "email_id": str(fetched_email.id),
        "subject": fetched_email.subject or "",
        "body": fetched_email.body,
        "classification": "",
        "rag_context": "",
        "draft": "",
        "critique": "",
        "reflection_count": 0,
        "reflection_scores": [],
        "approved": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_ms": 0,
        "max_reflections": 1,       # Conservative — 1 reflection per draft in bulk mode
        "force_reflection": False,
    }
    final_state = await run_graph(initial_state)
    return final_state.get("draft", "")


async def generate_bulk_drafts(
    db: AsyncSession,
    user_id: uuid.UUID,
    count: int = 3,
) -> list[dict]:
    """
    Generate draft responses for the `count` most recent fetched emails.
    Returns a list of DraftBlock dicts (one per email).
    Emails that already have a draft are skipped unless explicitly requested.
    """
    count = max(1, min(count, 20))  # Safety cap at 20

    result = await db.execute(
        select(FetchedEmail)
        .where(FetchedEmail.user_id == user_id)
        .order_by(desc(FetchedEmail.received_at))
        .limit(count)
    )
    emails = result.scalars().all()

    if not emails:
        return []

    draft_blocks = []
    for em in emails:
        try:
            draft_content = await _draft_single_email(em)

            # Save as InboxDraft (version 1)
            draft = InboxDraft(
                id=uuid.uuid4(),
                fetched_email_id=em.id,
                version=1,
                content=draft_content,
                status="pending",
            )
            db.add(draft)
            await db.flush()

            draft_blocks.append({
                "draft_id": draft.id,
                "fetched_email_id": em.id,
                "sender": f"{em.sender_name or ''} <{em.sender_email}>".strip(),
                "subject": em.subject or "(no subject)",
                "received_at": em.received_at.isoformat() if em.received_at else None,
                "priority_label": em.priority_label,
                "priority_score": em.priority_score,
                "draft_content": draft_content,
                "version": 1,
                "status": "pending",
            })
            logger.info(f"[BulkDraft] Drafted email from {em.sender_email}: subject='{em.subject}'")
        except Exception as e:
            logger.error(f"[BulkDraft] Failed to draft email {em.id}: {e}")
            draft_blocks.append({
                "draft_id": None,
                "fetched_email_id": em.id,
                "sender": em.sender_email,
                "subject": em.subject or "(no subject)",
                "received_at": em.received_at.isoformat() if em.received_at else None,
                "priority_label": em.priority_label,
                "priority_score": em.priority_score,
                "draft_content": "",
                "version": 0,
                "status": "error",
                "error": str(e),
            })

    return draft_blocks


async def redraft_with_feedback(
    db: AsyncSession,
    draft_id: uuid.UUID,
    feedback: str,
) -> dict:
    """
    Redraft a specific email reply incorporating user feedback.
    Creates a new InboxDraft version; previous version is preserved for history.
    """
    # Load the existing draft and its parent email
    result = await db.execute(
        select(InboxDraft).where(InboxDraft.id == draft_id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")

    email_result = await db.execute(
        select(FetchedEmail).where(FetchedEmail.id == draft.fetched_email_id)
    )
    fetched_email = email_result.scalar_one_or_none()
    if not fetched_email:
        raise ValueError(f"Original email for draft {draft_id} not found")

    # Mark current draft as "editing"
    draft.status = "editing"
    draft.feedback = feedback

    # Generate new draft incorporating the feedback as critique
    inputs = prepare_input(fetched_email.body, "", draft.content, feedback)
    prompt = FEEDBACK_SCRIBE_PROMPT.format(
        subject=fetched_email.subject or "",
        body=inputs["email_body"],
        previous_draft=inputs["draft"],
        feedback=feedback,
    )
    try:
        result_llm = await generate(prompt, system_prompt=FEEDBACK_SCRIBE_SYSTEM, max_tokens=350)
        new_content = result_llm["response"].strip()
    except Exception as e:
        logger.error(f"[BulkDraft] Redraft LLM call failed: {e}")
        raise RuntimeError(f"Failed to generate redraft: {e}")

    # Save as next version
    new_draft = InboxDraft(
        id=uuid.uuid4(),
        fetched_email_id=draft.fetched_email_id,
        version=draft.version + 1,
        content=new_content,
        status="pending",
    )
    db.add(new_draft)
    await db.flush()

    return {
        "draft_id": new_draft.id,
        "fetched_email_id": new_draft.fetched_email_id,
        "version": new_draft.version,
        "draft_content": new_content,
        "status": "pending",
        "previous_version": draft.version,
        "feedback_applied": feedback,
    }


async def approve_draft(db: AsyncSession, draft_id: uuid.UUID) -> dict:
    """Mark a draft as user-approved."""
    result = await db.execute(select(InboxDraft).where(InboxDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")
    draft.status = "approved"
    await db.flush()
    return {"draft_id": draft.id, "status": "approved", "version": draft.version}


async def edit_draft_directly(
    db: AsyncSession,
    draft_id: uuid.UUID,
    new_content: str,
) -> dict:
    """
    Replace draft content with user's direct edit.
    Saves as a new auto-approved version to preserve history.
    """
    result = await db.execute(select(InboxDraft).where(InboxDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")

    new_draft = InboxDraft(
        id=uuid.uuid4(),
        fetched_email_id=draft.fetched_email_id,
        version=draft.version + 1,
        content=new_content,
        status="approved",   # Direct edits are auto-approved
    )
    db.add(new_draft)
    draft.status = "editing"
    await db.flush()

    return {
        "draft_id": new_draft.id,
        "version": new_draft.version,
        "draft_content": new_content,
        "status": "approved",
    }
