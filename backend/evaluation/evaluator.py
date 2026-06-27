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
import re

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
          "tool_use_health":    bool,
          "answer_structured":   bool,
          "source_grounded":     bool,
          "execution_efficient": bool,
          "score":              int   (0 - 100)
          "details":            dict  — per-criterion explanation
        }
    """
    agent_trace: list[dict] = state.get("agent_trace", [])
    tool_calls:  list[dict] = state.get("tool_calls", [])
    answer: str             = state.get("synthesized_answer", "")

    # ── 1. Workflow Completed ────────────────────────────────────────────────
    agents_seen = {entry.get("agent") for entry in agent_trace if entry.get("agent")}
    workflow_completed = _AGENT_NAMES.issubset(agents_seen)

    # ── 2. Tool Use Health ───────────────────────────────────────────────────
    has_tools = len(tool_calls) > 0
    no_tool_errors = True
    for tc in tool_calls:
        out = str(tc.get("output", "")).lower()
        if "failed" in out or "error" in out:
            no_tool_errors = False
            break
    tool_use_health = has_tools and no_tool_errors

    # ── 3. Answer Structured ──────────────────────────────────────────────────
    answer_stripped = answer.strip() if answer else ""
    has_headers = bool(re.search(r"^##?\s+", answer_stripped, re.MULTILINE))
    answer_structured = len(answer_stripped) > 300 and has_headers

    # ── 4. Source Grounded (Citations) ────────────────────────────────────────
    if not has_tools:
        source_grounded = True
        citations_count = 0
    else:
        # Check if answer contains footnotes [1] or markdown links [name](url)
        md_links = re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", answer)
        footnotes = re.findall(r"\[\d+\]", answer)
        citations_count = len(md_links) + len(footnotes)
        source_grounded = citations_count > 0

    # ── 5. Execution Efficient (Loop Free) ───────────────────────────────────
    tool_queries = [tc.get("input", "").strip().lower() for tc in tool_calls if tc.get("tool") == "web_search"]
    unique_queries = set(tool_queries)
    execution_efficient = len(tool_queries) == len(unique_queries)

    # ── Score calculation (20 points per check, max 100) ─────────────────────
    passed = sum([
        workflow_completed,
        tool_use_health,
        answer_structured,
        source_grounded,
        execution_efficient
    ])
    score = passed * 20

    result = {
        "workflow_completed": workflow_completed,
        "tool_use_health":    tool_use_health,
        "answer_structured":   answer_structured,
        "source_grounded":     source_grounded,
        "execution_efficient": execution_efficient,
        "score":              score,
        "details": {
            "agents_seen":           sorted(agents_seen),
            "tool_calls_count":      len(tool_calls),
            "unique_searches_count": len(unique_queries),
            "citations_count":       citations_count,
            "answer_length":         len(answer_stripped),
        },
    }

    logger.info(
        "[Evaluator] score=%d workflow=%s tool_health=%s structure=%s grounded=%s efficient=%s",
        score, workflow_completed, tool_use_health, answer_structured, source_grounded, execution_efficient,
    )
    return result

