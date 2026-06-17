"""
MARS-Lite — Centralized settings via Pydantic BaseSettings.
Simplified: only the settings actually needed.
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── LLM (OpenRouter via OpenAI-compatible API) ────────────────────────────
    openrouter_api_key: str = Field(..., env="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── Agent Models ──────────────────────────────────────────────────────────
    planner_model:  str = "meta-llama/llama-3.2-3b-instruct"
    research_model: str = "meta-llama/llama-3.1-8b-instruct"
    analyst_model:  str = "meta-llama/llama-3.1-8b-instruct"

    # ── Orchestration ─────────────────────────────────────────────────────────
    max_react_steps: int = 3   # max ReAct steps per subtask

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Singleton — import this everywhere
settings = Settings()
