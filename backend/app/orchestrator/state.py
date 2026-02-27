from typing import TypedDict


class GraphState(TypedDict, total=False):
    email_id: str
    subject: str
    body: str
    classification: str
    rag_context: str
    draft: str
    critique: str
    reflection_count: int
    reflection_scores: list[int]
    approved: bool
    input_tokens: int
    output_tokens: int
    latency_ms: int
    max_reflections: int
    force_reflection: bool
