from dataclasses import dataclass
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_api_key
from app.services.runtime_config import (
    get_active_llm_profile,
    get_runtime_llm_api_key,
    get_runtime_value,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CodexRuntimeProfile:
    provider: str | None
    model: str | None
    api_base: str | None
    api_key: str | None
    source: str


class CodexRuntimeError(RuntimeError):
    """The codex sandbox rejected or failed the run, with its detail attached."""


def _runtime_headers() -> dict[str, str]:
    if not settings.codex_runtime_api_key:
        return {}
    return {"Authorization": f"Bearer {settings.codex_runtime_api_key}"}


async def resolve_codex_runtime_profile(db: AsyncSession) -> CodexRuntimeProfile:
    active_profile = await get_active_llm_profile(db)
    if active_profile is not None:
        return CodexRuntimeProfile(
            provider=active_profile.provider,
            model=active_profile.model,
            api_base=active_profile.api_base,
            api_key=decrypt_api_key(active_profile.encrypted_key),
            source="active_llm_profile",
        )

    return CodexRuntimeProfile(
        provider="openai",
        model=await get_runtime_value("llm_model", db),
        api_base=await get_runtime_value("llm_api_base", db),
        api_key=await get_runtime_llm_api_key(db),
        source="runtime_config",
    )


async def get_codex_runtime_status(db: AsyncSession) -> dict:
    profile = await resolve_codex_runtime_profile(db)
    if not settings.codex_runtime_enabled:
        return {
            "enabled": False,
            "available": False,
            "provider": profile.provider,
            "model": profile.model,
            "api_base": profile.api_base,
            "sandbox_url": settings.codex_runtime_url,
            "source": profile.source,
            "message": "Codex runtime is disabled.",
        }

    try:
        async with httpx.AsyncClient(
            timeout=5.0,
            headers=_runtime_headers(),
            trust_env=False,
        ) as client:
            response = await client.get(f"{settings.codex_runtime_url.rstrip('/')}/health")
            response.raise_for_status()
    except Exception as exc:
        return {
            "enabled": True,
            "available": False,
            "provider": profile.provider,
            "model": profile.model,
            "api_base": profile.api_base,
            "sandbox_url": settings.codex_runtime_url,
            "source": profile.source,
            "message": f"Codex runtime is not reachable: {exc}",
        }

    return {
        "enabled": True,
        "available": True,
        "provider": profile.provider,
        "model": profile.model,
        "api_base": profile.api_base,
        "sandbox_url": settings.codex_runtime_url,
        "source": profile.source,
        "message": "Codex runtime is reachable.",
    }


async def run_codex_runtime(
    *,
    prompt: str,
    db: AsyncSession,
    cwd: str | None = None,
    sandbox: str | None = None,
) -> dict:
    if not settings.codex_runtime_enabled:
        raise RuntimeError("Codex runtime is disabled.")

    profile = await resolve_codex_runtime_profile(db)
    payload = {
        "prompt": prompt,
        "cwd": cwd,
        "sandbox": sandbox or settings.codex_runtime_default_sandbox,
        "provider": profile.provider,
        "model": profile.model,
        "api_base": profile.api_base,
        "api_key": profile.api_key,
        "source": profile.source,
    }
    logger.info(
        "Starting codex run: model=%s api_base=%s sandbox=%s cwd=%s profile_source=%s",
        payload["model"],
        payload["api_base"],
        payload["sandbox"],
        cwd,
        profile.source,
    )
    async with httpx.AsyncClient(
        timeout=float(settings.codex_runtime_timeout_seconds),
        headers=_runtime_headers(),
        trust_env=False,
    ) as client:
        try:
            response = await client.post(
                f"{settings.codex_runtime_url.rstrip('/')}/run",
                json=payload,
            )
        except httpx.RequestError as exc:
            logger.error("Codex sandbox request failed: %s", exc)
            raise CodexRuntimeError(f"Codex sandbox is unreachable: {exc}") from exc
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                error_payload = response.json()
                if isinstance(error_payload, dict):
                    detail = str(error_payload.get("detail") or "").strip()
            except ValueError:
                detail = response.text.strip()
            logger.error(
                "Codex sandbox run failed: status=%s detail=%s",
                response.status_code,
                detail[:2000],
            )
            if detail:
                raise CodexRuntimeError(f"Codex runtime failed: {detail[:500]}") from exc
            raise CodexRuntimeError(
                f"Codex runtime failed with status {response.status_code}"
            ) from exc
        return response.json()
