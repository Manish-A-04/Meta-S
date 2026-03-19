from app.core.config import get_settings


def count_tokens_approx(text: str) -> int:
    return len(text.split())


def truncate_to_budget(text: str, max_tokens: int) -> str:
    words = text.split()
    if len(words) <= max_tokens:
        return text
    return " ".join(words[:max_tokens])


def allocate_budgets() -> dict[str, int]:
    settings = get_settings()
    total = settings.MAX_CONTEXT_TOKENS
    return {
        "system_prompt": 200,
        "email_body": 600,
        "rag_context": 600,
        "draft_critique": 400,
        "output_buffer": total - 200 - 600 - 600 - 400,
    }


def prepare_input(email_body: str, rag_context: str, draft: str = "", critique: str = "") -> dict[str, str]:
    budgets = allocate_budgets()
    return {
        "email_body": truncate_to_budget(email_body, budgets["email_body"]),
        "rag_context": truncate_to_budget(rag_context, budgets["rag_context"]),
        "draft": truncate_to_budget(draft, budgets["draft_critique"] // 2),
        "critique": truncate_to_budget(critique, budgets["draft_critique"] // 2),
    }
