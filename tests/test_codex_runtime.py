import pytest
from httpx import AsyncClient

from app.core.security import encrypt_api_key
from app.models.llm_profile import LLMProfile
from app.models.system_config import SystemConfig
from app.services.codex_runtime import resolve_codex_runtime_profile

pytestmark = pytest.mark.asyncio


async def test_codex_runtime_prefers_active_llm_profile(db):
    profile = LLMProfile(
        name="Lab GLM",
        provider="openai",
        api_base="https://llm.example.test/v1/",
        encrypted_key=encrypt_api_key("sk-profile"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.flush()
    db.add(SystemConfig(key="active_llm_profile_id", value=profile.id))
    db.add(SystemConfig(key="llm_model", value="openai/legacy-model"))
    db.add(SystemConfig(key="llm_api_base", value="https://legacy.example.test/v1/"))
    db.add(SystemConfig(key="llm_api_key", value="sk-legacy"))
    await db.commit()

    resolved = await resolve_codex_runtime_profile(db)

    assert resolved.source == "active_llm_profile"
    assert resolved.provider == "openai"
    assert resolved.model == "openai/glm-5"
    assert resolved.api_base == "https://llm.example.test/v1/"
    assert resolved.api_key == "sk-profile"


async def test_codex_status_endpoint_does_not_expose_api_key(
    client: AsyncClient,
    auth_headers: dict,
    db,
):
    profile = LLMProfile(
        name="Lab GLM",
        provider="openai",
        api_base="https://llm.example.test/v1/",
        encrypted_key=encrypt_api_key("sk-profile"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.flush()
    db.add(SystemConfig(key="active_llm_profile_id", value=profile.id))
    await db.commit()

    response = await client.get(
        "/api/v1/agent-runtime/codex/status",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "active_llm_profile"
    assert payload["model"] == "openai/glm-5"
    assert payload["api_base"] == "https://llm.example.test/v1/"
    assert "api_key" not in payload
    assert "sk-profile" not in response.text
