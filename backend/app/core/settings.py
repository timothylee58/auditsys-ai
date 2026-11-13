from functools import lru_cache

from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Secret fields eligible for override from Azure Key Vault when
# AZURE_KEY_VAULT_URI is set. Key Vault secret names use dashes
# (Key Vault forbids underscores); we map "azure-openai-api-key" ->
# "azure_openai_api_key" automatically.
_KEY_VAULT_FIELDS = [
    "supabase_url",
    "supabase_service_key",
    "supabase_jwt_secret",
    "azure_openai_api_key",
    "azure_openai_endpoint",
    "redis_url",
    "langfuse_public_key",
    "langfuse_secret_key",
    "secret_key",
]


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
    # Legacy HS256 project secret. Only needed for projects still issuing
    # symmetric tokens; modern projects verify via the JWKS endpoint and can
    # leave this unset.
    supabase_jwt_secret: str | None = None

    # Langfuse
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://localhost:3001"

    # Azure Key Vault (production secret source; local dev uses .env)
    azure_key_vault_uri: str | None = None

    # Security
    secret_key: str = "change-me-in-production"
    confidence_threshold: float = 0.75

    # Comma-separated user ids allowed to trigger privileged actions
    # (POST /evals/run). Empty = nobody — fail closed.
    admin_user_ids_raw: str = Field(default="", validation_alias="ADMIN_USER_IDS")

    # Abuse protection on token-burning endpoints
    query_rate_limit_per_minute: int = Field(default=30, validation_alias="QUERY_RATE_LIMIT_PER_MINUTE")
    upload_rate_limit_per_minute: int = Field(default=10, validation_alias="UPLOAD_RATE_LIMIT_PER_MINUTE")

    # Guardrails
    presidio_enabled: bool = True
    # spaCy model Presidio uses for NER. Must be installed in the image
    # (Dockerfile). en_core_web_sm is small and fast but weaker at PERSON
    # recall than en_core_web_lg; switch via PRESIDIO_SPACY_MODEL.
    presidio_spacy_model: str = Field(default="en_core_web_sm", validation_alias="PRESIDIO_SPACY_MODEL")

    # Audit-grade pipeline (claims -> cited spans -> verifier -> hash chain).
    # Off by default: the legacy retrieve/synthesise/validate graph stays the
    # live path until the new pipeline has been measured against the RAGAS gate.
    audit_grade_pipeline: bool = Field(default=False, validation_alias="AUDIT_GRADE_PIPELINE")
    # Smaller/cheaper deployment for the claim verifier. Falls back to the
    # main deployment when unset.
    azure_openai_verifier_deployment: str | None = Field(
        default=None, validation_alias="AZURE_OPENAI_VERIFIER_DEPLOYMENT"
    )
    # Agentic retrieval loop
    max_retrieval_rounds: int = Field(default=3, ge=1, le=6, validation_alias="MAX_RETRIEVAL_ROUNDS")
    min_evidence_spans: int = Field(default=1, ge=1, validation_alias="MIN_EVIDENCE_SPANS")
    min_span_similarity: float = Field(default=0.30, ge=0.0, le=1.0, validation_alias="MIN_SPAN_SIMILARITY")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_parse_none_str="",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins_raw.split(",") if o.strip()]

    @property
    def admin_user_ids(self) -> set[str]:
        return {o.strip() for o in self.admin_user_ids_raw.split(",") if o.strip()}


def _load_from_key_vault(settings: Settings) -> Settings:
    """Overlay secrets from Azure Key Vault using DefaultAzureCredential.

    Works unchanged locally (az login) and in production (managed identity)
    — no code path branches on environment, only on whether
    AZURE_KEY_VAULT_URI is set.
    """
    if not settings.azure_key_vault_uri:
        return settings

    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    client = SecretClient(vault_url=settings.azure_key_vault_uri, credential=DefaultAzureCredential())

    for field_name in _KEY_VAULT_FIELDS:
        secret_name = field_name.replace("_", "-")
        try:
            secret = client.get_secret(secret_name)
            setattr(settings, field_name, secret.value)
        except Exception as exc:  # noqa: BLE001 - a missing secret just keeps the env default
            logger.debug("key_vault_secret_missing name={} error={}", secret_name, exc)

    return settings


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    return _load_from_key_vault(settings)


settings = get_settings()
