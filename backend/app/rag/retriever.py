from sqlalchemy.ext.asyncio import AsyncSession
from app.rag.vector_store import search_similar
from app.core.logger import logger


async def retrieve_context(db: AsyncSession, query: str, top_k: int = 3) -> str:
    try:
        docs = await search_similar(db, query, top_k=top_k)
        if not docs:
            return ""
        chunks = []
        for doc in docs:
            chunks.append(f"[{doc.title}]: {doc.content}")
        context = "\n\n".join(chunks)
        logger.info(f"Retrieved {len(docs)} RAG documents")
        return context
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        return ""
