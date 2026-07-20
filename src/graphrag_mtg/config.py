"""Application settings loaded from the environment (and an optional .env).

Settings are read case-insensitively from environment variables. See
`.env.example` for the full list. Nothing here requires a running
service — importing this module is always safe.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the GraphRAG MTG pipeline.

    Attributes:
        neo4j_uri: Bolt URI of the Neo4j instance.
        neo4j_user: Neo4j username.
        neo4j_password: Neo4j password (also consumed by docker-compose).
        llm_provider: Which API serves extraction/generation calls —
            ``"anthropic"`` (default, ADR-003) or ``"openai"``.
        llm_model: Default LLM model id for extraction/generation phases.
        anthropic_api_key: API key for the default LLM provider (Claude).
        openai_api_key: API key for the alternative OpenAI provider.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="please-change-me")

    llm_provider: str = Field(default="anthropic")
    llm_model: str = Field(default="claude-opus-4-8")
    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance built from the environment."""
    return Settings()
