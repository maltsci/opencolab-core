import pytest
from httpx import AsyncClient

from app.core.config import Settings, settings
from app.core.constants import ROLE_ADMIN, ROLE_PI, ROLE_RESEARCHER
from app.core.security import decrypt_api_key, encrypt_api_key
from app.models.llm_key import LLMKey
from app.models.llm_profile import LLMProfile
from app.services.runtime_config import get_runtime_llm_api_key, get_runtime_value

pytestmark = pytest.mark.asyncio


async def test_create_user(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/admin/users",
        json={"username": "newuser", "password": "pass123", "role": ROLE_RESEARCHER},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser"
    assert data["role"] == ROLE_RESEARCHER


async def test_create_user_duplicate(client: AsyncClient, auth_headers, admin_user):
    response = await client.post(
        "/api/v1/admin/users",
        json={"username": "testadmin", "password": "pass123"},
        headers=auth_headers,
    )
    assert response.status_code == 409


async def test_list_users(client: AsyncClient, auth_headers, admin_user):
    response = await client.get("/api/v1/admin/users", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


async def test_pi_can_list_users(client: AsyncClient, pi_headers, pi_user):
    response = await client.get("/api/v1/admin/users", headers=pi_headers)
    assert response.status_code == 200
    assert any(item["id"] == pi_user.id for item in response.json())


async def test_update_user(client: AsyncClient, auth_headers, researcher_user):
    response = await client.put(
        f"/api/v1/admin/users/{researcher_user.id}",
        json={"role": ROLE_PI},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["role"] == ROLE_PI


async def test_admin_can_update_admin_role(client: AsyncClient, auth_headers, admin_user):
    response = await client.put(
        f"/api/v1/admin/users/{admin_user.id}",
        json={"role": ROLE_ADMIN},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["role"] == ROLE_ADMIN


async def test_pi_can_promote_researcher_to_pi(client: AsyncClient, pi_headers, researcher_user):
    response = await client.put(
        f"/api/v1/admin/users/{researcher_user.id}",
        json={"role": ROLE_PI},
        headers=pi_headers,
    )
    assert response.status_code == 200
    assert response.json()["role"] == ROLE_PI


async def test_pi_cannot_update_admin_role(client: AsyncClient, pi_headers, admin_user):
    response = await client.put(
        f"/api/v1/admin/users/{admin_user.id}",
        json={"role": ROLE_RESEARCHER},
        headers=pi_headers,
    )
    assert response.status_code == 403


async def test_delete_user(client: AsyncClient, auth_headers, researcher_user):
    response = await client.delete(
        f"/api/v1/admin/users/{researcher_user.id}",
        headers=auth_headers,
    )
    assert response.status_code == 204


async def test_non_admin_forbidden(client: AsyncClient, researcher_headers):
    response = await client.get(
        "/api/v1/admin/users", headers=researcher_headers
    )
    assert response.status_code == 403


async def test_setup_status_complete_when_llm_model_is_set_via_env(
    client: AsyncClient,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setenv("OPENCOLAB_LLM_MODEL", "tianfu-basic")
    response = await client.get("/api/v1/admin/config/setup-status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"setup_complete": True}


async def test_setup_status_incomplete_without_explicit_llm_config(
    client: AsyncClient,
    auth_headers,
    monkeypatch,
):
    monkeypatch.delenv("OPENCOLAB_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENCOLAB_LLM_API_BASE", raising=False)
    monkeypatch.delenv("OPENCOLAB_LLM_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_model", Settings.model_fields["llm_model"].default)
    monkeypatch.setattr(settings, "llm_api_base", None)
    monkeypatch.setattr(settings, "llm_api_key", None)

    response = await client.get("/api/v1/admin/config/setup-status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"setup_complete": False}


async def test_create_llm_key_supports_api_base(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/admin/llm-keys",
        json={
            "provider": "litellm",
            "name": "Lab Gateway",
            "key": "sk-litellm-test",
            "api_base": "http://localhost:4000",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201

    list_response = await client.get("/api/v1/admin/llm-keys", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()[0]["api_base"] == "http://localhost:4000"


async def test_update_llm_key_supports_api_base_and_name(
    client: AsyncClient,
    auth_headers,
    db,
):
    key = LLMKey(
        provider="litellm",
        name="Old Gateway",
        encrypted_key=encrypt_api_key("sk-litellm-old"),
        api_base="http://localhost:4000",
    )
    db.add(key)
    await db.commit()

    response = await client.put(
        f"/api/v1/admin/llm-keys/{key.id}",
        json={
            "provider": "litellm",
            "name": "New Gateway",
            "api_base": "http://localhost:4001",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    await db.refresh(key)
    assert key.name == "New Gateway"
    assert key.api_base == "http://localhost:4001"
    assert decrypt_api_key(key.encrypted_key) == "sk-litellm-old"


async def test_update_llm_key_replaces_key_when_provided(
    client: AsyncClient,
    auth_headers,
    db,
):
    key = LLMKey(
        provider="litellm",
        name="Lab Gateway",
        encrypted_key=encrypt_api_key("sk-litellm-old"),
        api_base="http://localhost:4000",
    )
    db.add(key)
    await db.commit()

    response = await client.put(
        f"/api/v1/admin/llm-keys/{key.id}",
        json={
            "provider": "litellm",
            "name": "Lab Gateway",
            "api_base": "http://localhost:4000",
            "key": "sk-litellm-new",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    await db.refresh(key)
    assert decrypt_api_key(key.encrypted_key) == "sk-litellm-new"


async def test_get_config_includes_selected_llm_key_id(client: AsyncClient, auth_headers, db):
    key = LLMKey(
        provider="litellm",
        name="Lab Gateway",
        encrypted_key=encrypt_api_key("sk-litellm-test"),
    )
    db.add(key)
    await db.flush()

    from app.models.system_config import SystemConfig

    db.add(SystemConfig(key="llm_key_id", value=key.id))
    await db.commit()

    response = await client.get("/api/v1/admin/config", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["llm_key_id"] == key.id


async def test_setup_status_complete_when_llm_key_is_selected(
    client: AsyncClient,
    auth_headers,
    db,
    monkeypatch,
):
    monkeypatch.delenv("OPENCOLAB_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENCOLAB_LLM_API_BASE", raising=False)
    monkeypatch.delenv("OPENCOLAB_LLM_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_model", Settings.model_fields["llm_model"].default)
    monkeypatch.setattr(settings, "llm_api_base", None)
    monkeypatch.setattr(settings, "llm_api_key", None)

    key = LLMKey(
        provider="litellm",
        name="Lab Gateway",
        encrypted_key=encrypt_api_key("sk-litellm-test"),
    )
    db.add(key)
    await db.flush()

    from app.models.system_config import SystemConfig

    db.add(SystemConfig(key="llm_key_id", value=key.id))
    await db.commit()

    response = await client.get("/api/v1/admin/config/setup-status", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"setup_complete": True}


async def test_setup_status_complete_with_multiple_runtime_config_rows(
    client: AsyncClient,
    auth_headers,
    db,
    monkeypatch,
):
    monkeypatch.delenv("OPENCOLAB_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENCOLAB_LLM_API_BASE", raising=False)
    monkeypatch.delenv("OPENCOLAB_LLM_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_model", Settings.model_fields["llm_model"].default)
    monkeypatch.setattr(settings, "llm_api_base", None)
    monkeypatch.setattr(settings, "llm_api_key", None)

    from app.models.system_config import SystemConfig

    db.add(SystemConfig(key="llm_model", value="openai/test-model"))
    db.add(SystemConfig(key="llm_key_id", value="key-123"))
    await db.commit()

    response = await client.get("/api/v1/admin/config/setup-status", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"setup_complete": True}


async def test_get_runtime_config_prefers_selected_llm_key_api_base(
    client: AsyncClient,
    auth_headers,
    db,
):
    key = LLMKey(
        provider="litellm",
        name="Lab Gateway",
        encrypted_key=encrypt_api_key("sk-litellm-test"),
        api_base="http://localhost:4000",
    )
    db.add(key)
    await db.flush()

    from app.models.system_config import SystemConfig

    db.add(SystemConfig(key="llm_key_id", value=key.id))
    await db.commit()

    response = await client.get("/api/v1/admin/config", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["llm_api_base"] == "http://localhost:4000"


async def test_llm_key_test_endpoint_returns_service_result(
    client: AsyncClient,
    auth_headers,
    monkeypatch,
):
    from app.api import admin as admin_api

    async def fake_test_llm_key_config(payload, test_model=None):
        assert payload.provider == "litellm"
        assert payload.api_base == "http://localhost:4000"
        assert isinstance(test_model, str)
        assert test_model != ""
        return {"ok": True, "message": "Connection successful"}

    monkeypatch.setattr(admin_api, "test_llm_key_config", fake_test_llm_key_config)

    response = await client.post(
        "/api/v1/admin/llm-keys/test",
        json={
            "provider": "litellm",
            "name": "Lab Gateway",
            "api_base": "http://localhost:4000",
            "key": "sk-litellm-test",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Connection successful"}


async def test_llm_key_test_endpoint_passes_runtime_model_to_service(
    client: AsyncClient,
    auth_headers,
    monkeypatch,
    db,
):
    from app.api import admin as admin_api
    from app.models.system_config import SystemConfig

    db.add(SystemConfig(key="llm_model", value="openai/tianfu-basic"))
    await db.commit()

    async def fake_test_llm_key_config(payload, test_model=None):
        assert payload.provider == "litellm"
        assert test_model == "openai/tianfu-basic"
        return {"ok": True, "message": "Completion probe succeeded"}

    monkeypatch.setattr(admin_api, "test_llm_key_config", fake_test_llm_key_config)

    response = await client.post(
        "/api/v1/admin/llm-keys/test",
        json={
            "provider": "litellm",
            "name": "Lab Gateway",
            "api_base": "http://localhost:4000",
            "key": "sk-litellm-test",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Completion probe succeeded"}


async def test_can_persist_llm_profile_model(db):
    profile = LLMProfile(
        name="Legacy GLM",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-legacy"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    assert profile.id
    assert profile.name == "Legacy GLM"
    assert profile.model == "openai/glm-5"
    assert profile.status == "unknown"


async def test_llm_profile_model_is_registered_in_metadata():
    from app.core.database import Base

    table = Base.metadata.tables["llm_profiles"]

    assert "llm_profiles" in Base.metadata.tables
    assert table.c.model.nullable is False
    assert table.c.status.nullable is False


async def test_llm_profile_crud_persists_model_and_masks_key(
    client: AsyncClient,
    auth_headers,
):
    create_response = await client.post(
        "/api/v1/admin/llm-profiles",
        json={
            "name": "Healwrap GLM-5",
            "provider": "openai",
            "api_base": "https://llm-api.healwrap.cn/v1/",
            "key": "sk-glm",
            "model": "openai/glm-5",
        },
        headers=auth_headers,
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["model"] == "openai/glm-5"
    assert created["status"] == "unknown"
    assert created["masked_key"] == "****"

    list_response = await client.get("/api/v1/admin/llm-profiles", headers=auth_headers)

    assert list_response.status_code == 200
    profiles = list_response.json()
    assert len(profiles) == 1
    assert profiles[0]["id"] == created["id"]
    assert profiles[0]["model"] == "openai/glm-5"
    assert profiles[0]["status"] == "unknown"
    assert profiles[0]["masked_key"] == "****"


async def test_llm_profile_update_and_delete(
    client: AsyncClient,
    auth_headers,
    db,
):
    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.commit()

    update_response = await client.put(
        f"/api/v1/admin/llm-profiles/{profile.id}",
        json={
            "name": "Healwrap GLM-4.5",
            "provider": "openai",
            "api_base": "https://llm-api.healwrap.cn/v2/",
            "key": "sk-glm-new",
            "model": "openai/glm-4.5",
        },
        headers=auth_headers,
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["id"] == profile.id
    assert updated["name"] == "Healwrap GLM-4.5"
    assert updated["model"] == "openai/glm-4.5"

    list_response = await client.get("/api/v1/admin/llm-profiles", headers=auth_headers)
    profiles = list_response.json()
    assert profiles[0]["name"] == "Healwrap GLM-4.5"
    assert profiles[0]["api_base"] == "https://llm-api.healwrap.cn/v2/"
    assert profiles[0]["model"] == "openai/glm-4.5"

    delete_response = await client.delete(
        f"/api/v1/admin/llm-profiles/{profile.id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    final_list_response = await client.get(
        "/api/v1/admin/llm-profiles",
        headers=auth_headers,
    )
    assert final_list_response.status_code == 200
    assert final_list_response.json() == []


async def test_activate_llm_profile_updates_runtime_config(
    client: AsyncClient,
    auth_headers,
    db,
):
    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.commit()

    response = await client.post(
        f"/api/v1/admin/llm-profiles/{profile.id}/activate",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "active_llm_profile_id": profile.id,
    }

    config_response = await client.get("/api/v1/admin/config", headers=auth_headers)
    assert config_response.status_code == 200
    assert config_response.json()["active_llm_profile_id"] == profile.id


async def test_fetch_llm_profile_models_returns_service_result(
    client: AsyncClient,
    auth_headers,
    monkeypatch,
):
    from app.api import admin as admin_api

    async def fake_fetch_models(provider, api_base, api_key):
        assert provider == "openai"
        assert api_base == "https://llm-api.healwrap.cn/v1/"
        assert api_key == "sk-glm"
        return ["glm-5", "kimi-k2.5"]

    monkeypatch.setattr(admin_api, "fetch_models", fake_fetch_models)

    response = await client.post(
        "/api/v1/admin/llm-profiles/fetch-models",
        json={
            "provider": "openai",
            "api_base": "https://llm-api.healwrap.cn/v1/",
            "key": "sk-glm",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"models": ["glm-5", "kimi-k2.5"]}


async def test_fetch_llm_profile_models_uses_saved_profile_key_when_key_omitted(
    client: AsyncClient,
    auth_headers,
    db,
    monkeypatch,
):
    from app.api import admin as admin_api

    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm-saved"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.commit()

    async def fake_fetch_models(provider, api_base, api_key):
        assert provider == "openai"
        assert api_base == "https://llm-api.healwrap.cn/v1/"
        assert api_key == "sk-glm-saved"
        return ["glm-5", "kimi-k2.5"]

    monkeypatch.setattr(admin_api, "fetch_models", fake_fetch_models)

    response = await client.post(
        "/api/v1/admin/llm-profiles/fetch-models",
        json={
            "profile_id": profile.id,
            "provider": "openai",
            "api_base": "https://llm-api.healwrap.cn/v1/",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"models": ["glm-5", "kimi-k2.5"]}


async def test_test_llm_profile_connection_returns_service_result(
    client: AsyncClient,
    auth_headers,
    monkeypatch,
):
    from app.api import admin as admin_api

    async def fake_test_connection(provider, api_base, api_key):
        assert provider == "openai"
        assert api_base == "https://llm-api.healwrap.cn/v1/"
        assert api_key == "sk-glm"
        return {
            "ok": True,
            "status": "connection_ok",
            "message": "Connection successful. 2 model(s) listed.",
            "models": ["glm-5", "kimi-k2.5"],
        }

    monkeypatch.setattr(admin_api, "test_connection", fake_test_connection)

    response = await client.post(
        "/api/v1/admin/llm-profiles/test-connection",
        json={
            "provider": "openai",
            "api_base": "https://llm-api.healwrap.cn/v1/",
            "key": "sk-glm",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "connection_ok"


async def test_test_llm_profile_connection_uses_saved_profile_key_when_key_omitted(
    client: AsyncClient,
    auth_headers,
    db,
    monkeypatch,
):
    from app.api import admin as admin_api

    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm-saved"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.commit()

    async def fake_test_connection(provider, api_base, api_key):
        assert provider == "openai"
        assert api_base == "https://llm-api.healwrap.cn/v1/"
        assert api_key == "sk-glm-saved"
        return {
            "ok": True,
            "status": "connection_ok",
            "message": "Connection successful. 2 model(s) listed.",
            "models": ["glm-5", "kimi-k2.5"],
        }

    monkeypatch.setattr(admin_api, "test_connection", fake_test_connection)

    response = await client.post(
        "/api/v1/admin/llm-profiles/test-connection",
        json={
            "profile_id": profile.id,
            "provider": "openai",
            "api_base": "https://llm-api.healwrap.cn/v1/",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "connection_ok"


async def test_test_llm_profile_model_returns_service_result(
    client: AsyncClient,
    auth_headers,
    monkeypatch,
):
    from app.api import admin as admin_api

    async def fake_test_model(provider, api_base, api_key, model):
        assert provider == "openai"
        assert api_base == "https://llm-api.healwrap.cn/v1/"
        assert api_key == "sk-glm"
        assert model == "openai/glm-5"
        return {
            "ok": True,
            "status": "model_ready",
            "message": "Model 'openai/glm-5' is ready.",
        }

    monkeypatch.setattr(admin_api, "test_model", fake_test_model)

    response = await client.post(
        "/api/v1/admin/llm-profiles/test-model",
        json={
            "provider": "openai",
            "api_base": "https://llm-api.healwrap.cn/v1/",
            "key": "sk-glm",
            "model": "openai/glm-5",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "model_ready"


async def test_test_llm_profile_model_uses_saved_profile_key_when_key_omitted(
    client: AsyncClient,
    auth_headers,
    db,
    monkeypatch,
):
    from app.api import admin as admin_api

    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm-saved"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.commit()

    async def fake_test_model(provider, api_base, api_key, model):
        assert provider == "openai"
        assert api_base == "https://llm-api.healwrap.cn/v1/"
        assert api_key == "sk-glm-saved"
        assert model == "openai/glm-5"
        return {
            "ok": True,
            "status": "model_ready",
            "message": "Model 'openai/glm-5' is ready.",
        }

    monkeypatch.setattr(admin_api, "test_model", fake_test_model)

    response = await client.post(
        "/api/v1/admin/llm-profiles/test-model",
        json={
            "profile_id": profile.id,
            "provider": "openai",
            "api_base": "https://llm-api.healwrap.cn/v1/",
            "model": "openai/glm-5",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "model_ready"


async def test_runtime_prefers_active_profile_over_legacy_fields(db):
    from app.models.system_config import SystemConfig

    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.flush()

    db.add(SystemConfig(key="active_llm_profile_id", value=profile.id))
    db.add(SystemConfig(key="llm_model", value="openai/legacy-model"))
    db.add(SystemConfig(key="llm_api_base", value="https://legacy.example/v1/"))
    db.add(SystemConfig(key="llm_api_key", value="sk-legacy"))
    await db.commit()

    assert await get_runtime_value("llm_model", db) == "openai/glm-5"
    assert await get_runtime_value("llm_api_base", db) == "https://llm-api.healwrap.cn/v1/"
    assert await get_runtime_llm_api_key(db) == "sk-glm"


async def test_runtime_uses_model_override_when_present(db):
    from app.models.system_config import SystemConfig

    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.flush()

    db.add(SystemConfig(key="active_llm_profile_id", value=profile.id))
    db.add(SystemConfig(key="llm_model_override", value="openai/glm-5-air"))
    await db.commit()

    assert await get_runtime_value("llm_model", db) == "openai/glm-5-air"
