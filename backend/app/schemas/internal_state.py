import uuid
from dataclasses import dataclass, field


@dataclass
class EmailState:
    email_id: uuid.UUID
    subject: str
    body: str
    classification: str = ""
    rag_context: str = ""
    draft: str = ""
    critique: str = ""
    reflection_count: int = 0
    reflection_scores: list[int] = field(default_factory=list)
    approved: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
