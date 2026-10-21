"""Typed configuration — the ONE place that reads environment variables (and `.env`)."""

from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # --- data source ---
    data_source: Literal["intervals", "fixtures"] = "intervals"
    intervals_api_key: str | None = None
    intervals_athlete_id: str = "0"
    """"0" means "the owner of the API key"."""
    athlete_timezone: str = "America/Toronto"
    fixture_path: str | None = None

    # --- models: "provider:model" (see llm.build_model) ---
    coach_model: str = "ollama:qwen3:14b"
    judge_model: str = "ollama:qwen3:14b"
    ollama_base_url: str = "http://localhost:11434"

    # --- observability ---
    phoenix_collector_endpoint: str | None = None
    phoenix_project: str = "running-coach"

    # --- HTTP server ---
    port: int = 3000


@lru_cache
def get_settings() -> Settings:
    # Export .env into os.environ too, so SDKs that read their own variables
    # (ANTHROPIC_API_KEY, PHOENIX_*) see the same configuration. Real env vars win.
    load_dotenv()
    return Settings()
