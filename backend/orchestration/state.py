"""
MARS-Lite — Shared Agent State (the blackboard).

Simplified: removed reviewer fields (quality_score, verdict, feedback),
removed memory_context, removed iteration tracking.
Added tool_calls to capture web_search invocations for the UI.
"""
from typing import TypedDict, Annotated, List, Optional
import operator
import logging

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    # ── Input ────────────────────────────────────────────────────────────────
    query: str
    session_id: str

    # ── Context Memory ───────────────────────────────────────────────────────
    memory_context: str
    memory_context_tokens: int

    # ── Planner output ───────────────────────────────────────────────────────
    subtasks: List[str]
    current_subtask_index: int

    # ── Research output (append-only accumulator) ────────────────────────────
    raw_research: Annotated[List[str], operator.add]

    # ── Analyst output ───────────────────────────────────────────────────────
    synthesized_answer: str

    # ── Tool calls (append-only) — one entry per web_search invocation ───────
    # Each entry: {tool, input, output, duration_ms, timestamp}
    tool_calls: Annotated[List[dict], operator.add]

    # ── LLM usage (append-only, one entry per LLM call) ─────────────────────
    # Each entry: {agent, model, prompt_tokens, completion_tokens, total_tokens, latency_ms}
    llm_usage: Annotated[List[dict], operator.add]

    # ── Audit trail (append-only) ─────────────────────────────────────────────
    agent_trace: Annotated[List[dict], operator.add]

    # ── Error ─────────────────────────────────────────────────────────────────
    error: Optional[str]


def initial_state(query: str, session_id: str = "default") -> AgentState:
    """Factory — returns a clean initial state for a new query."""
    import backend.memory.simple_memory as simple_memory
    mem = simple_memory.retrieve()
    history = mem.get("history", [])
    if history:
        # Format last 3 queries as context memory
        memory_context = "Recent Search History:\n" + "\n".join([
            f"- Past Query: {h['last_query']} (Category: {h['last_category']}, Budget: {h.get('last_budget') or 'N/A'})"
            for h in history[:3]
        ])
    else:
        memory_context = ""
    
    # Estimate tokens (~4 characters per token)
    memory_context_tokens = len(memory_context) // 4 if memory_context else 0

    logger.info("initial_state: memory_context_tokens=%d context_len=%d", memory_context_tokens, len(memory_context))

    return AgentState(
        query=query,
        session_id=session_id,
        memory_context=memory_context,
        memory_context_tokens=memory_context_tokens,
        subtasks=[],
        current_subtask_index=0,
        raw_research=[],
        synthesized_answer="",
        tool_calls=[],
        llm_usage=[],
        agent_trace=[],
        error=None,
    )
