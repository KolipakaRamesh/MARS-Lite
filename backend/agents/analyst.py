"""
MARS-Lite — Analyst Agent.

Responsibility: Synthesize all raw research chunks into a single, coherent,
structured markdown answer.

Simplified from MARS:
  - Removed iteration_count / retry logic entirely
  - Removed ANALYST_RETRY_SYSTEM_PROMPT and feedback injection
  - Single-pass synthesis only
"""
import logging

from backend.agents.base import BaseAgent
from backend.llm import get_provider
from backend.observability.tracer import trace_agent
from backend.orchestration.state import AgentState
from backend.config.settings import settings
from backend.agents.prompts import ANALYST_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    name = "analyst"
    description = "Synthesizes raw research into a structured, grounded answer"

    def __init__(self):
        self.llm = get_provider(
            model=settings.analyst_model,
            temperature=0.3,
            max_tokens=1024,
        )

    @trace_agent("analyst")
    async def run(self, state: AgentState) -> dict:
        logger.info("[Analyst] Synthesizing research")

        raw_research = state.get("raw_research", [])
        if not raw_research:
            return self._error_state("No research data to synthesize")

        research_block = "\n\n".join(raw_research)
        query = state["query"]

        user_msg = (
            f"ORIGINAL QUERY:\n{query}\n\n"
            f"RAW RESEARCH NOTES:\n{research_block}\n\n"
            f"Synthesize a complete answer now."
        )

        model = state.get("analyst_model") or settings.analyst_model
        answer, usage = await self.llm.invoke_with_usage(ANALYST_SYSTEM_PROMPT, user_msg, model=model)

        return {
            "synthesized_answer": answer,
            "llm_usage": [{"agent": "analyst", **usage}],
            "agent_trace": [
                self._trace("synthesis_complete", {
                    "answer_length":    len(answer),
                    "research_chunks":  len(raw_research),
                })
            ],
        }
