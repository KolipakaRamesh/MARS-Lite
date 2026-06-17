"""
MARS-Lite — LangGraph Orchestration Graph.

Simplified topology:
  planner → research (loop until all subtasks done) → analyst → END

The reviewer node and retry loop have been removed.
"""
import logging
from langgraph.graph import StateGraph, END
from backend.orchestration.state import AgentState
from backend.orchestration.router import route_after_research

logger = logging.getLogger(__name__)


def build_graph(planner, research, analyst):
    """
    Wire up the StateGraph with three agents and one conditional edge.
    Returns a compiled, executable graph.

    Args:
        planner:  PlannerAgent instance
        research: ResearchAgent instance
        analyst:  AnalystAgent instance
    """
    graph = StateGraph(AgentState)

    # ── Register nodes ───────────────────────────────────────────────────────
    graph.add_node("planner",  planner.run)
    graph.add_node("research", research.run)
    graph.add_node("analyst",  analyst.run)

    # ── Entry point ──────────────────────────────────────────────────────────
    graph.set_entry_point("planner")

    # ── Static edges ─────────────────────────────────────────────────────────
    graph.add_edge("planner", "research")

    # ── Conditional edge: research loop or advance to analyst ─────────────────
    graph.add_conditional_edges(
        "research",
        route_after_research,
        {
            "research": "research",  # loop: more subtasks remain
            "analyst":  "analyst",   # done: all subtasks complete
        },
    )

    # ── Analyst → END ─────────────────────────────────────────────────────────
    graph.add_edge("analyst", END)

    compiled = graph.compile()
    logger.info("MARS-Lite graph compiled: planner → research(loop) → analyst → END")
    return compiled
