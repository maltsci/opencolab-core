import asyncio
import json
import logging
import queue
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.services.file_storage import resolve_file_path

logger = logging.getLogger(__name__)

_marker_lock = threading.Lock()
_marker_converter = None
_marker_converter_config: tuple[str | None, str | None] | None = None

_PPS_OPTIONS = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": False,
    "useTableRecognition": True,
    "useFormulaRecognition": True,
    "prettifyMarkdown": True,
}


class PPSParseError(RuntimeError):
    """Raised when the remote PPS parser cannot produce usable Markdown."""


def extract_pdf_document_metadata(file_path: str) -> dict[str, str]:
    """Read a small whitelist of embedded PDF metadata locally."""
    try:
        import fitz

        with fitz.open(file_path) as document:
            raw_metadata = document.metadata or {}
    except Exception as exc:
        logger.warning(
            "Unable to read embedded PDF metadata for %s (%s)",
            Path(file_path).name,
            type(exc).__name__,
        )
        return {}

    metadata: dict[str, str] = {}
    for key in ("title", "author", "subject", "keywords"):
        value = " ".join(str(raw_metadata.get(key) or "").split()).strip()
        if value:
            metadata[key] = value
    return metadata


def _patch_surya_transformers_compatibility() -> None:
    """Patch Surya composite config metadata for newer transformers builds.

    transformers may call config.to_diff_dict(), which instantiates a default
    config object unless has_no_defaults_at_init is set. SuryaOCRConfig
    requires encoder/decoder kwargs, so that default construction raises
    KeyError("encoder") during marker model loading.
    """
    try:
        from surya.recognition.model.config import SuryaOCRConfig
    except ImportError:
        return

    SuryaOCRConfig.has_no_defaults_at_init = True

    if getattr(SuryaOCRConfig, "_opencolab_get_text_config_patched", False):
        return

    original_get_text_config = SuryaOCRConfig.get_text_config

    def _get_text_config(self, decoder=None, encoder=None):
        if decoder is None and encoder is None and hasattr(self, "decoder"):
            return getattr(self, "decoder")
        if encoder:
            text_encoder = getattr(self, "text_encoder", None)
            if text_encoder is not None:
                return text_encoder
        if decoder:
            decoder_config = getattr(self, "decoder", None)
            if decoder_config is not None:
                return decoder_config
        return original_get_text_config(self, decoder=decoder, encoder=encoder)

    SuryaOCRConfig.get_text_config = _get_text_config
    SuryaOCRConfig._opencolab_get_text_config_patched = True


async def parse_pdf(file_path: str) -> str:
    """Parse a PDF with PPS first, then fall back to the local parser."""
    resolved = str(resolve_file_path(file_path, allow_legacy_absolute=True))
    if settings.pdf_pps_enabled and settings.pdf_pps_api_key:
        try:
            return await _parse_with_pps(resolved)
        except (PPSParseError, TimeoutError) as exc:
            logger.warning(
                "PPS parsing failed for %s (%s); using the local PDF parser",
                Path(resolved).name,
                exc,
            )
        except Exception as exc:
            logger.warning(
                "PPS parsing failed for %s (%s); using the local PDF parser",
                Path(resolved).name,
                type(exc).__name__,
            )

    return _parse_pdf_locally(resolved)


def _parse_pdf_locally(resolved: str) -> str:
    if not settings.pdf_marker_enabled:
        logger.info(
            "marker-pdf disabled; using basic text extraction for %s",
            Path(resolved).name,
        )
        return _fallback_extract(resolved)

    try:
        converter = _get_marker_converter()
        return _parse_with_marker_timeout(
            converter,
            resolved,
            settings.pdf_parse_timeout_seconds,
        )
    except TimeoutError:
        logger.warning(
            "marker-pdf timed out after %.1fs for %s, falling back to basic text extraction",
            settings.pdf_parse_timeout_seconds,
            Path(resolved).name,
        )
        return _fallback_extract(resolved)
    except Exception as exc:
        logger.warning(
            "marker-pdf failed (%s), falling back to basic text extraction", exc
        )
        return _fallback_extract(resolved)


async def _parse_with_pps(file_path: str) -> str:
    jobs_url = settings.pdf_pps_jobs_url.rstrip("/")
    token = settings.pdf_pps_api_key
    if not jobs_url or not token:
        raise PPSParseError("PPS is not configured")

    page_range = _pdf_page_range(file_path)
    headers = {"Authorization": f"bearer {token}"}
    deadline = time.monotonic() + settings.pdf_pps_timeout_seconds
    timeout = httpx.Timeout(
        min(settings.pdf_pps_timeout_seconds, 60.0),
        connect=min(settings.pdf_pps_timeout_seconds, 10.0),
    )

    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            with Path(file_path).open("rb") as stream:
                response = await client.post(
                    jobs_url,
                    headers=headers,
                    data={
                        "model": "PP-StructureV3",
                        "optionalPayload": json.dumps(_PPS_OPTIONS),
                        "pageRanges": page_range,
                    },
                    files={"file": (Path(file_path).name, stream, "application/pdf")},
                )
            response.raise_for_status()
            job_id = _require_string(response.json(), "data", "jobId")

            while time.monotonic() < deadline:
                status_response = await client.get(
                    f"{jobs_url}/{job_id}", headers=headers
                )
                status_response.raise_for_status()
                status_data = status_response.json().get("data", {})
                state = status_data.get("state")
                if state == "failed":
                    error = status_data.get("errorMsg") or "unknown server error"
                    raise PPSParseError(f"job failed: {error}")
                if state == "done":
                    result_url = _require_string(status_data, "resultUrl", "jsonUrl")
                    _validate_result_url(jobs_url, result_url)
                    result_response = await client.get(result_url)
                    result_response.raise_for_status()
                    markdown = _parse_pps_jsonl(result_response.text)
                    logger.info("PPS parsed %s successfully", Path(file_path).name)
                    return markdown
                if state not in {"pending", "running"}:
                    raise PPSParseError(f"unexpected job state: {state!r}")
                await asyncio.sleep(settings.pdf_pps_poll_interval_seconds)
    except PPSParseError:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise PPSParseError(type(exc).__name__) from exc

    raise TimeoutError(f"PPS timed out after {settings.pdf_pps_timeout_seconds:.1f}s")


