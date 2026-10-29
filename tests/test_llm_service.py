import asyncio
from types import SimpleNamespace

import pytest

from app.services import rag_service
from app.services import llm_service
from app.services.llm_service import (
    LLMRequestTimeoutError,
    build_prompt,
    normalize_litellm_model_name,
    should_bypass_proxy_for_api_base,
    stream_llm_response,
)


def test_normalize_litellm_model_name_prefixes_openai_for_custom_api_base():
    assert (
        normalize_litellm_model_name(
            "tianfu-basic",
            "http://localhost:4000/v1",
        )
        == "openai/tianfu-basic"
    )


def test_normalize_litellm_model_name_keeps_provider_qualified_model():
    assert (
        normalize_litellm_model_name(
            "ollama/llama3",
            "http://localhost:11434",
        )
        == "ollama/llama3"
    )


def test_normalize_litellm_model_name_does_not_rewrite_ollama_base():
    assert (
        normalize_litellm_model_name(
            "llama3",
            "http://localhost:11434",
        )
        == "llama3"
    )


def test_should_bypass_proxy_for_api_base_on_localhost():
    assert should_bypass_proxy_for_api_base("http://localhost:4000") is True
    assert should_bypass_proxy_for_api_base("http://127.0.0.1:11434") is True
    assert should_bypass_proxy_for_api_base("https://api.openai.com/v1") is False


@pytest.mark.asyncio
async def test_stream_llm_response_uses_local_client_for_local_api_base(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def __aiter__(self):
            async def generator():
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))]
                )

            return generator()

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(llm_service.litellm, "acompletion", fake_acompletion)

    chunks = []
    async for token in stream_llm_response(
        [{"role": "user", "content": "hello"}],
        model="openai/tianfu-basic",
        api_base="http://localhost:4000",
        api_key="test-key",
    ):
        chunks.append(token)

    assert chunks == ["ok"]
    assert "client" in captured
    assert captured["client"] is not None


@pytest.mark.asyncio
async def test_stream_llm_response_times_out(monkeypatch):
    async def fake_acompletion(**kwargs):
        await asyncio.sleep(0.05)
        return None

    monkeypatch.setattr(llm_service.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm_service, "LLM_STREAM_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(LLMRequestTimeoutError):
        async for _ in stream_llm_response(
            [{"role": "user", "content": "hello"}],
            model="openai/tianfu-basic",
            api_base="http://localhost:4000",
            api_key="test-key",
        ):
            pass


@pytest.mark.asyncio
async def test_stream_llm_response_falls_back_to_non_streaming_when_stream_yields_no_tokens(
    monkeypatch,
):
    captured_calls: list[dict] = []

    class HangingStreamResponse:
        def __aiter__(self):
            async def generator():
                await asyncio.sleep(0.05)
                if False:
                    yield None

            return generator()

    class NonStreamingResponse:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(content="fallback answer"),
            )
        ]

    async def fake_acompletion(**kwargs):
        captured_calls.append(kwargs)
        if kwargs.get("stream"):
            return HangingStreamResponse()
        return NonStreamingResponse()

    monkeypatch.setattr(llm_service.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm_service, "LLM_STREAM_CHUNK_TIMEOUT_SECONDS", 0.01)

    chunks = []
    async for token in stream_llm_response(
        [{"role": "user", "content": "hello"}],
        model="openai/test-model",
        api_base="https://example.com/v1",
        api_key="test-key",
    ):
        chunks.append(token)

    assert chunks == ["fallback answer"]
    assert [call.get("stream") for call in captured_calls] == [True, False]


@pytest.mark.asyncio
async def test_stream_llm_response_falls_back_to_non_streaming_for_list_content(
    monkeypatch,
):
    class EmptyStreamResponse:
        def __aiter__(self):
            async def generator():
                if False:
                    yield None

            return generator()

    class NonStreamingResponse:
        choices = [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "structured "},
                        {"type": "text", "text": "answer"},
                    ]
                }
            }
        ]

    async def fake_acompletion(**kwargs):
        if kwargs.get("stream"):
            return EmptyStreamResponse()
        return NonStreamingResponse()

    monkeypatch.setattr(llm_service.litellm, "acompletion", fake_acompletion)

    chunks = []
    async for token in stream_llm_response(
        [{"role": "user", "content": "hello"}],
        model="openai/test-model",
        api_base="https://example.com/v1",
        api_key="test-key",
    ):
        chunks.append(token)

    assert chunks == ["structured answer"]


