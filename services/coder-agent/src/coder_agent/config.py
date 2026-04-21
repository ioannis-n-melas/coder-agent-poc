"""Config — read from env via pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model_server_url: str = Field(
        ...,
        description="Base URL of the OpenAI-compatible model server.",
    )
    model_server_audience: str | None = Field(
        default=None,
        description=(
            "Audience (usually the root Cloud Run URL) for minting a Google ID token "
            "when calling a private model-server. Unset locally."
        ),
    )
    model_name: str = Field(
        default="qwen2.5-coder-1.5b",
        description="Model identifier sent in the OpenAI request. Cosmetic for llama.cpp.",
    )

    gcp_project_id: str | None = Field(default=None)
    artifacts_bucket: str | None = Field(default=None)

    log_level: str = Field(default="INFO")

    request_timeout_seconds: int = Field(
        default=120,
        description="Timeout for a single model-server request.",
    )
    max_tokens_per_response: int = Field(default=1024)
    temperature: float = Field(default=0.2)

    @property
    def model_server_base(self) -> str:
        """Return the base URL without trailing slash, ensuring /v1 is present."""
        url = self.model_server_url.rstrip("/")
        if not url.endswith("/v1"):
            url = f"{url}/v1"
        return url


def get_settings() -> Settings:
    """Factory — Pydantic caches via module load, but tests can override this."""
    return Settings()  # type: ignore[call-arg]
