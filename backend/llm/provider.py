"""
MARS — Abstract LLM Provider.

Design: thin interface so any backend (OpenRouter, OpenAI, Anthropic, local)
can be swapped without touching agent code.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple


class LLMProvider(ABC):
    """Minimal contract every LLM backend must implement."""

    @abstractmethod
    async def invoke(self, system_prompt: str, user_message: str, model: str = None) -> str:
        """Single-turn call. Returns the assistant content string."""
        ...

    @abstractmethod
    async def chat(self, system_prompt: str, messages: List[Dict[str, str]], model: str = None) -> str:
        """
        Multi-turn call.
        messages: [{"role": "user"|"assistant", "content": "..."}]
        Returns the next assistant content string.
        """
        ...

    @abstractmethod
    async def chat_with_usage(self, system_prompt: str, messages: List[Dict[str, str]], model: str = None) -> Tuple[str, dict]:
        """Multi-turn call that also returns usage data."""
        ...

    @abstractmethod
    async def invoke_with_usage(self, system_prompt: str, user_message: str, model: str = None) -> Tuple[str, dict]:
        """Single-turn call that also returns usage data."""
        ...
