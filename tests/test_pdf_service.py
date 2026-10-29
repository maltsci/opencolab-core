import json
import sys
import types

import pytest
from surya.recognition.model.config import SuryaOCRConfig

from app.services import pdf_service
from app.services.pdf_service import (
    PPSParseError,
    _parse_pps_jsonl,
    _patch_surya_transformers_compatibility,
    preload_marker_converter,
)


@pytest.fixture(autouse=True)
def disable_pps_by_default(monkeypatch):
    monkeypatch.setattr(pdf_service.settings, "pdf_pps_enabled", False)


@pytest.mark.asyncio
async def test_parse_pdf_prefers_pps_when_configured(monkeypatch, tmp_path):
    pdf_path = tmp_path / "remote.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    async def fake_parse_with_pps(path: str) -> str:
        assert path == str(pdf_path)
        return "remote markdown"

    monkeypatch.setattr(pdf_service.settings, "pdf_pps_enabled", True)
    monkeypatch.setattr(pdf_service.settings, "pdf_pps_api_key", "test-token")
    monkeypatch.setattr(pdf_service, "_parse_with_pps", fake_parse_with_pps)
    monkeypatch.setattr(
        pdf_service,
        "_parse_pdf_locally",
        lambda path: pytest.fail("local parser should not be called"),
    )

    result = await pdf_service.parse_pdf(str(pdf_path))

    assert result == "remote markdown"


@pytest.mark.asyncio
async def test_parse_pdf_falls_back_when_pps_fails(monkeypatch, tmp_path):
    pdf_path = tmp_path / "remote-failure.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    async def failing_parse_with_pps(path: str) -> str:
        raise PPSParseError("job failed")

    monkeypatch.setattr(pdf_service.settings, "pdf_pps_enabled", True)
    monkeypatch.setattr(pdf_service.settings, "pdf_pps_api_key", "test-token")
    monkeypatch.setattr(pdf_service, "_parse_with_pps", failing_parse_with_pps)
    monkeypatch.setattr(
        pdf_service, "_parse_pdf_locally", lambda path: "local fallback"
    )

    result = await pdf_service.parse_pdf(str(pdf_path))

    assert result == "local fallback"


@pytest.mark.asyncio
async def test_parse_pdf_skips_pps_without_token(monkeypatch, tmp_path):
    pdf_path = tmp_path / "no-token.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(pdf_service.settings, "pdf_pps_enabled", True)
    monkeypatch.setattr(pdf_service.settings, "pdf_pps_api_key", None)
    monkeypatch.setattr(
        pdf_service, "_parse_pdf_locally", lambda path: "local fallback"
    )

    result = await pdf_service.parse_pdf(str(pdf_path))

    assert result == "local fallback"


def test_parse_pps_jsonl_combines_markdown_pages():
    lines = [
        {
            "result": {
                "layoutParsingResults": [
                    {"markdown": {"text": "First page", "images": {}}}
                ]
            }
        },
        {
            "result": {
                "layoutParsingResults": [
                    {"markdown": {"text": "Second page", "images": {}}}
                ]
            }
        },
    ]

    result = _parse_pps_jsonl("\n".join(json.dumps(line) for line in lines))

    assert result == (
        "<!-- page 1 -->\n\nFirst page"
        "\n\n---\n\n"
        "<!-- page 2 -->\n\nSecond page"
    )


def test_parse_pps_jsonl_rejects_empty_results():
    with pytest.raises(PPSParseError, match="no Markdown"):
        _parse_pps_jsonl('{"result":{"layoutParsingResults":[]}}')


@pytest.mark.asyncio
async def test_parse_pdf_uses_fallback_when_marker_is_disabled(monkeypatch, tmp_path):
    pdf_path = tmp_path / "basic.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(pdf_service.settings, "pdf_marker_enabled", False)
    monkeypatch.setattr(pdf_service, "_fallback_extract", lambda path: "basic text")

    result = await pdf_service.parse_pdf(str(pdf_path))

    assert result == "basic text"


