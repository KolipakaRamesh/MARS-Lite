"""
MARS-Lite — FastAPI Application.

Endpoints:
  POST /run               — blocking run, returns full result JSON
  GET  /run/stream        — SSE stream with real-time agent events
  GET  /health            — readiness check
  GET  /traces            — return stored observability traces
  DELETE /traces          — clear all traces
  GET  /memory            — return current simple memory contents
  DELETE /memory          — clear memory

All Convex, Opik, and heartbeat logic has been removed.
"""
import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.agents.planner  import PlannerAgent
from backend.agents.analyst  import AnalystAgent
from backend.agents.research import ResearchAgent
from backend.orchestration.graph  import build_graph
from backend.orchestration.state  import initial_state
from backend.tools.registry       import build_default_registry
from backend.observability.tracer import (
    get_all_traces, clear_traces,
    register_sse_session, pop_sse_events, cleanup_sse_session,
)
from backend.evaluation.evaluator import evaluate
import backend.memory.simple_memory as simple_memory
from backend.config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Shared singletons ─────────────────────────────────────────────────────────
_graph = None

BASE_DIR     = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend" / "dist"

# Ensure data directory exists on startup
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize graph on startup."""
    global _graph
    logger.info("MARS-Lite starting up...")

    tool_registry = build_default_registry()
    planner  = PlannerAgent()
    research = ResearchAgent(tool_registry)
    analyst  = AnalystAgent()

    _graph = build_graph(planner, research, analyst)
    logger.info("MARS-Lite ready ✓")
    yield
    logger.info("MARS-Lite shutting down")


app = FastAPI(
    title="MARS-Lite",
    description="Educational multi-agent research pipeline with full observability",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query:      str = Field(..., min_length=3, description="The research question")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class QueryResponse(BaseModel):
    session_id:         str
    query:              str
    answer:             str
    subtasks:           list[str]
    tool_calls:         list[dict] = []
    llm_usage:          list[dict] = []
    agent_trace:        list[dict] = []
    evaluation:         dict       = {}
    memory:             dict       = {}
    error:              str | None = None


# ── Internal pipeline runner ──────────────────────────────────────────────────

async def _run_pipeline(session_id: str, query: str) -> dict:
    """Execute the full agent pipeline and return the final state."""
    if _graph is None:
        raise RuntimeError("Graph not initialized")

    state = initial_state(query, session_id)
    final_state = dict(state)

    async for output in _graph.astream(state):
        for node_name, node_output in output.items():
            logger.info("[Graph] Node completed: %s", node_name)
            final_state = {**final_state, **node_output}

    return final_state


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "system": "MARS-Lite", "graph_ready": _graph is not None}


@app.post("/run", response_model=QueryResponse)
async def run_query(req: QueryRequest):
    """Blocking endpoint — runs the full pipeline and returns when done."""
    if _graph is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    try:
        final_state = await _run_pipeline(req.session_id, req.query)
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    # Store memory and evaluate
    mem     = simple_memory.store(req.query)
    result  = evaluate(final_state)

    return QueryResponse(
        session_id=final_state["session_id"],
        query=final_state["query"],
        answer=final_state.get("synthesized_answer", ""),
        subtasks=final_state.get("subtasks", []),
        tool_calls=final_state.get("tool_calls", []),
        llm_usage=final_state.get("llm_usage", []),
        agent_trace=final_state.get("agent_trace", []),
        evaluation=result,
        memory=mem,
        error=final_state.get("error"),
    )


@app.get("/run/stream")
async def run_stream(
    query:      str = Query(..., min_length=3),
    session_id: str = Query(default_factory=lambda: str(uuid.uuid4())),
):
    """
    SSE endpoint — streams agent events in real time.

    Events:
      agent_start     — agent just began executing
      agent_end       — agent finished (includes token counts + tool_calls)
      tool_call       — a tool was invoked (sent within agent_end)
      result          — final answer + evaluation + memory
      error           — pipeline error
    """
    if _graph is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    async def event_stream():
        register_sse_session(session_id)

        try:
            # Run the pipeline as a background task so we can poll the queue
            pipeline_task = asyncio.create_task(
                _run_pipeline(session_id, query)
            )

            # Drain events while the pipeline is running
            while not pipeline_task.done():
                await asyncio.sleep(0.15)
                for evt in pop_sse_events(session_id):
                    yield _sse_event(evt["event"], evt["data"])

            # Drain any remaining events after pipeline finishes
            for evt in pop_sse_events(session_id):
                yield _sse_event(evt["event"], evt["data"])

            # Get the result (raises if pipeline failed)
            final_state = await pipeline_task

            # Store memory and evaluate
            mem    = simple_memory.store(query)
            result = evaluate(final_state)

            # Emit the final result event
            yield _sse_event("result", {
                "session_id":  final_state["session_id"],
                "query":       final_state["query"],
                "answer":      final_state.get("synthesized_answer", ""),
                "subtasks":    final_state.get("subtasks", []),
                "tool_calls":  final_state.get("tool_calls", []),
                "llm_usage":   final_state.get("llm_usage", []),
                "agent_trace": final_state.get("agent_trace", []),
                "evaluation":  result,
                "memory":      mem,
            })

        except Exception as exc:
            logger.error("SSE pipeline error: %s", exc, exc_info=True)
            yield _sse_event("error", {"detail": str(exc)})
        finally:
            cleanup_sse_session(session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Observability Endpoints ───────────────────────────────────────────────────

@app.get("/traces")
def list_traces():
    """Return all stored agent traces from data/traces.json."""
    return {"traces": get_all_traces()}


@app.delete("/traces")
def delete_traces():
    """Clear all stored traces."""
    clear_traces()
    return {"status": "cleared"}


# ── Memory Endpoints ──────────────────────────────────────────────────────────

@app.get("/memory")
def get_memory():
    """Return current simple memory contents."""
    return simple_memory.retrieve()


@app.delete("/memory")
def delete_memory():
    """Clear all stored memory."""
    simple_memory.clear()
    return {"status": "cleared"}


# ── Serve Frontend ────────────────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning("Frontend not built. Run 'npm run build' in frontend/")
