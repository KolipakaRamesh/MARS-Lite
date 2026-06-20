"""
MARS-Lite — Lightweight Local Observability Tracer.

Replaces the Opik integration with a zero-dependency local tracer that:
  - Records structured span data for every agent run
  - Persists spans to data/traces.json
  - Exposes spans via the /traces API endpoint
  - Streams agent_start / agent_end events during SSE execution

The @trace_agent decorator API is unchanged — agents need zero modification.
"""
import json
import logging
import time
import functools
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# ── Storage ───────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
TRACES_FILE = DATA_DIR / "traces.json"


def _load_traces() -> list:
    """Read all stored traces from disk."""
    try:
        if TRACES_FILE.exists():
            return json.loads(TRACES_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read traces file: %s", exc)
    return []


def _save_trace(span: dict) -> None:
    """Append a completed span to the traces file."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        traces = _load_traces()
        traces.append(span)
        # Keep only the last 100 traces to avoid unbounded growth
        traces = traces[-100:]
        TRACES_FILE.write_text(json.dumps(traces, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not save trace: %s", exc)


def get_all_traces() -> list:
    """Public API: return all stored traces (used by /traces endpoint)."""
    return _load_traces()


def clear_traces() -> None:
    """Clear all stored traces."""
    try:
        TRACES_FILE.write_text("[]", encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not clear traces: %s", exc)


# ── In-memory SSE event queue (populated during graph execution) ──────────────
# request_id → list of events waiting to be streamed
_sse_queues: dict[str, list] = {}


def register_sse_session(request_id: str) -> None:
    """Called before graph execution to set up the event queue."""
    _sse_queues[request_id] = []


def pop_sse_events(request_id: str) -> list:
    """Drain and return all pending SSE events for a request."""
    events = _sse_queues.get(request_id, [])
    _sse_queues[request_id] = []
    return events


def cleanup_sse_session(request_id: str) -> None:
    """Remove the queue after streaming is done."""
    _sse_queues.pop(request_id, None)


def _push_event(request_id: str | None, event_type: str, data: dict) -> None:
    """Push an SSE event into the queue if a session is active."""
    if request_id and request_id in _sse_queues:
        _sse_queues[request_id].append({"event": event_type, "data": data})


# ── Decorator ─────────────────────────────────────────────────────────────────

def trace_agent(span_name: str) -> Callable:
    """
    Decorator for agent run() methods.

    Captures:
        - agent name, start/end timestamps, duration
        - token counts from llm_usage in the returned state patch
        - status (success / error)

    Pushes agent_start and agent_end events to the SSE queue (if active).
    Persists the completed span to data/traces.json.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(self, state, *args, **kwargs):
            request_id = state.get("session_id")
            start_time = datetime.now(timezone.utc)
            t0 = time.perf_counter()

            # ── agent_start event ─────────────────────────────────────────────
            _push_event(request_id, "agent_start", {
                "agent":      span_name,
                "timestamp":  start_time.isoformat(),
                "query":      state.get("query", ""),
                "subtask_index": state.get("current_subtask_index", 0),
                "memory_context_tokens": state.get("memory_context_tokens", 0),
            })

            status = "success"
            result = {}
            try:
                result = await fn(self, state, *args, **kwargs)
                return result
            except Exception as exc:
                status = "error"
                logger.error("[%s] Agent error: %s", span_name, exc)
                raise
            finally:
                end_time = datetime.now(timezone.utc)
                duration_ms = round((time.perf_counter() - t0) * 1000, 1)

                # Extract token counts from the agent's returned llm_usage
                usage_entries = result.get("llm_usage", [])
                tokens_in  = sum(u.get("prompt_tokens", 0)     for u in usage_entries)
                tokens_out = sum(u.get("completion_tokens", 0) for u in usage_entries)
                model_name = usage_entries[0].get("model", "") if usage_entries else ""

                span = {
                    "request_id":  request_id,
                    "agent_name":  span_name,
                    "start_time":  start_time.isoformat(),
                    "end_time":    end_time.isoformat(),
                    "duration_ms": duration_ms,
                    "status":      status,
                    "tokens_in":   tokens_in,
                    "tokens_out":  tokens_out,
                    "total_tokens": tokens_in + tokens_out,
                    "model":       model_name,
                }

                # Persist to disk
                _save_trace(span)

                # ── agent_end event ───────────────────────────────────────────
                _push_event(request_id, "agent_end", {
                    **span,
                    "memory_context_tokens": state.get("memory_context_tokens", 0),
                    # Also include tool_calls if research agent produced any
                    "tool_calls": result.get("tool_calls", []),
                    "subtasks": result.get("subtasks"),
                    "synthesized_answer": result.get("synthesized_answer"),
                })

        return wrapper
    return decorator
