import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.orchestrator.graph import run_graph
from app.orchestrator.state import GraphState
from app.rag.retriever import retrieve_context
from app.db.models import Email, Draft, AgentLog
from app.core.logger import logger


async def process_email(
    db: AsyncSession,
    user_id: uuid.UUID,
    subject: str | None,
    body: str,
    force_reflection: bool = False,
    max_reflections: int = 2,
) -> dict:
    email_id = uuid.uuid4()
    email_record = Email(
        id=email_id,
        user_id=user_id,
        subject=subject,
        body=body,
        status="pending",
    )
    db.add(email_record)
    await db.flush()

    rag_context = await retrieve_context(db, body, top_k=3)

    initial_state: GraphState = {
        "email_id": str(email_id),
        "subject": subject or "",
        "body": body,
        "classification": "",
        "rag_context": rag_context,
        "draft": "",
        "critique": "",
        "reflection_count": 0,
        "reflection_scores": [],
        "approved": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_ms": 0,
        "max_reflections": max_reflections,
        "force_reflection": force_reflection,
    }

    final_state = await run_graph(initial_state)

    email_record.classification = final_state.get("classification", "Work")
    email_record.status = "processed"

    scores = final_state.get("reflection_scores", [])
    ref_count = final_state.get("reflection_count", 0)

    if ref_count == 0:
        draft_record = Draft(
            email_id=email_id,
            version=1,
            content=final_state.get("draft", ""),
            reflection_score=None,
            approved=True,
        )
        db.add(draft_record)
    else:
        for i, score in enumerate(scores):
            is_last = i == len(scores) - 1
            draft_record = Draft(
                email_id=email_id,
                version=i + 1,
                content=final_state.get("draft", ""),
                reflection_score=score,
                approved=is_last and final_state.get("approved", False),
            )
            db.add(draft_record)

    agent_types = ["router", "analyst", "scribe"]
    for _ in range(ref_count):
        agent_types.append("reflector")
        agent_types.append("scribe")
    for agent_type in agent_types:
        log = AgentLog(
            email_id=email_id,
            agent_type=agent_type,
            input_tokens=final_state.get("input_tokens", 0) // len(agent_types),
            output_tokens=final_state.get("output_tokens", 0) // len(agent_types),
            latency_ms=final_state.get("latency_ms", 0) // len(agent_types),
        )
        db.add(log)

    await db.flush()
    logger.info(f"Email {email_id} processed: {final_state.get('classification')}")

    return {
        "email_id": email_id,
        "classification": final_state.get("classification", "Work"),
        "final_draft": final_state.get("draft", ""),
        "reflection_count": ref_count,
        "reflection_scores": scores,
        "approved": final_state.get("approved", True),
        "usage": {
            "input_tokens": final_state.get("input_tokens", 0),
            "output_tokens": final_state.get("output_tokens", 0),
            "total_tokens": final_state.get("input_tokens", 0) + final_state.get("output_tokens", 0),
            "latency_ms": final_state.get("latency_ms", 0),
        },
    }
