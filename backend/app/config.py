from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    llm_heavy: str = "claude-opus-4-7"
    llm_light: str = "claude-haiku-4-5-20251001"
    llm_mid: str = "claude-sonnet-4-6"
    llm_budget_default: float = 5.00

    # Crypto
    fernet_key: str = ""

    # DB
    database_url: str = "postgresql+asyncpg://zwan:changeme@localhost:5432/zwan"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"

    # Ports
    backend_port: int = 8731
    frontend_port: int = 3000

    # Burp
    burp_api_url: str = "http://127.0.0.1:1337"
    burp_api_key: str = ""

    # Interactsh
    interactsh_server: str = ""
    interactsh_token: str = ""


settings = Settings()
