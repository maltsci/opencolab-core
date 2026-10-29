import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.models.llm_key import LLMKey
from app.models.llm_profile import LLMProfile
from app.models.system_config import SystemConfig

logger = logging.getLogger(__name__)

# Keys that can be managed at runtime via the admin UI.
# Maps config key -> (env var name, default from Settings).
RUNTIME_KEYS: dict[str, tuple[str, str | None]] = {
    "llm_model": ("OPENCOLAB_LLM_MODEL", settings.llm_model),
    "llm_model_override": ("OPENCOLAB_LLM_MODEL_OVERRIDE", None),
    "llm_api_base": ("OPENCOLAB_LLM_API_BASE", settings.llm_api_base),
    "llm_api_key": ("OPENCOLAB_LLM_API_KEY", None),
    "llm_key_id": ("OPENCOLAB_LLM_KEY_ID", None),
    "active_llm_profile_id": ("OPENCOLAB_ACTIVE_LLM_PROFILE_ID", None),
    "llm_proxy": ("OPENCOLAB_LLM_PROXY", settings.llm_proxy),
    "embedding_model": ("OPENCOLAB_EMBEDDING_MODEL", settings.embedding_model),
    "upload_dir": ("OPENCOLAB_UPLOAD_DIR", settings.upload_dir),
    "max_file_size_mb": ("OPENCOLAB_MAX_FILE_SIZE_MB", str(settings.max_file_size_mb)),
    "chunk_size": ("OPENCOLAB_CHUNK_SIZE", str(settings.chunk_size)),
    "chunk_overlap": ("OPENCOLAB_CHUNK_OVERLAP", str(settings.chunk_overlap)),
    "rag_top_k": ("OPENCOLAB_RAG_TOP_K", str(settings.rag_top_k)),
    "bibliographic_lookup_enabled": (
        "OPENCOLAB_BIBLIOGRAPHIC_LOOKUP_ENABLED",
        str(settings.bibliographic_lookup_enabled).lower(),
    ),
    "bibliographic_auto_apply_enabled": (
        "OPENCOLAB_BIBLIOGRAPHIC_AUTO_APPLY_ENABLED",
        str(settings.bibliographic_auto_apply_enabled).lower(),
    ),
    "bibliographic_lookup_contact_email": (
        "OPENCOLAB_BIBLIOGRAPHIC_LOOKUP_CONTACT_EMAIL",
        settings.bibliographic_lookup_contact_email,
    ),
}


async def _get_db_or_env_value(key: str, db: AsyncSession) -> str | None:
    env_var, default = RUNTIME_KEYS[key]

    result = await db.execute(select(SystemConfig.value).where(SystemConfig.key == key))
    db_val = result.scalar_one_or_none()
    if db_val is not None and db_val != "":
        return db_val

    env_val = os.environ.get(env_var)
    if env_val is not None and env_val != "":
        return env_val

    return default


