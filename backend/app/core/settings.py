from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # CORS
    allowed_origins_raw: str = Field(default="http://localhost:3000", validation_alias="ALLOWED_ORIGINS")

    # Database
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/auditsys"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Azure OpenAI
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str | None = "gpt-4o"
    azure_openai_embedding_deployment: str | None = "text-embedding-3-large"
    azure_openai_api_version: str | None = "2024-02-01"

    # Supabase
    supabase_url: str | None = None
    supabase_service_key: str | None = None

    # Langfuse
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://localhost:3001"

    # Security
    secret_key: str = "change-me-in-production"
    confidence_threshold: float = 0.75

    # Guardrails
    presidio_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_parse_none_str="",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins_raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
