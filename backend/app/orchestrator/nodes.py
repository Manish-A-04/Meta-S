import re
from app.orchestrator.state import GraphState
from app.llm.model_loader import generate
from app.llm.prompt_templates import (
    ROUTER_SYSTEM, ROUTER_PROMPT,
    ANALYST_SYSTEM, ANALYST_PROMPT,
    SCRIBE_SYSTEM, SCRIBE_PROMPT,
    REFLECTOR_SYSTEM, REFLECTOR_PROMPT,
)
from app.llm.token_manager import prepare_input
from app.core.logger import logger


async def router_node(state: GraphState) -> GraphState:
    logger.info(f"Router processing email: {state.get('email_id')}")
    prompt = ROUTER_PROMPT.format(
        subject=state.get("subject", ""),
        body=state.get("body", ""),
    )
    result = await generate(prompt, system_prompt=ROUTER_SYSTEM, max_tokens=10)
    raw = result["response"].strip()
    classification = "Work"
    for cat in ["Spam", "Urgent", "Work"]:
        if cat.lower() in raw.lower():
            classification = cat
            break
    return {
        **state,
        "classification": classification,
        "input_tokens": state.get("input_tokens", 0) + result["input_tokens"],
        "output_tokens": state.get("output_tokens", 0) + result["output_tokens"],
        "latency_ms": state.get("latency_ms", 0) + result["latency_ms"],
    }


async def analyst_node(state: GraphState) -> GraphState:
    logger.info(f"Analyst processing email: {state.get('email_id')}")
    inputs = prepare_input(state.get("body", ""), state.get("rag_context", ""))
    prompt = ANALYST_PROMPT.format(
        subject=state.get("subject", ""),
        body=inputs["email_body"],
        rag_context=inputs["rag_context"] if inputs["rag_context"] else "No relevant context found.",
    )
    result = await generate(prompt, system_prompt=ANALYST_SYSTEM, max_tokens=200)
    analysis = result["response"].strip()
    combined_context = state.get("rag_context", "")
    if analysis:
        combined_context = f"{combined_context}\n\nAnalysis: {analysis}" if combined_context else analysis
    return {
        **state,
        "rag_context": combined_context,
        "input_tokens": state.get("input_tokens", 0) + result["input_tokens"],
        "output_tokens": state.get("output_tokens", 0) + result["output_tokens"],
        "latency_ms": state.get("latency_ms", 0) + result["latency_ms"],
    }


async def scribe_node(state: GraphState) -> GraphState:
    logger.info(f"Scribe drafting for email: {state.get('email_id')}")
    inputs = prepare_input(
        state.get("body", ""),
        state.get("rag_context", ""),
        state.get("draft", ""),
        state.get("critique", ""),
    )
    critique_section = ""
    if state.get("critique"):
        critique_section = f"Previous critique to address:\n{inputs['critique']}\n\n"
    prompt = SCRIBE_PROMPT.format(
        subject=state.get("subject", ""),
        body=inputs["email_body"],
        classification=state.get("classification", ""),
        rag_context=inputs["rag_context"],
        critique_section=critique_section,
    )
    result = await generate(prompt, system_prompt=SCRIBE_SYSTEM, max_tokens=300)
    return {
        **state,
        "draft": result["response"].strip(),
        "input_tokens": state.get("input_tokens", 0) + result["input_tokens"],
        "output_tokens": state.get("output_tokens", 0) + result["output_tokens"],
        "latency_ms": state.get("latency_ms", 0) + result["latency_ms"],
    }


async def reflector_node(state: GraphState) -> GraphState:
    logger.info(f"Reflector evaluating draft for email: {state.get('email_id')}")
    prompt = REFLECTOR_PROMPT.format(
        subject=state.get("subject", ""),
        body=state.get("body", ""),
        draft=state.get("draft", ""),
    )
    result = await generate(prompt, system_prompt=REFLECTOR_SYSTEM, max_tokens=150)
    response_text = result["response"].strip()
    score = 7
    score_match = re.search(r"Score:\s*(\d+)", response_text)
    if score_match:
        score = min(10, max(1, int(score_match.group(1))))
    critique = response_text
    critique_match = re.search(r"Critique:\s*(.*)", response_text, re.DOTALL)
    if critique_match:
        critique = critique_match.group(1).strip()
    scores = list(state.get("reflection_scores", []))
    scores.append(score)
    approved = score >= 7
    return {
        **state,
        "critique": critique,
        "reflection_count": state.get("reflection_count", 0) + 1,
        "reflection_scores": scores,
        "approved": approved,
        "input_tokens": state.get("input_tokens", 0) + result["input_tokens"],
        "output_tokens": state.get("output_tokens", 0) + result["output_tokens"],
        "latency_ms": state.get("latency_ms", 0) + result["latency_ms"],
    }
