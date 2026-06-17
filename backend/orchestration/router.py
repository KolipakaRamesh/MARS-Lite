"""
MARS-Lite — Orchestration Router.

Only one routing function remains: after each research step, decide
whether to loop back for more subtasks or advance to the analyst.
The reviewer route has been removed entirely.
"""
import logging
from langgraph.graph import END
from backend.orchestration.state import AgentState

logger = logging.getLogger(__name__)


def route_after_research(state: AgentState) -> str:
    """
    After a research step:
    - If there are remaining subtasks → loop back to research
    - If all subtasks done, or an error occurred → proceed to analyst
    """
    if state.get("error"):
        return "analyst"  # forward best-effort research on error

    idx   = state["current_subtask_index"]
    total = len(state["subtasks"])
    next_node = "research" if idx < total else "analyst"
    logger.info("[Router] Research %d/%d complete. Next: %s", idx, total, next_node)
    return next_node