@pytest.mark.asyncio
async def test_stream_llm_response_reads_structured_stream_deltas(monkeypatch):
    class StructuredStreamResponse:
        def __aiter__(self):
            async def generator():
                yield {
                    "choices": [
                        {
                            "delta": {
                                "content": [
                                    {"type": "text", "text": "hello "},
                                    {"type": "text", "text": "world"},
                                ]
                            }
                        }
                    ]
                }

            return generator()

    async def fake_acompletion(**kwargs):
        return StructuredStreamResponse()

    monkeypatch.setattr(llm_service.litellm, "acompletion", fake_acompletion)

    chunks = []
    async for token in stream_llm_response(
        [{"role": "user", "content": "hello"}],
        model="openai/test-model",
        api_base="https://example.com/v1",
        api_key="test-key",
    ):
        chunks.append(token)

    assert chunks == ["hello world"]


@pytest.mark.asyncio
async def test_classify_query_mode_forces_rag_for_summary_queries():
    mode = await rag_service.classify_query_mode(
        "这篇文章的主要内容是什么？",
        model="openai/tianfu-basic",
        api_base="http://localhost:4000",
        api_key="test-key",
    )

    assert mode == "rag"


@pytest.mark.asyncio
async def test_classify_query_mode_prefers_rag_for_specific_queries():
    mode = await rag_service.classify_query_mode(
        "第三章讲了什么？",
        model="openai/tianfu-basic",
        api_base="http://localhost:4000",
        api_key="test-key",
    )

    assert mode == "rag"


@pytest.mark.asyncio
async def test_stream_llm_response_sets_generation_budget(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def __aiter__(self):
            async def generator():
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))]
                )

            return generator()

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(llm_service.litellm, "acompletion", fake_acompletion)

    async for _ in stream_llm_response(
        [{"role": "user", "content": "hello"}],
        model="openai/tianfu-basic",
        api_base="http://localhost:4000",
        api_key="test-key",
    ):
        pass

    assert captured["max_tokens"] == llm_service.LLM_RESPONSE_MAX_TOKENS


def test_build_prompt_truncates_long_chunk_text():
    chunks = [
        {
            "text": "A" * (llm_service.MAX_CONTEXT_CHARS_PER_CHUNK + 200),
        }
    ]

    messages = build_prompt("summarize", chunks)

    system_message = messages[0]["content"]
    assert "A" * llm_service.MAX_CONTEXT_CHARS_PER_CHUNK in system_message
    assert "A" * (llm_service.MAX_CONTEXT_CHARS_PER_CHUNK + 50) not in system_message


def test_build_prompt_requests_simplified_chinese_when_locale_is_zh_cn():
    messages = build_prompt("summarize", [], locale="zh-CN")

    system_message = messages[0]["content"]
    assert "Respond in Simplified Chinese." in system_message


def test_build_prompt_includes_project_instructions():
    messages = build_prompt(
        "summarize", [], project_instructions="# Role\nYou are a market research helper."
    )

    system_message = messages[0]["content"]
    assert "Project instructions" in system_message
    assert "You are a market research helper." in system_message


def test_build_prompt_ignores_blank_project_instructions():
    messages = build_prompt("summarize", [], project_instructions="   ")

    system_message = messages[0]["content"]
    assert "Project instructions" not in system_message


@pytest.mark.asyncio
async def test_remote_embed_query_bypasses_proxy_for_local_worker(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embedding": [0.1, 0.2]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr(rag_service.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(rag_service.settings, "worker_url", "http://localhost:8001")

    embedding = await rag_service._remote_embed_query("hello")

    assert embedding == [0.1, 0.2]
    assert captured["trust_env"] is False
    assert captured["url"] == "http://localhost:8001/embed"
