from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_asset import ResearchAsset
from app.models.source import Chunk, Source
from app.models.trace import SourceExtraction
from app.services.bibliographic_metadata_service import (
    build_local_bibliographic_metadata,
)


def build_source_extraction_payload(
    source_name: str,
    text: str,
    document_metadata: dict[str, str] | None = None,
) -> dict:
    """Build a minimal deterministic extraction payload."""
    normalized_text = _normalize_text(text)
    embedded_title = _normalize_embedded_title((document_metadata or {}).get("title"))
    parsed_heading = _extract_markdown_heading(normalized_text)
    title = (
        embedded_title or parsed_heading or _extract_title(normalized_text, source_name)
    )
    if embedded_title:
        local_title_source = "pdf_metadata"
        local_title_confidence = "high"
    elif parsed_heading:
        local_title_source = "parsed_heading"
        local_title_confidence = "high"
    else:
        local_title_source = "parsed_text"
        local_title_confidence = "medium"
    body_text = _extract_body_text(normalized_text, title)
    sentences = _split_sentences(body_text)
    summary = sentences[0] if sentences else ""
    highlights = sentences[:3]

    structured_json = _build_v1_structured_json(
        title=title,
        summary=summary,
        highlights=highlights,
        source_text=normalized_text,
        local_title_source=local_title_source,
        local_title_confidence=local_title_confidence,
        embedded_keywords=(document_metadata or {}).get("keywords"),
    )
    document_type = _infer_document_type(source_name)
    metadata_status = (
        structured_json["bibliographic"]["resolution"]["status"]
        if document_type == "paper"
        else "not_applicable"
    )

    return {
        "status": "ready",
        "document_type": document_type,
        "schema_version": "v1",
        "structured_json": structured_json,
        # Preserve the parser output separately from retrieval chunks. Chunks may
        # overlap or split Markdown blocks, which makes them unsuitable for reading.
        "rendered_markdown": text or None,
        "error_message": None,
        "metadata_status": metadata_status,
        "metadata_attempts": 0,
        "metadata_next_attempt_at": None,
        "metadata_checked_at": None,
        "metadata_error": None,
    }


def build_failed_source_extraction_payload(
    source_name: str,
    error_message: str,
) -> dict:
    """Build a terminal failed extraction payload."""
    title = _extract_title("", source_name)

    return {
        "status": "failed",
        "document_type": _infer_document_type(source_name),
        "schema_version": "v1",
        "structured_json": _build_v1_structured_json(
            title=title,
            summary="",
            highlights=[],
            source_text="",
        ),
        "rendered_markdown": None,
        "error_message": error_message,
        "metadata_status": "failed"
        if source_name.lower().endswith(".pdf")
        else "not_applicable",
        "metadata_attempts": 0,
        "metadata_next_attempt_at": None,
        "metadata_checked_at": None,
        "metadata_error": error_message
        if source_name.lower().endswith(".pdf")
        else None,
    }


async def upsert_source_extraction(
    db: AsyncSession,
    source_id: str,
    payload: dict,
) -> SourceExtraction:
    """Create or update a source extraction row."""
    result = await db.execute(
        select(SourceExtraction).where(SourceExtraction.source_id == source_id)
    )
    extraction = result.scalar_one_or_none()

    if extraction is None:
        extraction = SourceExtraction(source_id=source_id, **payload)
        db.add(extraction)
        await _apply_local_bibliographic_metadata(db, source_id, payload)
        return extraction

    extraction.status = payload["status"]
    extraction.document_type = payload["document_type"]
    extraction.schema_version = payload["schema_version"]
    extraction.structured_json = payload["structured_json"]
    extraction.rendered_markdown = payload.get("rendered_markdown")
    extraction.error_message = payload["error_message"]
    extraction.metadata_status = payload["metadata_status"]
    extraction.metadata_attempts = payload["metadata_attempts"]
    extraction.metadata_next_attempt_at = payload["metadata_next_attempt_at"]
    extraction.metadata_checked_at = payload["metadata_checked_at"]
    extraction.metadata_error = payload["metadata_error"]
    await _apply_local_bibliographic_metadata(db, source_id, payload)
    return extraction


async def _apply_local_bibliographic_metadata(
    db: AsyncSession,
    source_id: str,
    payload: dict,
) -> None:
    bibliographic = (payload.get("structured_json") or {}).get("bibliographic") or {}
    asset = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.source_id == source_id)
    )
    if asset is None:
        return

    metadata = dict(asset.catalog_metadata_json or {})
    stored_bibliographic = dict(metadata.get("bibliographic") or {})
    keywords = bibliographic.get("keywords")
    if isinstance(keywords, list):
        stored_bibliographic["keywords"] = [
            normalized
            for value in keywords[:10]
            if (normalized := " ".join(str(value).split()).strip())
            and len(normalized) <= 100
        ]
        metadata["bibliographic"] = stored_bibliographic
        asset.catalog_metadata_json = metadata

    candidate = bibliographic.get("local_title_candidate") or {}
    if candidate.get("confidence") != "high":
        return
    title = " ".join(str(candidate.get("value") or "").split()).strip()
    if not title or len(title) > 500:
        return
    if asset.title_locked or asset.title_source not in {
        "filename",
        "parsed_text",
        "parsed_heading",
        "pdf_metadata",
    }:
        return
    metadata["title"] = title
    asset.title = title
    asset.title_source = str(candidate.get("source") or "parsed_text")
    asset.catalog_metadata_json = metadata


