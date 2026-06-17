"""
MARS-Lite — Tool Registry.

Simplified: only web_search is registered.
The registry itself is unchanged — clean, minimal, explicit.
"""
import asyncio
from typing import Callable, Dict, Any, Union, Coroutine
import logging

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        fn: Union[Callable[[str], str], Callable[[str], Coroutine[Any, Any, str]]],
        description: str,
    ) -> None:
        """Register a tool by name."""
        self._tools[name] = {"fn": fn, "description": description}
        logger.debug("Tool registered: %s", name)

    async def call(self, name: str, input_str: str) -> str:
        """Execute a tool by name, handling both sync and async functions."""
        entry = self._tools.get(name)
        if not entry:
            return f"Tool '{name}' not found. Available tools: {list(self._tools.keys())}"

        fn = entry["fn"]
        try:
            if asyncio.iscoroutinefunction(fn):
                return await fn(input_str)
            else:
                return fn(input_str)
        except Exception as exc:
            logger.error("Error executing tool '%s': %s", name, exc)
            return f"Error executing tool '{name}': {str(exc)}"

    def list_tools(self) -> list[dict]:
        return [{"name": k, "description": v["description"]} for k, v in self._tools.items()]

    def tool_descriptions_for_prompt(self) -> str:
        return "\n".join(f"  - {t['name']}: {t['description']}" for t in self.list_tools())

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())


def build_default_registry() -> ToolRegistry:
    """Factory — builds registry with only web_search."""
    from backend.tools.web_search import web_search

    registry = ToolRegistry()
    registry.register(
        "web_search",
        web_search,
        "Search the web for recent information. Input: a search query string.",
    )
    return registry
