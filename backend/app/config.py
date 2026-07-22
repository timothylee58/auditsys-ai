"""Application configuration — Pydantic v2 BaseSettings with Azure Key Vault integration."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for AuditSys AI backend.

    Loads from .env file by default. When AZURE_KEY_VAULT_URI is set,
    secrets are pulled from Azure Key Vault using DefaultAzureCredential
    (works locally with `az login`, in production with managed identity).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_parse_none_str="",
    )

    # --- Supabase ---
    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_service_key: str | None = Field(default=None, validation_alias="SUPABASE_SERVICE_KEY")

    # --- Azure OpenAI ---
    azure_openai_api_key: str | None = Field(default=None, validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str | None = Field(
        default=None, validation_alias="AZURE_OPENAI_ENDPOINT"
    )
    azure_openai_deployment: str = Field(
        default="gpt-4o", validation_alias="AZURE_OPENAI_DEPLOYMENT"
    )
    azure_openai_embedding_deployment: str = Field(
        default="text-embedding-3-large",
        validation_alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    )
    azure_openai_api_version: str = Field(
        default="2024-02-01", validation_alias="AZURE_OPENAI_API_VERSION"
    )

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # --- Langfuse ---
    langfuse_public_key: str | None = Field(
        default=None, validation_alias="LANGFUSE_PUBLIC_KEY"
    )
    langfuse_secret_key: str | None = Field(
        default=None, validation_alias="LANGFUSE_SECRET_KEY"
    )
    langfuse_host: str = Field(
        default="http://localhost:3001", validation_alias="LANGFUSE_HOST"
    )

    # --- Security ---
    secret_key: str = Field(default="change-me-in-production", validation_alias="SECRET_KEY")
    confidence_threshold: float = Field(
        default=0.75, validation_alias="CONFIDENCE_THRESHOLD"
    )

    # --- Guardrails ---
    presidio_enabled: bool = Field(default=True, validation_alias="PRESIDIO_ENABLED")

    # --- Azure Key Vault ---
    azure_key_vault_uri: str | None = Field(
        default=None, validation_alias="AZURE_KEY_VAULT_URI"
    )

    # --- CORS ---
    allowed_origins_raw: str = Field(
        default="http://localhost:3000", validation_alias="ALLOWED_ORIGINS"
    )

    @property
    def allowed_origins(self) -> list[str]:
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        return [o.strip() for o in self.allowed_origins_raw.split(",") if o.strip()]

    @model_validator(mode="after")
    def _pull_keyvault_secrets(self) -> "Settings":
        """If AZURE_KEY_VAULT_URI is configured, overlay secrets from Key Vault."""
        if not self.azure_key_vault_uri:
            return self

        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=self.azure_key_vault_uri, credential=credential)

            # Map of Key Vault secret names → Settings field names
            secret_mapping: dict[str, str] = {
                "supabase-url": "supabase_url",
                "supabase-service-key": "supabase_service_key",
                "azure-openai-api-key": "azure_openai_api_key",
                "azure-openai-endpoint": "azure_openai_endpoint",
                "redis-url": "redis_url",
                "langfuse-public-key": "langfuse_public_key",
                "langfuse-secret-key": "langfuse_secret_key",
                "secret-key": "secret_key",
            }

            for vault_name, field_name in secret_mapping.items():
                try:
                    secret = client.get_secret(vault_name)
                    if secret.value:
                        object.__setattr__(self, field_name, secret.value)
                except Exception:
                    # Secret not found in vault — use env/default
                    pass

        except ImportError:
            # azure-identity or azure-keyvault-secrets not installed
            pass

        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()


settings = get_settings()
