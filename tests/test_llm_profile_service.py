import pytest

from app.services import llm_profile_service


pytestmark = pytest.mark.asyncio


async def test_fetch_models_returns_sorted_model_ids(monkeypatch):
    async def fake_list_models(*args, **kwargs):
        return ["glm-5", "kimi-k2.5"]

    monkeypatch.setattr(llm_profile_service, "_list_models_for_provider", fake_list_models)

    result = await llm_profile_service.fetch_models(
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        api_key="sk-test",
    )

    assert result == ["glm-5", "kimi-k2.5"]


async def test_test_model_marks_profile_unhealthy_on_completion_failure(monkeypatch):
    async def fake_probe(*args, **kwargs):
        raise RuntimeError("ReadTimeout")

    monkeypatch.setattr(llm_profile_service, "_probe_completion", fake_probe)

    result = await llm_profile_service.test_model(
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        api_key="sk-test",
        model="openai/glm-5",
    )

    assert result["ok"] is False
    assert result["status"] == "model_unhealthy"