async def rebuild_local_bibliographic_metadata_from_chunks(
    db: AsyncSession,
    source_id: str,
) -> SourceExtraction | None:
    """Upgrade stored extraction metadata using already indexed local text."""
    source = await db.get(Source, source_id)
    asset = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.source_id == source_id)
    )
    extraction = await db.scalar(
        select(SourceExtraction).where(SourceExtraction.source_id == source_id)
    )
    if source is None or asset is None or extraction is None:
        return None
    if extraction.document_type != "paper":
        return None

    chunks = (
        await db.scalars(
            select(Chunk)
            .where(Chunk.source_id == source_id)
            .order_by(Chunk.chunk_index.asc())
        )
    ).all()
    source_text = "\n".join(chunk.text for chunk in chunks if chunk.text.strip())
    if not source_text:
        return None

    structured = dict(extraction.structured_json or {})
    existing_bibliographic = dict(structured.get("bibliographic") or {})
    title = " ".join(
        str(structured.get("title") or asset.title or source.name).split()
    ).strip()
    title_source = asset.title_source or "parsed_text"
    local_bibliographic = build_local_bibliographic_metadata(
        text=source_text,
        title=title,
        title_source=title_source,
        title_confidence="medium" if title_source == "filename" else "high",
    )

    provider_candidates = existing_bibliographic.get("provider_candidates")
    if isinstance(provider_candidates, list) and provider_candidates:
        local_bibliographic["provider_candidates"] = provider_candidates
    existing_resolution = existing_bibliographic.get("resolution")
    if (
        isinstance(existing_resolution, dict)
        and existing_resolution.get("status") in {"resolved", "needs_review"}
    ):
        local_bibliographic["resolution"] = existing_resolution

    structured["bibliographic"] = local_bibliographic
    extraction.structured_json = structured
    extraction.schema_version = "v1"
    extraction.metadata_status = str(local_bibliographic["resolution"]["status"])
    extraction.metadata_error = None
    await _apply_local_bibliographic_metadata(
        db,
        source_id,
        {"structured_json": structured},
    )
    return extraction


def _normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _build_v1_structured_json(
    *,
    title: str,
    summary: str,
    highlights: list[str],
    source_text: str,
    local_title_source: str = "parsed_text",
    local_title_confidence: str = "medium",
    embedded_keywords: str | None = None,
) -> dict:
    return {
        "title": title,
        "summary": summary,
        "highlights": highlights,
        "bibliographic": build_local_bibliographic_metadata(
            text=source_text,
            title=title,
            title_source=local_title_source,
            title_confidence=local_title_confidence,
            embedded_keywords=embedded_keywords,
        ),
        "claims": [],
        "methods": [],
        "limitations": [],
        "datasets": [],
    }


def _normalize_embedded_title(value: str | None) -> str | None:
    if not value:
        return None
    normalized = " ".join(str(value).split()).strip()
    if not normalized or len(normalized) > 500:
        return None
    lowered = normalized.casefold()
    if lowered in {"untitled", "microsoft word", "document"}:
        return None
    return normalized


def _extract_markdown_heading(normalized_text: str) -> str | None:
    first_line = normalized_text.split("\n", 1)[0].strip() if normalized_text else ""
    match = re.fullmatch(r"#\s+(.+)", first_line)
    if not match:
        return None
    title = " ".join(match.group(1).split()).strip()
    return title if 1 <= len(title) <= 500 else None


def _extract_title(normalized_text: str, source_name: str) -> str:
    first_line = normalized_text.split("\n", 1)[0].strip() if normalized_text else ""
    if first_line and len(first_line) <= 160:
        return first_line
    stem = source_name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
    return stem or source_name


def _extract_body_text(normalized_text: str, title: str) -> str:
    if not normalized_text:
        return ""
    first_line, _, remainder = normalized_text.partition("\n")
    normalized_first_line = first_line.strip()
    if normalized_first_line.startswith("# "):
        normalized_first_line = normalized_first_line[2:].strip()
    if normalized_first_line == title and remainder.strip():
        return remainder.strip()
    return normalized_text


def _infer_document_type(source_name: str) -> str | None:
    return "paper" if source_name.lower().endswith(".pdf") else None


def _split_sentences(normalized_text: str) -> list[str]:
    body = normalized_text.replace("\n", " ").strip()
    if not body:
        return []

    parts = re.split(r"(?<=[.!?])\s+", body)
    sentences: list[str] = []
    for part in parts:
        sentence = part.strip()
        if not sentence:
            continue
        sentences.append(sentence)
    return sentences