async def get_active_llm_profile(db: AsyncSession) -> LLMProfile | None:
    profile_id = await _get_db_or_env_value("active_llm_profile_id", db)
    if not profile_id:
        return None

    result = await db.execute(select(LLMProfile).where(LLMProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        logger.warning(
            "Configured active_llm_profile_id %s was not found; falling back",
            profile_id,
        )
    return profile


async def get_runtime_value(key: str, db: AsyncSession) -> str | None:
    """Resolve a runtime config value with priority: DB > env var > .env.{env} > .env."""
    if key not in RUNTIME_KEYS:
        return None

    if key == "llm_model":
        model_override = await _get_db_or_env_value("llm_model_override", db)
        if model_override:
            return model_override

        active_profile = await get_active_llm_profile(db)
        if active_profile is not None and active_profile.model:
            return active_profile.model

    if key == "llm_api_base":
        active_profile = await get_active_llm_profile(db)
        if active_profile is not None and active_profile.api_base:
            return active_profile.api_base

    if key == "llm_api_base":
        llm_key_id = await _get_db_or_env_value("llm_key_id", db)
        if llm_key_id:
            result = await db.execute(select(LLMKey).where(LLMKey.id == llm_key_id))
            key_record = result.scalar_one_or_none()
            if key_record is not None and key_record.api_base:
                return key_record.api_base

    return await _get_db_or_env_value(key, db)


async def get_all_runtime_config(db: AsyncSession) -> dict[str, str | None]:
    """Get all runtime config values with resolved priority."""
    config = {}
    for key in RUNTIME_KEYS:
        config[key] = await get_runtime_value(key, db)
    return config


def _mask_key(key: str | None, show: int = 4) -> str:
    if not key:
        return "<none>"
    if len(key) <= show * 2:
        return key[:show] + "***"
    return key[:show] + "***" + key[-show:]


async def get_runtime_llm_api_key(db: AsyncSession) -> str | None:
    """Resolve the effective LLM API key.

    Priority:
    1. Active profile key
    2. Selected legacy key from llm_key_id
    3. Raw llm_api_key runtime value
    4. Provider-specific environment variables handled by LiteLLM
    """
    from app.core.security import decrypt_api_key

    active_profile = await get_active_llm_profile(db)
    if active_profile is not None:
        key = decrypt_api_key(active_profile.encrypted_key)
        logger.info(
            "LLM key resolved: source=active_profile profile_id=%s profile_name=%r masked=%s",
            active_profile.id,
            active_profile.name,
            _mask_key(key),
        )
        return key

    llm_key_id = await _get_db_or_env_value("llm_key_id", db)
    if llm_key_id:
        result = await db.execute(select(LLMKey).where(LLMKey.id == llm_key_id))
        key = result.scalar_one_or_none()
        if key is not None:
            resolved = decrypt_api_key(key.encrypted_key)
            logger.info(
                "LLM key resolved: source=legacy_key key_id=%s masked=%s",
                llm_key_id,
                _mask_key(resolved),
            )
            return resolved
        logger.warning(
            "Configured llm_key_id %s was not found; falling back", llm_key_id
        )

    raw_key = await get_runtime_value("llm_api_key", db)
    if raw_key:
        logger.info(
            "LLM key resolved: source=runtime_config masked=%s", _mask_key(raw_key)
        )
    else:
        logger.warning(
            "LLM key resolved: source=none (no profile, no legacy key, no runtime config)"
        )
    return raw_key


async def set_runtime_value(key: str, value: str | None, db: AsyncSession) -> None:
    """Save a runtime config value to the database."""
    if key not in RUNTIME_KEYS:
        raise ValueError(f"Unknown config key: {key}")

    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = value
    else:
        db.add(SystemConfig(key=key, value=value))

    await db.flush()


async def set_runtime_values(values: dict[str, str | None], db: AsyncSession) -> None:
    """Save multiple runtime config values to the database."""
    for key, value in values.items():
        await set_runtime_value(key, value, db)
    await db.commit()


async def is_setup_complete(db: AsyncSession) -> bool:
    """Check if initial setup has an explicit LLM configuration."""
    result = await db.execute(
        select(SystemConfig).where(
            SystemConfig.key.in_(("llm_model", "llm_key_id", "active_llm_profile_id")),
            SystemConfig.value.isnot(None),
            SystemConfig.value != "",
        )
    )
    if result.scalars().first() is not None:
        return True

    if os.environ.get("OPENCOLAB_ACTIVE_LLM_PROFILE_ID"):
        return True

    if os.environ.get("OPENCOLAB_LLM_MODEL"):
        return True

    if os.environ.get("OPENCOLAB_LLM_API_BASE") or os.environ.get(
        "OPENCOLAB_LLM_API_KEY"
    ):
        return True

    if settings.llm_model != Settings.model_fields["llm_model"].default:
        return True

    return bool(settings.llm_api_base or settings.llm_api_key)
