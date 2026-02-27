from app.orchestrator.state import GraphState
from app.orchestrator.nodes import router_node, analyst_node, scribe_node, reflector_node
from app.core.logger import logger


def should_reflect(state: GraphState) -> bool:
    max_ref = state.get("max_reflections", 2)
    current = state.get("reflection_count", 0)
    force = state.get("force_reflection", False)
    approved = state.get("approved", False)
    if current >= max_ref:
        return False
    if current == 0 and force:
        return True
    if current == 0:
        return True
    if not approved:
        return True
    return False


async def run_graph(initial_state: GraphState) -> GraphState:
    logger.info(f"Starting orchestrator graph for email: {initial_state.get('email_id')}")
    state = await router_node(initial_state)
    logger.info(f"Classification: {state.get('classification')}")
    state = await analyst_node(state)
    state = await scribe_node(state)
    while should_reflect(state):
        state = await reflector_node(state)
        if not state.get("approved", False) and state.get("reflection_count", 0) < state.get("max_reflections", 2):
            state = await scribe_node(state)
    if state.get("reflection_count", 0) == 0:
        state["approved"] = True
    logger.info(
        f"Graph complete. Reflections: {state.get('reflection_count')}, "
        f"Approved: {state.get('approved')}"
    )
    return state
