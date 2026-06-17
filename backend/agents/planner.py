"""
MARS-Lite — Planner Agent.

Responsibility: Decompose the user's query into 2–3 ordered, atomic subtasks.

Simplified from MARS:
  - Removed inner retry loop (single attempt with fallback)
  - Kept @trace_agent decorator and usage tracking unchanged
"""
import json
import logging
import re

from backend.agents.base import BaseAgent
from backend.llm import get_provider
from backend.observability.tracer import trace_agent
from backend.orchestration.state import AgentState
from backend.config.settings import settings
from backend.agents.prompts import PLANNER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    name = "planner"
    description = "Decomposes queries into ordered research subtasks"

    def __init__(self):
        self.llm = get_provider(
            model=settings.planner_model,
            temperature=0.0,
            max_tokens=512,
        )

    @trace_agent("planner")
    async def run(self, state: AgentState) -> dict:
        query = state["query"]
        logger.info("[Planner] Decomposing query: %s", query[:80])

        try:
            raw, usage = await self.llm.invoke_with_usage(PLANNER_SYSTEM_PROMPT, query)
            subtasks = self._parse_subtasks(raw)
        except Exception as exc:
            logger.warning("[Planner] Failed, falling back to single subtask: %s", exc)
            subtasks = [query]
            usage = {"model": self.llm.model, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "latency_ms": 0}

        logger.info("[Planner] Generated %d subtasks", len(subtasks))

        return {
            "subtasks": subtasks,
            "current_subtask_index": 0,
            "llm_usage": [{"agent": "planner", **usage}],
            "agent_trace": [
                self._trace("plan_created", {"query": query, "subtasks": subtasks})
            ],
        }

    @staticmethod
    def _parse_subtasks(raw: str) -> list[str]:
        """Extract JSON array from LLM output (handles markdown code fences)."""
        cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip()

        # Find first [...] block
        match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
        content_to_parse = match.group() if match else cleaned

        try:
            arr = json.loads(content_to_parse)
        except Exception:
            import ast
            try:
                if not content_to_parse.strip().startswith('['):
                    content_to_parse = f"[{content_to_parse}]"
                arr = ast.literal_eval(content_to_parse)
            except Exception:
                arr = [content_to_parse]

        if not isinstance(arr, list) or len(arr) == 0:
            raise ValueError("Expected non-empty JSON array")

        return [str(s).strip() for s in arr if s]
