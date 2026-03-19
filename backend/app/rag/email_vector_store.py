"""
RAG Email Vector Store
──────────────────────────────────────────────────────────────────────────────
Indexes and searches fetched emails with a HYBRID strategy:
  1. SQL filters FIRST for exact metadata (date range, sender) — always precise
  2. Cosine similarity ONLY over the already-filtered subset — never guessing facts

This ensures:
  • "Emails from last 5 days" → exact SQL datetime filter, not semantic guess
  • "Last email from john@example.com" → exact SQL sender+ORDER BY received_at
  • "Find emails about project X" → semantic search (no factual filter needed)
"""

import uuid
import numpy as np
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FetchedEmail
from app.rag.embeddings import generate_embedding, get_embedding_model
from app.core.logger import logger


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr, b_arr = np.array(a), np.array(b)
    norm_a, norm_b = np.linalg.norm(a_arr), np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


async def index_unindexed_emails(db: AsyncSession) -> int:
    """
    Generate and store embeddings for all FetchedEmails where is_indexed=False.
    Uses batch encoding (SentenceTransformer supports batch natively — efficient).
    Returns count of newly indexed emails.
    """
    result = await db.execute(
        select(FetchedEmail).where(FetchedEmail.is_indexed == False)  # noqa: E712
    )
    emails = result.scalars().all()

    if not emails:
        return 0

    model = get_embedding_model()
    texts = [f"Subject: {em.subject or ''}\n{em.body}" for em in emails]

    try:
        # Batch encode — much faster than one-by-one for large sets
        embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
        for em, emb in zip(emails, embeddings):
            em.embedding = emb.tolist()
            em.is_indexed = True
        await db.flush()
        logger.info(f"[EmailVectorStore] Indexed {len(emails)} new emails")
        return len(emails)
    except Exception as e:
        logger.error(f"[EmailVectorStore] Indexing failed: {e}")
        return 0


async def search_emails_hybrid(
    db: AsyncSession,
    query: str,
    sender_filter: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    top_k: int = 5,
    require_embedding: bool = True,
) -> list[FetchedEmail]:
    """
    Hybrid search: SQL filters applied FIRST, cosine similarity over filtered set.

    Args:
        query: Semantic query text.
        sender_filter: Filter to emails from this sender (partial match, case-insensitive).
        date_from: Only emails received on or after this datetime (UTC).
        date_to: Only emails received on or before this datetime (UTC).
        top_k: Max emails to return.
        require_embedding: If True, skip emails without embeddings in semantic ranking.
                           If False, return filtered results even without embeddings.
    """
    filters = []
    if sender_filter:
        filters.append(FetchedEmail.sender_email.ilike(f"%{sender_filter}%"))
    if date_from:
        filters.append(FetchedEmail.received_at >= date_from)
    if date_to:
        filters.append(FetchedEmail.received_at <= date_to)

    stmt = select(FetchedEmail)
    if filters:
        stmt = stmt.where(and_(*filters))
    stmt = stmt.order_by(FetchedEmail.received_at.desc())

    result = await db.execute(stmt)
    candidates = result.scalars().all()

    if not candidates:
        return []

    # If no semantic query needed (factual lookup only), just return SQL-ordered results
    if not query.strip() or not require_embedding:
        return list(candidates[:top_k])

    # Cosine similarity over the filtered subset
    try:
        query_embedding = generate_embedding(query)
        scored = []
        for em in candidates:
            if em.embedding:
                sim = _cosine_similarity(query_embedding, em.embedding)
                scored.append((sim, em))
            else:
                scored.append((0.0, em))  # Unindexed emails go to bottom

        scored.sort(key=lambda x: x[0], reverse=True)
        return [em for _, em in scored[:top_k]]
    except Exception as e:
        logger.error(f"[EmailVectorStore] Semantic search failed: {e}")
        return list(candidates[:top_k])


async def get_sender_emails_ordered(
    db: AsyncSession,
    sender_query: str,
    limit: int = 1,
) -> list[FetchedEmail]:
    """
    Get the most recent N emails from a sender (exact SQL — no semantic needed).
    sender_query: partial match on sender_email or sender_name.
    """
    result = await db.execute(
        select(FetchedEmail)
        .where(
            FetchedEmail.sender_email.ilike(f"%{sender_query}%") |
            FetchedEmail.sender_name.ilike(f"%{sender_query}%")
        )
        .order_by(FetchedEmail.received_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
