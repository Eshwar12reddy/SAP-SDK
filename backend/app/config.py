from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-120b"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    database_url: str = "postgresql://localhost:5432/brim_ai"
    jwt_secret: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    auto_create_schema: bool = False
    rate_limit_enabled: bool = True
    auth_rate_limit: str = "10/minute"
    request_timeout: float = Field(180, gt=0, le=600)
    openrouter_max_tokens: int = Field(131072, gt=0, le=131072)
    openrouter_context_window: int = Field(131072, gt=0, le=2_000_000)
    openrouter_context_safety_margin: int = Field(256, ge=0, le=16_384)
    openrouter_min_completion_tokens: int = Field(16, ge=1, le=1024)
    openrouter_greeting_max_tokens: int = Field(100, gt=0, le=131072)
    openrouter_simple_max_tokens: int = Field(300, gt=0, le=131072)
    openrouter_definition_max_tokens: int = Field(600, gt=0, le=131072)
    openrouter_technical_max_tokens: int = Field(1500, gt=0, le=131072)
    openrouter_comparison_max_tokens: int = Field(2000, gt=0, le=131072)
    openrouter_how_to_max_tokens: int = Field(2500, gt=0, le=131072)
    openrouter_troubleshooting_max_tokens: int = Field(3500, gt=0, le=131072)
    openrouter_scenario_max_tokens: int = Field(5000, gt=0, le=131072)
    openrouter_complex_max_tokens: int = Field(8000, gt=0, le=131072)
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )

    @field_validator("jwt_secret")
    @classmethod
    def _strong_jwt_secret(cls, value: str) -> str:
        placeholders = {"change-me", "changeme", "secret", "replace-with-a-long-random-secret"}
        if len(value) < 32 or value.strip().lower() in placeholders:
            raise ValueError(
                "JWT_SECRET must be set to a random value of at least 32 characters "
                "(generate one with: openssl rand -hex 32)"
            )
        return value

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
