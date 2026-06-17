"""
MARS-Lite — Rule-Based Evaluator.

Replaces the LLM-as-Judge (ReviewerAgent) with deterministic, instant checks.
No LLM calls. No quality scoring. Just observable facts about the run.

Criteria:
  workflow_completed  — did all 3 agents execute?
  tool_called         — did web_search get invoked at least once?
  task_completed      — is there a non-empty synthesized answer?
  score               — 0, 33, 66, or 100 (33 per passing criterion)
"""
import logging

logger = logging.getLogger(__name__)

_AGENT_NAMES = {"planner", "research", "analyst"}


def evaluate(state: dict) -> dict:
    """
    Run all rule-based checks against the final pipeline state.

    Args:
        state: The final AgentState dict after graph execution.

    Returns:
        {
          "workflow_completed": bool,
          "tool_called":        bool,
          "task_completed":     bool,
          "score":              int   (0 | 33 | 66 | 100)
          "details":            dict  — per-criterion explanation
        }
    """
    agent_trace: list[dict] = state.get("agent_trace", [])
    tool_calls:  list[dict] = state.get("tool_calls", [])
    answer: str             = state.get("synthesized_answer", "")

    # ── Criterion 1: all three agents appear in the trace ───────────────────
    agents_seen = {entry.get("agent") for entry in agent_trace}
    workflow_completed = _AGENT_NAMES.issubset(agents_seen)

    # ── Criterion 2: at least one web_search was executed ───────────────────
    tool_called = any(tc.get("tool") == "web_search" for tc in tool_calls)

    # ── Criterion 3: analyst produced a non-empty answer ────────────────────
    task_completed = bool(answer and answer.strip())

    # ── Score ────────────────────────────────────────────────────────────────
    passed = sum([workflow_completed, tool_called, task_completed])
    score  = passed * 33 + (1 if passed == 3 else 0)  # 100 when all pass

    result = {
        "workflow_completed": workflow_completed,
        "tool_called":        tool_called,
        "task_completed":     task_completed,
        "score":              score,
        "details": {
            "agents_seen":       sorted(agents_seen),
            "tool_calls_count":  len(tool_calls),
            "answer_length":     len(answer),
        },
    }

    logger.info(
        "[Evaluator] score=%d workflow=%s tool=%s task=%s",
        score, workflow_completed, tool_called, task_completed,
    )
    return result
