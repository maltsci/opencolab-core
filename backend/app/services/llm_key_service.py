import httpx
from openai import AsyncOpenAI

from app.schemas.admin import LLMKeyCreate
from app.services.llm_service import should_bypass_proxy_for_api_base

_ANTHROPIC_VERSION = "2023-06-01"


def _build_async_client(api_base: str | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=15.0,
        trust_env=not should_bypass_proxy_for_api_base(api_base),
    )


def _normalize_completion_probe_model(model: str | None) -> str | None:
    if not model:
        return None
    if model.startswith(("openai/", "litellm/")):
        return model.split("/", 1)[1]
    return model


async def test_llm_key_config(
    payload: LLMKeyCreate,
    test_model: str | None = None,
) -> dict[str, str | bool]:
    provider = payload.provider.lower()
    api_base = payload.api_base.strip() if payload.api_base else None

    if provider in {"litellm", "openai"}:
        http_client = _build_async_client(api_base)
        client = AsyncOpenAI(
            api_key=payload.key,
            base_url=api_base,
            http_client=http_client,
        )
        try:
            response = await client.models.list()
            model_count = len(response.data)
            probe_model = _normalize_completion_probe_model(test_model)
            if not probe_model and response.data:
                probe_model = getattr(response.data[0], "id", None)

            if not probe_model:
                return {
                    "ok": True,
                    "message": (
                        f"Connection successful. {model_count} model(s) listed. "
                        "Completion probe skipped because no model was available."
                    ),
                }

            try:
                await client.chat.completions.create(
                    model=probe_model,
                    messages=[{"role": "user", "content": "Reply with ok."}],
                    max_tokens=8,
                )
            except Exception as exc:
                return {
                    "ok": False,
                    "message": (
                        f"Connected and listed {model_count} model(s), but the "
                        f"completion probe for '{probe_model}' failed: {exc}"
                    ),
                }

            return {
                "ok": True,
                "message": (
                    f"Connection successful. {model_count} model(s) listed. "
                    f"Completion probe succeeded with '{probe_model}'."
                ),
            }
        finally:
            await http_client.aclose()

    if provider == "ollama":
        base_url = (api_base or "http://localhost:11434").rstrip("/")
        async with _build_async_client(base_url) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            return {
                "ok": True,
                "message": f"Connection successful. {len(models)} model(s) listed.",
            }

    if provider == "anthropic":
        base_url = (api_base or "https://api.anthropic.com").rstrip("/")
        headers = {
            "x-api-key": payload.key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }
        async with _build_async_client(base_url) as client:
            response = await client.get(f"{base_url}/v1/models", headers=headers)
            response.raise_for_status()
            models = response.json().get("data", [])
            return {
                "ok": True,
                "message": f"Connection successful. {len(models)} model(s) listed.",
            }

    raise ValueError(f"Unsupported provider: {payload.provider}")
