import logging
import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlparse

import httpx
import litellm
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

LLM_STREAM_TIMEOUT_SECONDS = 90.0
LLM_STREAM_CHUNK_TIMEOUT_SECONDS = 15.0
LLM_RESPONSE_MAX_TOKENS = 1600
MAX_CONTEXT_CHARS_PER_CHUNK = 1200


def _clip_chunk_text(text: str, limit: int = MAX_CONTEXT_CHARS_PER_CHUNK) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


class LLMRequestTimeoutError(RuntimeError):
    """Raised when an LLM request takes too long to start streaming."""


def normalize_litellm_model_name(
    model: str | None,
    api_base: str | None,
) -> str | None:
    """Normalize bare model names for common OpenAI-compatible endpoints."""
    if not model or "/" in model or not api_base:
        return model

    normalized_api_base = api_base.strip().lower()
    if (
        "ollama" in normalized_api_base
        or ":11434" in normalized_api_base
        or normalized_api_base.endswith("/api")
        or "/api/" in normalized_api_base
    ):
        return model

    return f"openai/{model}"


def should_bypass_proxy_for_api_base(api_base: str | None) -> bool:
    """Return True when the target API base is a local endpoint."""
    if not api_base:
        return False

    hostname = (urlparse(api_base).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


@asynccontextmanager
async def local_openai_compatible_client(
    api_base: str | None,
    api_key: str | None,
):
    """Yield an AsyncOpenAI client that bypasses env proxies for local endpoints."""
    if not should_bypass_proxy_for_api_base(api_base):
        yield None
        return

    http_client = httpx.AsyncClient(trust_env=False)
    client = AsyncOpenAI(
        api_key=api_key or "local-placeholder-key",
        base_url=api_base,
        http_client=http_client,
    )
    try:
        yield client
    finally:
        await http_client.aclose()


def build_prompt(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
    locale: str | None = None,
    project_instructions: str | None = None,
) -> list[dict]:
    """Build the messages list for the LLM call."""
    messages = []
    language_instruction = get_response_language_instruction(locale)
    instructions_block = (
        f"\n\nProject instructions (follow these for all answers in this project):\n"
        f"{project_instructions.strip()}"
        if project_instructions and project_instructions.strip()
        else ""
    )

    if chunks:
        context_text = "\n\n---\n\n".join(
            f"[Chunk {i+1}]\n{_clip_chunk_text(c['text'])}"
            for i, c in enumerate(chunks)
        )
        system_content = (
            "You are a concise AI research assistant.\n"
            "Use only the selected or linked document content below.\n"
            "Do not say you cannot access the files.\n"
            "Do not describe the context as user-provided snippets; describe it as selected documents, linked documents, or retrieved document content.\n"
            "Answer briefly first, and mention uncertainty when the retrieved document content is insufficient.\n\n"
            f"{language_instruction}\n\n"
            f"Retrieved content from selected documents:\n{context_text}"
            f"{instructions_block}"
        )
    else:
        system_content = (
            "You are a concise AI research assistant. "
            "Answer the user's question briefly and directly. "
            "If the user refers to an uploaded file but no document content is provided, "
            "ask them to select the file in the sidebar before sending their message. "
            f"{language_instruction}"
            f"{instructions_block}"
        )

    messages.append({"role": "system", "content": system_content})

    if history:
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": question})
    return messages


def get_response_language_instruction(locale: str | None) -> str:
    normalized_locale = (locale or "").strip().lower()
    if normalized_locale.startswith("zh"):
        return "Respond in Simplified Chinese."
    return "Respond in English."


def _read_stream_value(data: Any, key: str) -> Any:
    if isinstance(data, dict):
        return data.get(key)
    return getattr(data, key, None)


def _coerce_text(value: Any, visited: set[int] | None = None) -> str:
    if visited is None:
        visited = set()

    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return ""

    value_id = id(value)
    if value_id in visited:
        return ""
    visited.add(value_id)

    if isinstance(value, list):
        parts = [_coerce_text(item, visited) for item in value]
        return "".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in (
            "text",
            "content",
            "output_text",
            "reasoning_content",
            "value",
        ):
            coerced = _coerce_text(value.get(key), visited)
            if coerced:
                return coerced
        return ""

    for key in (
        "text",
        "content",
        "output_text",
        "reasoning_content",
        "value",
    ):
        coerced = _coerce_text(getattr(value, key, None), visited)
        if coerced:
            return coerced
    return ""


def _extract_stream_content(chunk: Any) -> str | None:
    choices = _read_stream_value(chunk, "choices")
    if not choices:
        return None

    delta = _read_stream_value(choices[0], "delta")
    if delta is None:
        return None

    for key in ("content", "text", "output_text", "reasoning_content"):
        content = _coerce_text(_read_stream_value(delta, key))
        if content:
            return content
    return None


def _extract_completion_content(response: Any) -> str:
    choices = _read_stream_value(response, "choices")
    if not choices:
        logger.warning("LLM non-stream response contained no choices")
        return ""

    message = _read_stream_value(choices[0], "message")
    if message is None:
        logger.warning("LLM non-stream response contained no message payload")
        return ""

    for key in ("content", "text", "output_text", "reasoning_content"):
        raw_value = _read_stream_value(message, key)
        content = _coerce_text(raw_value)
        if content:
            logger.info(
                "LLM non-stream content extracted from key=%s raw_type=%s len=%d",
                key,
                type(raw_value).__name__,
                len(content),
            )
            return content

    fallback_content = _coerce_text(message)
    logger.warning(
        "LLM non-stream message used fallback coercion raw_type=%s len=%d",
        type(message).__name__,
        len(fallback_content),
    )
    return fallback_content


async def _non_stream_completion(
    messages: list[dict],
    model: str,
    api_base: str | None,
    api_key: str | None,
    max_tokens: int,
) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
    }
    if api_base:
        kwargs["api_base"] = api_base
    effective_api_key = api_key or settings.llm_api_key
    if effective_api_key:
        kwargs["api_key"] = effective_api_key

    async with local_openai_compatible_client(
        api_base,
        effective_api_key,
    ) as local_client:
        if local_client is not None:
            kwargs["client"] = local_client
        response = await litellm.acompletion(**kwargs)
    return _extract_completion_content(response)