def _pdf_page_range(file_path: str) -> str:
    try:
        import fitz

        with fitz.open(file_path) as document:
            page_count = document.page_count
    except Exception as exc:
        raise PPSParseError("could not read PDF page count") from exc
    if page_count < 1:
        raise PPSParseError("PDF has no pages")
    return f"1-{page_count}"


def _require_string(payload: dict, *path: str) -> str:
    value = payload
    for key in path:
        if not isinstance(value, dict):
            raise PPSParseError(f"missing response field: {'.'.join(path)}")
        value = value.get(key)
    if not isinstance(value, str) or not value:
        raise PPSParseError(f"missing response field: {'.'.join(path)}")
    return value


def _validate_result_url(jobs_url: str, result_url: str) -> None:
    jobs_origin = urlsplit(jobs_url)
    result_origin = urlsplit(result_url)
    if (
        result_origin.scheme not in {"http", "https"}
        or result_origin.scheme != jobs_origin.scheme
        or result_origin.netloc != jobs_origin.netloc
    ):
        raise PPSParseError("result URL is outside the configured PPS service")


def _parse_pps_jsonl(content: str) -> str:
    pages: list[str] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PPSParseError(f"invalid JSONL at line {line_number}") from exc
        layout_results = payload.get("result", {}).get("layoutParsingResults", [])
        if not isinstance(layout_results, list):
            raise PPSParseError("invalid layoutParsingResults")
        for result in layout_results:
            if not isinstance(result, dict):
                continue
            markdown = result.get("markdown")
            text = markdown.get("text") if isinstance(markdown, dict) else None
            if isinstance(text, str) and text.strip():
                pages.append(text.strip())

    if not pages:
        raise PPSParseError("PPS returned no Markdown text")
    return "\n\n---\n\n".join(
        f"<!-- page {index} -->\n\n{text}" for index, text in enumerate(pages, start=1)
    )


def preload_marker_converter() -> None:
    """Load marker models once during worker startup."""
    _get_marker_converter()


def _get_marker_converter():
    global _marker_converter, _marker_converter_config

    with _marker_lock:
        device = settings.pdf_marker_device or None
        dtype_name = settings.pdf_marker_dtype or None
        config = (device, dtype_name)
        if _marker_converter is not None and _marker_converter_config == config:
            return _marker_converter

        _patch_surya_transformers_compatibility()
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict

        dtype = _resolve_marker_dtype(dtype_name)
        logger.info(
            "Loading marker PDF models (device=%s, dtype=%s)",
            device or "auto",
            dtype_name or "auto",
        )
        started_at = time.perf_counter()
        _marker_converter = PdfConverter(
            artifact_dict=create_model_dict(device=device, dtype=dtype)
        )
        _marker_converter_config = config
        logger.info(
            "Marker PDF models loaded in %.1fs", time.perf_counter() - started_at
        )
        return _marker_converter


def _resolve_marker_dtype(dtype_name: str | None):
    if not dtype_name:
        return None
    import torch

    normalized = dtype_name.lower()
    if normalized == "float16":
        return torch.float16
    if normalized == "float32":
        return torch.float32
    if normalized == "bfloat16":
        return torch.bfloat16
    raise ValueError(f"Unsupported marker dtype: {dtype_name}")


def _parse_with_marker_timeout(
    converter, file_path: str, timeout_seconds: float
) -> str:
    result_queue: queue.Queue[tuple[str, str | BaseException]] = queue.Queue(maxsize=1)

    def run_marker() -> None:
        try:
            started_at = time.perf_counter()
            with _marker_lock:
                rendered = converter(file_path)
            logger.info(
                "marker-pdf parsed %s in %.1fs",
                Path(file_path).name,
                time.perf_counter() - started_at,
            )
            result_queue.put(("ok", rendered.markdown))
        except BaseException as exc:
            result_queue.put(("error", exc))

    thread = threading.Thread(target=run_marker, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError(f"marker-pdf timed out after {timeout_seconds:.1f}s")

    status, payload = result_queue.get_nowait()
    if status == "error":
        if isinstance(payload, BaseException):
            raise payload
        raise RuntimeError(str(payload))
    return str(payload)


def _fallback_extract(file_path: str) -> str:
    """Basic fallback if marker is not available."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except ImportError:
        return f"[PDF parsing unavailable for {Path(file_path).name}]"
