import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings

# Backend root (parent of app/)
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _env_files() -> tuple[str, ...]:
    """Return .env files in load order (later files override earlier ones).

    Looks in project root (opencolab/) and backend/. Uses OPENCOLAB_ENV for .env.{env}.
    """
    env_name = os.environ.get("OPENCOLAB_ENV", "dev")
    project_root = _BACKEND_ROOT.parent
    candidates = [
        project_root / ".env",
        project_root / f".env.{env_name}",
        _BACKEND_ROOT / ".env",
        _BACKEND_ROOT / f".env.{env_name}",
    ]
    return tuple(str(p) for p in candidates if p.exists())


class Settings(BaseSettings):
    # Application
    app_name: str = "OpenColab Core"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    api_key_encryption_secret: str | None = None

    # Database: set OPENCOLAB_DATABASE_URL, or POSTGRES_USER + POSTGRES_PASSWORD (+ optional POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT)
    database_url: str = ""
    postgres_user: str = Field(default="", validation_alias="POSTGRES_USER")
    postgres_password: str = Field(default="", validation_alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="opencolab", validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "opencolab_chunks"

    # Embedding
    embedding_model: str = "BAAI/bge-m3"
    embedding_provider: Literal["local", "siliconflow"] = "local"
    embedding_fallback_provider: Literal["none", "local", "siliconflow"] = (
        "none"
    )
    embedding_local_model_path: str | None = None
    embedding_local_files_only: bool = True
    siliconflow_api_key: str | None = None
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_embedding_model: str = "BAAI/bge-large-zh-v1.5"

    # LLM
    llm_model: str = "gpt-4o-mini"
    llm_api_base: str | None = None
    llm_proxy: str | None = None
    llm_response_max_tokens: int = 1600

    # File storage
    upload_dir: str = "./uploads"
    skill_pack_dir: str = "./skill-packs"
    max_file_size_mb: int = 50
    pdf_parse_timeout_seconds: float = 180.0
    pdf_pps_enabled: bool = False
    pdf_pps_jobs_url: str = ""
    pdf_pps_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPENCOLAB_PDF_PPS_API_KEY",
            "PPS_LOCAL_API_KEY",
            "LOCAL_MODEL_SERVICE_TOKEN",
        ),
    )
    pdf_pps_timeout_seconds: float = 300.0
    pdf_pps_poll_interval_seconds: float = 3.0
    pdf_marker_enabled: bool = False
    pdf_marker_device: str | None = None
    pdf_marker_dtype: str | None = None
    pdf_marker_preload_enabled: bool = False
    worker_max_concurrent: int = 1

    # Exact-identifier bibliographic metadata lookup. Disabled by default so
    # air-gapped deployments never make unexpected outbound requests.
    bibliographic_lookup_enabled: bool = False
    bibliographic_auto_apply_enabled: bool = False
    bibliographic_lookup_contact_email: str | None = None

    # RAG
    chunk_size: int = 512
    chunk_overlap: int = 64
    rag_top_k: int = 5

    # LLM API key (optional, can also use OPENAI_API_KEY etc.)
    llm_api_key: str | None = None

    # Worker URL (for query-time embedding via the document processing worker)
    worker_url: str = "http://localhost:8001"

    # Codex agent runtime sidecar. Credentials and model are resolved from the
    # active LLM Profile first, then the legacy OPENCOLAB_LLM_* settings.
    codex_runtime_enabled: bool = True
    codex_runtime_url: str = "http://codex-sandbox:8102"
    codex_runtime_api_key: str | None = None
    codex_runtime_timeout_seconds: int = 1800
    codex_runtime_default_sandbox: str = "workspace-write"
    codex_runtime_workspace_dir: str | None = None
    codex_runtime_sandbox_workspace_dir: str | None = None

    # Initial admin password (required on first run, used to seed the admin account)
    admin_password: str | None = None

    model_config = {"env_prefix": "OPENCOLAB_", "env_file": _env_files(), "extra": "ignore"}

    @model_validator(mode="after")
    def resolve_database_url(self) -> "Settings":
        env_name = os.environ.get("OPENCOLAB_ENV", "dev")
        if env_name not in {"dev", "test"} and self.secret_key == "change-me-in-production":
            raise ValueError("Set OPENCOLAB_SECRET_KEY before running outside dev/test.")
        if self.database_url and self.database_url.strip():
            return self
        if self.postgres_user and self.postgres_password:
            from urllib.parse import quote_plus

            user = quote_plus(self.postgres_user)
            password = quote_plus(self.postgres_password)
            self.database_url = (
                f"postgresql+asyncpg://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
            return self
        raise ValueError(
            "Set OPENCOLAB_DATABASE_URL or POSTGRES_USER + POSTGRES_PASSWORD in .env. "
            "Example: postgresql+asyncpg://user:password@localhost:5432/dbname"
        )


settings = Settings()
