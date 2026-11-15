import asyncio
import base64
import json
import logging
import queue
import threading
import time
from collections import Counter
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

        resolved = str(resolve_file_path(file_path, allow_legacy_absolute=True))
        with fitz.open(resolved) as document:
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

    local_text = _parse_pdf_locally(resolved)
    if len(local_text.strip()) < 100:
        boilerplate_lines, _page_count, image_pages_count = _detect_repeated_page_boilerplate(
            resolved
        )
        if image_pages_count > 0:
            ocr_text = await _ocr_scanned_pdf_if_needed(
                resolved,
                boilerplate_lines=boilerplate_lines,
                min_size=100,
            )
            if ocr_text.strip() and len(ocr_text.strip()) >= len(local_text.strip()):
                return ocr_text
    return local_text


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


def _is_structural_markdown_line(norm: str) -> bool:
    if not norm:
        return True
    if norm in {"---", "***", "___"} or set(norm) <= {"-", "=", "_", "*", "|", " ", ":"}:
        return True
    if norm.startswith("|") and norm.endswith("|"):
        return True
    if norm.startswith("<!-- page ") and norm.endswith("-->"):
        return True
    return False


def _detect_repeated_page_boilerplate(file_path: str) -> tuple[set[str], int, int]:
    """Detect repeated cross-page header/footer/watermark lines and scanned image pages."""
    try:
        import fitz

        with fitz.open(file_path) as doc:
            page_count = len(doc)
            image_pages_count = 0
            non_empty_page_texts: list[str] = []
            line_page_counts: Counter[str] = Counter()

            for page in doc:
                try:
                    if page.get_images():
                        image_pages_count += 1
                except Exception:
                    pass
                raw_page_text = (page.get_text() or "").strip()
                if not raw_page_text:
                    continue
                non_empty_page_texts.append(raw_page_text)
                if page_count >= 3:
                    page_norms = {
                        norm
                        for line in raw_page_text.splitlines()
                        if len(norm := " ".join(line.split()).strip()) >= 6
                    }
                    for norm in page_norms:
                        line_page_counts[norm] += 1
    except Exception:
        return set(), 0, 0

    boilerplate_lines: set[str] = set()
    if page_count >= 3:
        threshold = max(3, int(page_count * 0.25))
        boilerplate_lines = {
            norm for norm, cnt in line_page_counts.items() if cnt >= threshold
        }
        if len(non_empty_page_texts) >= 3 and len(set(non_empty_page_texts)) == 1:
            for line in non_empty_page_texts[0].splitlines():
                norm = " ".join(line.split()).strip()
                if norm:
                    boilerplate_lines.add(norm)

    return boilerplate_lines, page_count, image_pages_count


def _deduplicate_repeated_text(
    text: str,
    boilerplate_lines: set[str] | None = None,
) -> str:
    """Strip cross-page spam watermarks and collapse heavily repeated lines."""
    if not text or not text.strip():
        return ""

    boilerplate = set(boilerplate_lines or ())
    lines = text.splitlines()
    line_counts: Counter[str] = Counter()
    non_empty_norms: list[str] = []

    for line in lines:
        norm = " ".join(line.split()).strip()
        if not norm:
            continue
        non_empty_norms.append(norm)
        if len(norm) >= 8 and not _is_structural_markdown_line(norm):
            line_counts[norm] += 1

    repeated_norms = {norm for norm, cnt in line_counts.items() if cnt >= 3} | boilerplate
    if not repeated_norms:
        return text

    repeated_hits = sum(1 for norm in non_empty_norms if norm in repeated_norms)
    is_watermark_dominated = bool(non_empty_norms) and (
        repeated_hits * 2 >= len(non_empty_norms)
    )

    filtered: list[str] = []
    seen_repeated: set[str] = set()
    prev_non_empty_norm: str | None = None
    for line in lines:
        norm = " ".join(line.split()).strip()
        if not norm:
            if filtered and filtered[-1] != "":
                filtered.append("")
            continue
        if norm in repeated_norms:
            if is_watermark_dominated or norm in boilerplate:
                continue
            if norm in seen_repeated or norm == prev_non_empty_norm:
                continue
            seen_repeated.add(norm)
        elif norm == prev_non_empty_norm and len(norm) >= 8 and not _is_structural_markdown_line(norm):
            continue
        filtered.append(line)
        prev_non_empty_norm = norm

    while filtered and filtered[0] == "":
        filtered.pop(0)
    while filtered and filtered[-1] == "":
        filtered.pop()
    return "\n".join(filtered)


