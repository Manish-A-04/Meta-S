import uuid
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import RagDocument
from app.rag.embeddings import generate_embedding
from app.core.logger import logger


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


async def add_document(db: AsyncSession, title: str, content: str) -> RagDocument:
    embedding = generate_embedding(content)
    doc = RagDocument(
        id=uuid.uuid4(),
        title=title,
        content=content,
        embedding=embedding,
    )
    db.add(doc)
    await db.flush()
    return doc


async def search_similar(db: AsyncSession, query: str, top_k: int = 3) -> list[RagDocument]:
    try:
        query_embedding = generate_embedding(query)
        result = await db.execute(select(RagDocument).where(RagDocument.embedding.isnot(None)))
        docs = list(result.scalars().all())
        if not docs:
            return []
        scored = []
        for doc in docs:
            sim = _cosine_similarity(query_embedding, doc.embedding)
            scored.append((sim, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return []
