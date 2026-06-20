"""
MARS — OpenRouter LLM Provider (Async).

Uses the OpenAI-compatible API endpoint exposed by OpenRouter via AsyncOpenAI.
Supports every model available on openrouter.ai with zero code changes.
Retry logic via tenacity handles transient 429 / 5xx errors.
"""
import logging
import time
import asyncio
from typing import List, Dict, Tuple

from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from backend.llm.provider import LLMProvider
from backend.config.settings import settings

logger = logging.getLogger(__name__)


class OpenRouterProvider(LLMProvider):
    """
    OpenAI-compatible async client pointed at OpenRouter.

    Args:
        model:       OpenRouter model ID (e.g. "meta-llama/llama-3.1-8b-instruct")
        temperature: Sampling temperature (0.0 = deterministic)
        max_tokens:  Max tokens in the completion
    """

    def __init__(
        self,
        model: str = "meta-llama/llama-3.1-8b-instruct",
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def invoke(self, system_prompt: str, user_message: str, model: str = None) -> str:
        """Single-turn convenience wrapper."""
        return await self.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            model=model,
        )

    async def chat(self, system_prompt: str, messages: List[Dict[str, str]], model: str = None) -> str:
        """Multi-turn call — full message history passed to the model."""
        content, _ = await self.chat_with_usage(system_prompt, messages, model=model)
        return content

    async def chat_with_usage(
        self, system_prompt: str, messages: List[Dict[str, str]], model: str = None
    ) -> Tuple[str, dict]:
        """
        Multi-turn call that also returns a live usage record from OpenRouter.

        Returns:
            (content_str, usage_dict) where usage_dict contains:
                model, prompt_tokens, completion_tokens, total_tokens, latency_ms
        """
        model = model or self.model
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        t0 = time.perf_counter()
        response = await self._call_with_retry(full_messages, model=model)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)

        usage_record = {
            "model":             model,
            "prompt_tokens":     getattr(usage, "prompt_tokens",     0) if usage else 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
            "total_tokens":      getattr(usage, "total_tokens",      0) if usage else 0,
            "latency_ms":        latency_ms,
        }

        logger.debug(
            "OpenRouter [%s] prompt=%d completion=%d total=%d latency=%.0fms",
            model,
            usage_record["prompt_tokens"],
            usage_record["completion_tokens"],
            usage_record["total_tokens"],
            latency_ms,
        )
        return content.strip(), usage_record

    async def invoke_with_usage(self, system_prompt: str, user_message: str, model: str = None) -> Tuple[str, dict]:
        """Single-turn call that also returns usage data."""
        return await self.chat_with_usage(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            model=model,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _call_with_retry(self, messages: List[Dict[str, str]], model: str = None):
        model = model or self.model
        return await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            extra_headers={
                "HTTP-Referer": "https://github.com/mars-agent",
                "X-Title": "MARS Multi-Agent System",
            },
        )