async def _resolve_ocr_llm_config() -> tuple[str | None, str | None, str | None]:
    """Resolve active LLM credentials from DB runtime_config first, falling back to static settings."""
    model = settings.llm_model
    api_base = settings.llm_api_base
    api_key = settings.llm_api_key

    try:
        from app.core.database import async_session_factory
        from app.services.runtime_config import get_runtime_llm_api_key, get_runtime_value

        async with async_session_factory() as db:
            db_model = await get_runtime_value("llm_model", db)
            db_api_base = await get_runtime_value("llm_api_base", db)
            db_api_key = await get_runtime_llm_api_key(db)
            if db_model:
                model = db_model
            if db_api_base:
                api_base = db_api_base
            if db_api_key:
                api_key = db_api_key
    except Exception as exc:
        logger.debug("Unable to resolve runtime LLM config from DB: %s", exc)

    if model and model.startswith("openai/"):
        model = model.removeprefix("openai/")
    return model, api_base, api_key


def _select_scanned_ocr_page_indices(page_count: int) -> list[int]:
    if page_count <= 0:
        return []
    if page_count <= 12:
        return list(range(page_count))
    front = [i for i in (0, 1, 2, 4, 6, 8, 9, 10, 11) if i < page_count]
    tail_span = page_count - 12
    step = max(1, tail_span // 4)
    body = [min(page_count - 1, 12 + step * k) for k in (1, 2, 3)]
    return sorted(set(front + body))[:12]


async def _ocr_scanned_pdf_if_needed(
    file_path: str,
    *,
    boilerplate_lines: set[str] | None = None,
    min_size: int = 100,
) -> str:
    """Transcribe representative scanned PDF pages via the configured vision LLM when no text layer exists."""
    model, api_base, api_key = await _resolve_ocr_llm_config()
    if not model or not api_base or not api_key:
        return ""

    try:
        import fitz

        rendered_pages: list[tuple[int, str]] = []
        with fitz.open(file_path) as doc:
            indices = _select_scanned_ocr_page_indices(len(doc))
            for idx in indices:
                pix = doc[idx].get_pixmap(matrix=fitz.Matrix(1.2, 1.2))
                b64 = base64.b64encode(pix.tobytes("png")).decode()
                rendered_pages.append((idx, b64))
    except Exception as exc:
        logger.warning(
            "Unable to render scanned PDF pages for %s (%s)",
            Path(file_path).name,
            exc,
        )
        return ""

    if not rendered_pages:
        return ""

    endpoint = f"{api_base.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    semaphore = asyncio.Semaphore(4)

    async def _transcribe_page(
        client: httpx.AsyncClient, page_idx: int, b64_png: str
    ) -> tuple[int, str]:
        payload = {
            "model": model,
            "reasoning_effort": "low",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Directly transcribe the main text on this scanned page into clean "
                                "Markdown. Ignore any advertising headers, footers, or watermarks. "
                                "Do not add explanations."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_png}"},
                        },
                    ],
                }
            ],
            "max_tokens": 1600,
        }
        async with semaphore:
            try:
                resp = await client.post(endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = (
                    ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                    or ""
                )
                return page_idx, str(content).strip()
            except Exception as exc:
                logger.warning(
                    "Vision OCR failed for %s page %d (%s)",
                    Path(file_path).name,
                    page_idx + 1,
                    exc,
                )
                return page_idx, ""

    try:
        async with httpx.AsyncClient(timeout=35.0, trust_env=False) as client:
            results = await asyncio.gather(
                *[_transcribe_page(client, idx, b64) for idx, b64 in rendered_pages]
            )
    except Exception as exc:
        logger.warning("Scanned PDF OCR aborted for %s (%s)", Path(file_path).name, exc)
        return ""

    sections = [
        f"<!-- page {idx + 1} -->\n\n{text}"
        for idx, text in sorted(results, key=lambda item: item[0])
        if text
    ]
    if not sections:
        return ""

    combined = "\n\n---\n\n".join(sections)
    cleaned = _deduplicate_repeated_text(combined, boilerplate_lines=boilerplate_lines)
    if len(cleaned.strip()) < min_size:
        logger.info(
            "Scanned PDF OCR yielded %d chars (< %d) for %s",
            len(cleaned.strip()),
            min_size,
            Path(file_path).name,
        )
    return cleaned


def _fallback_extract(file_path: str, min_size: int = 100) -> str:
    """Three-tier local PDF text extraction fallback (pymupdf4llm -> pymupdf -> pypdf) with min_size guard."""
    boilerplate_lines, page_count, image_pages_count = (
        _detect_repeated_page_boilerplate(file_path)
    )
    if page_count >= 3 and image_pages_count >= max(3, int(page_count * 0.8)):
        try:
            import fitz

            with fitz.open(file_path) as doc:
                raw_fitz_text = "".join(page.get_text() for page in doc)
            if not _deduplicate_repeated_text(
                raw_fitz_text, boilerplate_lines=boilerplate_lines
            ):
                logger.info(
                    "Detected scanned image-only PDF (%d/%d image pages) for %s; skipping slow text extractors",
                    image_pages_count,
                    page_count,
                    Path(file_path).name,
                )
                return ""
        except Exception:
            pass
    best_short_text = ""
    any_parser_available = False

    # Tier 1: pymupdf4llm (preserves Markdown headings, tables, and academic structure)
    try:
        import pymupdf4llm  # type: ignore[import-not-found]

        any_parser_available = True
        raw_text = str(pymupdf4llm.to_markdown(file_path) or "")
        text = _deduplicate_repeated_text(raw_text, boilerplate_lines=boilerplate_lines)
        if len(text) >= min_size:
            return text
        if len(text) > len(best_short_text):
            best_short_text = text
        logger.warning(
            "pymupdf4llm extracted fewer than %d chars (%d) for %s; falling back to pymupdf",
            min_size,
            len(text),
            Path(file_path).name,
        )
    except ImportError:
        pass
    except Exception as exc:
        logger.warning(
            "pymupdf4llm failed for %s (%s); falling back to pymupdf",
            Path(file_path).name,
            exc,
        )

    # Tier 2: pymupdf (fitz) direct page text extraction
    try:
        import fitz  # PyMuPDF

        any_parser_available = True
        with fitz.open(file_path) as doc:
            raw_text = "".join(page.get_text() for page in doc)
        text = _deduplicate_repeated_text(raw_text, boilerplate_lines=boilerplate_lines)
        if len(text) >= min_size:
            return text
        if len(text) > len(best_short_text):
            best_short_text = text
        logger.warning(
            "pymupdf extracted fewer than %d chars (%d) for %s; falling back to pypdf",
            min_size,
            len(text),
            Path(file_path).name,
        )
    except ImportError:
        pass
    except Exception as exc:
        logger.warning(
            "pymupdf failed for %s (%s); falling back to pypdf",
            Path(file_path).name,
            exc,
        )

    # Tier 3: pypdf fallback
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        any_parser_available = True
        reader = PdfReader(file_path)
        raw_text = "".join((page.extract_text() or "") for page in reader.pages)
        text = _deduplicate_repeated_text(raw_text, boilerplate_lines=boilerplate_lines)
        if len(text) >= min_size:
            return text
        if len(text) > len(best_short_text):
            best_short_text = text
    except ImportError:
        pass
    except Exception as exc:
        logger.warning(
            "pypdf failed for %s (%s)",
            Path(file_path).name,
            exc,
        )

    if best_short_text or any_parser_available:
        return best_short_text
    return f"[PDF parsing unavailable for {Path(file_path).name}]"
