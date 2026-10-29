import httpx
from openai import AsyncOpenAI

from app.services.llm_service import (
    normalize_litellm_model_name,
    should_bypass_proxy_for_api_base,
)

_ANTHROPIC_VERSION = "2023-06-01"


def _build_async_client(api_base: str | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=15.0,
        trust_env=not should_bypass_proxy_for_api_base(api_base),
    )


def _normalize_completion_probe_model(model: str | None, api_base: str | None) -> str | None:
    normalized = normalize_litellm_model_name(model, api_base)
    if not normalized:
        return None
    if normalized.startswith(("openai/", "litellm/")):
        return normalized.split("/", 1)[1]
    return normalized


async def _list_models_for_provider(
    provider: str,
    api_base: str | None,
    api_key: str,
) -> list[str]:
    normalized_provider = provider.lower()
    normalized_api_base = api_base.strip() if api_base else None

    if normalized_provider in {"litellm", "openai"}:
        http_client = _build_async_client(normalized_api_base)
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=normalized_api_base,
            http_client=http_client,
        )
        try:
            response = await client.models.list()
            return [
                model_id
                for model_id in (getattr(model, "id", None) for model in response.data)
                if model_id
            ]
        finally:
            await http_client.aclose()

    if normalized_provider == "ollama":
        base_url = (normalized_api_base or "http://localhost:11434").rstrip("/")
        async with _build_async_client(base_url) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            return [
                model["name"]
                for model in response.json().get("models", [])
                if model.get("name")
            ]

    if normalized_provider == "anthropic":
        base_url = (normalized_api_base or "https://api.anthropic.com").rstrip("/")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }
        async with _build_async_client(base_url) as client:
            response = await client.get(f"{base_url}/v1/models", headers=headers)
            response.raise_for_status()
            return [
                model["id"]
                for model in response.json().get("data", [])
                if model.get("id")
            ]

    raise ValueError(f"Unsupported provider: {provider}")


async def fetch_models(
    provider: str,
    api_base: str | None,
    api_key: str,
) -> list[str]:
    models = await _list_models_for_provider(provider, api_base, api_key)
    return sorted(dict.fromkeys(models))


async def _probe_completion(
    provider: str,
    api_base: str | None,
    api_key: str,
    model: str,
) -> None:
    normalized_provider = provider.lower()
    normalized_api_base = api_base.strip() if api_base else None
    probe_model = _normalize_completion_probe_model(model, normalized_api_base)
    if not probe_model:
        raise ValueError("Model is required for completion probe")

    if normalized_provider in {"litellm", "openai"}:
        http_client = _build_async_client(normalized_api_base)
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=normalized_api_base,
            http_client=http_client,
        )
        try:
            await client.chat.completions.create(
                model=probe_model,
                messages=[{"role": "user", "content": "Reply with ok."}],
                max_tokens=8,
            )
            return
        finally:
            await http_client.aclose()

    if normalized_provider == "ollama":
        base_url = (normalized_api_base or "http://localhost:11434").rstrip("/")
        async with _build_async_client(base_url) as client:
            response = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": probe_model,
                    "messages": [{"role": "user", "content": "Reply with ok."}],
                    "stream": False,
                },
            )
            response.raise_for_status()
            return

    if normalized_provider == "anthropic":
        base_url = (normalized_api_base or "https://api.anthropic.com").rstrip("/")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        async with _build_async_client(base_url) as client:
            response = await client.post(
                f"{base_url}/v1/messages",
                headers=headers,
                json={
                    "model": probe_model,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "Reply with ok."}],
                },
            )
            response.raise_for_status()
            return

    raise ValueError(f"Unsupported provider: {provider}")


async def test_connection(
    provider: str,
    api_base: str | None,
    api_key: str,
) -> dict[str, str | bool | list[str]]:
    models = await fetch_models(provider, api_base, api_key)
    return {
        "ok": True,
        "status": "connection_ok",
        "message": f"Connection successful. {len(models)} model(s) listed.",
        "models": models,
    }


async def test_model(
    provider: str,
    api_base: str | None,
    api_key: str,
    model: str,
) -> dict[str, str | bool]:
    try:
        await _probe_completion(provider, api_base, api_key, model)
    except Exception as exc:
        return {
            "ok": False,
            "status": "model_unhealthy",
            "message": f"Completion probe for '{model}' failed: {exc}",
        }

    return {
        "ok": True,
        "status": "model_ready",
        "message": f"Model '{model}' is ready.",
    }