async def stream_llm_response(
    messages: list[dict],
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]:
    """Stream tokens from the LLM."""
    effective_api_base = api_base or settings.llm_api_base
    effective_model = normalize_litellm_model_name(
        model or settings.llm_model,
        effective_api_base,
    )
    effective_api_key = api_key or settings.llm_api_key

    has_key = bool(effective_api_key)
    logger.info(
        "LLM stream start: model=%r api_base=%r has_key=%s input_api_key_provided=%s",
        effective_model,
        effective_api_base,
        has_key,
        bool(api_key),
    )

    effective_max_tokens = max_tokens or settings.llm_response_max_tokens
    kwargs: dict = {
        "model": effective_model,
        "messages": messages,
        "stream": True,
        "max_tokens": effective_max_tokens,
    }
    if effective_api_base:
        kwargs["api_base"] = effective_api_base
    if effective_api_key:
        kwargs["api_key"] = effective_api_key

    async with local_openai_compatible_client(
        effective_api_base,
        effective_api_key,
    ) as local_client:
        if local_client is not None:
            kwargs["client"] = local_client
        try:
            response = await asyncio.wait_for(
                litellm.acompletion(**kwargs),
                timeout=LLM_STREAM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise LLMRequestTimeoutError(
                f"LLM request timed out after {int(LLM_STREAM_TIMEOUT_SECONDS)} seconds."
            ) from exc

        stream_iterator = response.__aiter__()
        yielded_any = False

        while True:
            try:
                chunk = await asyncio.wait_for(
                    anext(stream_iterator),
                    timeout=LLM_STREAM_CHUNK_TIMEOUT_SECONDS,
                )
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                if yielded_any:
                    logger.warning("LLM stream stalled after partial content")
                    raise LLMRequestTimeoutError(
                        "LLM streaming stalled before the response finished."
                    ) from None
                logger.warning(
                    "LLM stream produced no content before chunk timeout; falling back to non-stream completion"
                )
                fallback_content = await _non_stream_completion(
                    messages,
                    effective_model,
                    effective_api_base,
                    effective_api_key,
                    effective_max_tokens,
                )
                if fallback_content:
                    logger.info(
                        "LLM non-stream fallback succeeded len=%d",
                        len(fallback_content),
                    )
                    yield fallback_content
                    return
                logger.warning("LLM non-stream fallback returned empty content")
                raise LLMRequestTimeoutError(
                    "LLM streaming timed out before any content was received."
                ) from None

            content = _extract_stream_content(chunk)
            if content is not None:
                yielded_any = True
                yield content

        if not yielded_any:
            logger.warning(
                "LLM stream finished without yielding content; falling back to non-stream completion"
            )
            fallback_content = await _non_stream_completion(
                messages,
                effective_model,
                effective_api_base,
                effective_api_key,
                effective_max_tokens,
            )
            if fallback_content:
                logger.info(
                    "LLM post-stream fallback succeeded len=%d",
                    len(fallback_content),
                )
                yield fallback_content
            else:
                logger.warning("LLM post-stream fallback returned empty content")


async def complete_llm_response(
    messages: list[dict],
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
    max_tokens: int | None = None,
) -> str:
    chunks: list[str] = []
    async for token in stream_llm_response(
        messages,
        model=model,
        api_base=api_base,
        api_key=api_key,
        max_tokens=max_tokens,
    ):
        chunks.append(token)
    return "".join(chunks)