@pytest.mark.asyncio
async def test_parse_pdf_falls_back_when_marker_times_out(monkeypatch, tmp_path):
    pdf_path = tmp_path / "slow.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    marker_module = types.ModuleType("marker")
    converters_module = types.ModuleType("marker.converters")
    pdf_module = types.ModuleType("marker.converters.pdf")
    models_module = types.ModuleType("marker.models")

    class SlowConverter:
        def __init__(self, artifact_dict):
            self.artifact_dict = artifact_dict

        def __call__(self, path):
            import time

            time.sleep(0.2)
            return types.SimpleNamespace(markdown="marker text")

    pdf_module.PdfConverter = SlowConverter
    models_module.create_model_dict = lambda: {}
    monkeypatch.setitem(sys.modules, "marker", marker_module)
    monkeypatch.setitem(sys.modules, "marker.converters", converters_module)
    monkeypatch.setitem(sys.modules, "marker.converters.pdf", pdf_module)
    monkeypatch.setitem(sys.modules, "marker.models", models_module)
    monkeypatch.setattr(pdf_service.settings, "pdf_marker_enabled", True)
    monkeypatch.setattr(
        pdf_service.settings,
        "pdf_parse_timeout_seconds",
        0.01,
        raising=False,
    )
    monkeypatch.setattr(pdf_service, "_fallback_extract", lambda path: "fallback text")

    result = await pdf_service.parse_pdf(str(pdf_path))

    assert result == "fallback text"


@pytest.mark.asyncio
async def test_marker_converter_is_reused_after_preload(monkeypatch, tmp_path):
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    first_pdf.write_bytes(b"%PDF-1.4\n")
    second_pdf.write_bytes(b"%PDF-1.4\n")

    marker_module = types.ModuleType("marker")
    converters_module = types.ModuleType("marker.converters")
    pdf_module = types.ModuleType("marker.converters.pdf")
    models_module = types.ModuleType("marker.models")
    calls = {"models": 0, "converter": 0}

    class FastConverter:
        def __init__(self, artifact_dict):
            self.artifact_dict = artifact_dict
            calls["converter"] += 1

        def __call__(self, path):
            return types.SimpleNamespace(markdown=f"parsed {path}")

    def create_model_dict(device=None, dtype=None):
        calls["models"] += 1
        return {"device": device, "dtype": dtype}

    pdf_module.PdfConverter = FastConverter
    models_module.create_model_dict = create_model_dict
    monkeypatch.setitem(sys.modules, "marker", marker_module)
    monkeypatch.setitem(sys.modules, "marker.converters", converters_module)
    monkeypatch.setitem(sys.modules, "marker.converters.pdf", pdf_module)
    monkeypatch.setitem(sys.modules, "marker.models", models_module)
    monkeypatch.setattr(pdf_service, "_marker_converter", None)
    monkeypatch.setattr(pdf_service, "_marker_converter_config", None)
    monkeypatch.setattr(pdf_service.settings, "pdf_marker_enabled", True)

    preload_marker_converter()
    await pdf_service.parse_pdf(str(first_pdf))
    await pdf_service.parse_pdf(str(second_pdf))

    assert calls == {"models": 1, "converter": 1}


def test_surya_ocr_config_diff_dict_does_not_require_default_encoder_decoder():
    _patch_surya_transformers_compatibility()

    cfg = SuryaOCRConfig(
        encoder={},
        decoder={
            "bos_token_id": 1,
            "pad_token_id": 0,
            "eos_token_id": 2,
        },
    )

    diff = cfg.to_diff_dict()

    assert diff["is_encoder_decoder"] is True
    assert diff["decoder_start_token_id"] == 1


def test_surya_ocr_config_get_text_config_prefers_decoder_by_default():
    _patch_surya_transformers_compatibility()

    decoder = {
        "bos_token_id": 1,
        "pad_token_id": 0,
        "eos_token_id": 2,
    }
    text_encoder = {"query_token_count": 128}
    cfg = SuryaOCRConfig(encoder={}, decoder=decoder)
    cfg.text_encoder = text_encoder

    assert cfg.get_text_config() == decoder
    assert cfg.get_text_config(decoder=True) == decoder
    assert cfg.get_text_config(encoder=True) == text_encoder
