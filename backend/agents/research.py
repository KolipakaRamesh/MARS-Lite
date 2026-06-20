"""
MARS-Lite — Research Agent.

Responsibility: Execute a single subtask using a ReAct (Reason+Act) loop.
Only tool available: web_search.

Simplified from MARS:
  - Removed LongTermMemory dependency entirely
  - Removed memory retrieval and context injection
  - Added structured tool_calls tracking for the UI dashboard
  - @trace_agent decorator and ReAct loop unchanged
"""
import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

from backend.agents.base import BaseAgent
from backend.llm import get_provider
from backend.observability.tracer import trace_agent, push_sse_event
from backend.orchestration.state import AgentState
from backend.tools.registry import ToolRegistry
from backend.config.settings import settings
from backend.agents.prompts import RESEARCH_REACT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    name = "research"
    description = "Executes subtasks via ReAct web_search loop"

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self.llm = get_provider(
            model=settings.research_model,
            temperature=0.2,
            max_tokens=1024,
        )
        self.max_steps = settings.max_react_steps

    @trace_agent("research")
    async def run(self, state: AgentState) -> dict:
        idx     = state["current_subtask_index"]
        subtask = state["subtasks"][idx]
        session_id = state.get("session_id")
        step_mode = state.get("step_mode", False)
        model = state.get("research_model") or settings.research_model

        logger.info("[Research] Subtask %d/%d: %s", idx + 1, len(state["subtasks"]), subtask[:80])

        result, usage, tool_calls = await self._react_loop(
            subtask=subtask,
            session_id=session_id,
            subtask_index=idx,
            step_mode=step_mode,
            model=model,
        )

        return {
            "raw_research":          [f"=== Subtask {idx + 1}: {subtask} ===\n{result}"],
            "current_subtask_index": idx + 1,
            "tool_calls":            tool_calls,
            "llm_usage":             [{"agent": "research", **usage}],
            "agent_trace":           [
                self._trace("subtask_complete", {
                    "subtask_index": idx,
                    "subtask":       subtask,
                    "result_length": len(result),
                    "tool_calls":    len(tool_calls),
                })
            ],
        }

    # ------------------------------------------------------------------
    # ReAct Loop
    # ------------------------------------------------------------------

    async def _react_loop(
        self, subtask: str, session_id: str, subtask_index: int, step_mode: bool = False, model: str = None
    ) -> tuple[str, dict, list]:
        """
        Multi-turn conversation implementing the ReAct pattern.
        Returns (answer_str, aggregated_usage_dict, tool_calls_list).
        """
        system = RESEARCH_REACT_SYSTEM_PROMPT

        messages = [{"role": "user", "content": subtask}]

        # Aggregate token usage across all steps
        agg_usage = {
            "model":             model or self.llm.model,
            "prompt_tokens":     0,
            "completion_tokens": 0,
            "total_tokens":      0,
            "latency_ms":        0.0,
        }
        tool_calls: list[dict] = []

        for step in range(self.max_steps):
            response, step_usage = await self.llm.chat_with_usage(system, messages, model=model)
            agg_usage["prompt_tokens"]     += step_usage.get("prompt_tokens", 0)
            agg_usage["completion_tokens"] += step_usage.get("completion_tokens", 0)
            agg_usage["total_tokens"]      += step_usage.get("total_tokens", 0)
            agg_usage["latency_ms"]        += step_usage.get("latency_ms", 0)

            messages.append({"role": "assistant", "content": response})

            # Extract intermediate thought
            thought = response.split("Action:", 1)[0].replace("Thought:", "").strip()

            # Check if agent reached a conclusion
            if "Final Answer:" in response:
                answer = response.split("Final Answer:", 1)[-1].strip()
                logger.debug("[Research] Final Answer at step %d", step + 1)
                push_sse_event(session_id, "react_step", {
                    "subtask_index": subtask_index,
                    "step":          step + 1,
                    "thought":       thought,
                    "final_answer":  answer,
                })
                return answer, agg_usage, tool_calls

            # Parse and execute tool call
            tool_name, tool_input = self._parse_action(response)

            if tool_name is None:
                logger.warning("[Research] Could not parse Action at step %d", step + 1)
                messages.append({
                    "role":    "user",
                    "content": "Please follow the format: Thought / Action / Action Input, then Final Answer.",
                })
                continue

            # Stream intermediate thought and action details
            push_sse_event(session_id, "react_step", {
                "subtask_index": subtask_index,
                "step":          step + 1,
                "thought":       thought,
                "tool":          tool_name,
                "tool_input":    tool_input,
            })

            # Check if step-by-step debugger mode is active
            if step_mode:
                logger.info("[Research] Pausing for user approval for session %s, tool: %s", session_id, tool_name)
                # Stream pending approval
                push_sse_event(session_id, "step_pending", {
                    "subtask_index": subtask_index,
                    "step":          step + 1,
                    "tool":          tool_name,
                    "tool_input":    tool_input,
                })
                
                from backend.observability.tracer import register_approval_event, clear_approval_event
                evt = asyncio.Event()
                register_approval_event(session_id, evt)
                await evt.wait()
                clear_approval_event(session_id)
                logger.info("[Research] Approval received, resuming execution for session %s", session_id)

            # Execute tool and time it
            t0 = time.perf_counter()
            observation = await self.tool_registry.call(tool_name, tool_input)
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)

            # Record the tool call for the UI
            tool_calls.append({
                "tool":        tool_name,
                "input":       tool_input,
                "output":      observation[:500],  # truncate for UI display
                "duration_ms": duration_ms,
                "timestamp":   datetime.now(timezone.utc).isoformat(),
            })

            # Stream observation detail
            push_sse_event(session_id, "react_observation", {
                "subtask_index": subtask_index,
                "step":          step + 1,
                "observation":   observation[:500],
            })

            messages.append({
                "role":    "user",
                "content": f"Observation: {observation}\n\nContinue your research.",
            })

        logger.warning("[Research] Max steps reached, returning best-effort result")
        return self._extract_best_effort(messages), agg_usage, tool_calls

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_action(text: str) -> tuple[Optional[str], str]:
        """Extract (tool_name, tool_input) from a ReAct-formatted response."""
        action_match = re.search(r"Action:\s*(.+?)(?:\n|$)", text)
        input_match  = re.search(r"Action Input:\s*(.+?)(?:\n|$)", text, re.DOTALL)

        if not action_match:
            return None, ""

        tool_name  = action_match.group(1).strip()
        tool_input = input_match.group(1).strip() if input_match else ""
        return tool_name, tool_input

    @staticmethod
    def _extract_best_effort(messages: list[dict]) -> str:
        """When max steps exceeded, return the last assistant message."""
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                return msg["content"]
        return "Research incomplete: no results gathered."
