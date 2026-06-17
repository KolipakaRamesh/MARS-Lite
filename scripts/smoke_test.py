"""Quick smoke test for MARS-Lite system — validates all modules load and core utilities work."""
import sys
sys.path.insert(0, '.')

from backend.config.settings import settings
from backend.llm import get_provider
from backend.orchestration.state import AgentState, initial_state
from backend.orchestration.router import route_after_research
from backend.orchestration.graph import build_graph
from backend.tools.registry import build_default_registry
from backend.tools.web_search import web_search
from backend.agents.base import BaseAgent
from backend.agents.planner import PlannerAgent
from backend.agents.analyst import AnalystAgent
from backend.agents.research import ResearchAgent

print("All MARS-Lite modules imported successfully")

# State factory
state = initial_state("What is quantum computing?", "test-session")
print(f"State factory test: session={state['session_id']}, query_len={len(state['query'])}")

# Tool registry
registry = build_default_registry()
tools = registry.list_tools()
print(f"Tool registry: {len(tools)} tools registered: {[t['name'] for t in tools]}")

# LLM provider factory (doesn't call API)
provider = get_provider(model="meta-llama/llama-3.2-3b-instruct", temperature=0.0)
print(f"LLM provider: {provider.model}")

print()
print("=" * 50)
print("MARS-Lite system validation PASSED")
print("=" * 50)

