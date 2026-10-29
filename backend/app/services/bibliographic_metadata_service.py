from __future__ import annotations

from copy import deepcopy
from collections import Counter
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from html import unescape
import re
import unicodedata

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_asset import ResearchAsset
from app.models.bibliographic_metadata import BibliographicMetadataCache
from app.models.trace import SourceExtraction
from app.services.bibliographic_provider_service import (
    NormalizedIdentifier,
    ProviderRecord,
    lookup_provider_record,
)

_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_PMID_PATTERN = re.compile(r"\bPMID\s*:?\s*(\d{1,9})\b", re.IGNORECASE)
_PMCID_PATTERN = re.compile(
    r"\bPMCID\s*:?\s*(?:PMC)?(\d{1,10})\b",
    re.IGNORECASE,
)
_ARXIV_PATTERN = re.compile(
    r"(?:\barXiv\s*:?\s*|arxiv\.org/abs/)"
    r"([a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(v\d+)?\b",
    re.IGNORECASE,
)
_REFERENCES_PATTERN = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:references|bibliography|参考文献)\s*$"
)
_FRONT_MATTER_LIMIT = 12_000
_AUTO_APPLY_TITLE_SIMILARITY = 0.85
_TOPIC_TOKEN_PATTERN = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[-\u2010-\u2015][A-Za-z0-9]+)*"
)
_TOPIC_HTML_TAG_PATTERN = re.compile(r"<[^>\n]{1,500}>")
_TOPIC_EXPLICIT_KEYWORDS_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?"
    r"(?:keywords?|key\s+words|index\s+terms?|主题词|关键词)"
    r"\s*[:：\-–—]\s*(.+?)"
    r"(?=^\s*(?:(?:[IVXLCDM]+|\d+)\.?\s*)?(?:introduction|引言)\b|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_TOPIC_ABSTRACT_PATTERN = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:abstract|摘要)\s*[:：\-–—]?\s*"
)
_TOPIC_ABSTRACT_END_PATTERN = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?"
    r"(?:keywords?|key\s+words|index\s+terms?|introduction|引言|关键词|主题词)"
    r"\b\s*[:：\-–—]?"
)
_TOPIC_SEGMENT_PATTERN = re.compile(r"[.!?;:。！？；：\n\r\t()\[\]{}]+|\s[-–—]\s")
_TOPIC_KEYWORD_SEPARATOR_PATTERN = re.compile(r"[,，;；|]+")
_TOPIC_STOPWORDS = {
    "a",
    "about",
    "abstract",
    "after",
    "against",
    "also",
    "an",
    "among",
    "analysis",
    "and",
    "approach",
    "are",
    "article",
    "as",
    "at",
    "background",
    "be",
    "been",
    "before",
    "between",
    "both",
    "by",
    "can",
    "conclusion",
    "data",
    "different",
    "during",
    "effect",
    "for",
    "from",
    "has",
    "have",
    "into",
    "introduction",
    "is",
    "it",
    "its",
    "main",
    "may",
    "method",
    "methods",
    "more",
    "new",
    "novel",
    "of",
    "on",
    "one",
    "or",
    "our",
    "paper",
    "present",
    "presented",
    "presents",
    "propose",
    "proposed",
    "proposes",
    "result",
    "results",
    "several",
    "show",
    "shown",
    "shows",
    "study",
    "studies",
    "such",
    "than",
    "that",
    "the",
    "their",
    "these",
    "this",
    "to",
    "through",
    "two",
    "under",
    "use",
    "used",
    "uses",
    "using",
    "via",
    "was",
    "we",
    "were",
    "which",
    "widely",
    "with",
    "work",
}
_TOPIC_BOUNDARY_WORDS = {
    "achieve",
    "achieved",
    "achieves",
    "activate",
    "activated",
    "activates",
    "apply",
    "applied",
    "applies",
    "cause",
    "caused",
    "causes",
    "demonstrate",
    "demonstrated",
    "demonstrates",
    "improve",
    "improved",
    "improves",
    "induce",
    "induced",
    "induces",
    "inhibit",
    "inhibited",
    "inhibits",
    "introduce",
    "introduced",
    "introduces",
    "predict",
    "predicted",
    "predicts",
    "reduce",
    "reduced",
    "reduces",
    "reveal",
    "revealed",
    "reveals",
}
_TOPIC_NOISE_TERMS = {
    "align",
    "body",
    "center",
    "class",
    "copyright",
    "div",
    "fig",
    "figure",
    "font",
    "height",
    "href",
    "html",
    "http",
    "https",
    "page",
    "span",
    "style",
    "table",
    "tbody",
    "td",
    "tr",
    "width",
    "www",
}
_TOPIC_GENERIC_HEADS = {
    "algorithm",
    "approach",
    "framework",
    "method",
    "model",
    "representation",
    "restoration",
    "system",
    "technique",
}


def apply_provider_record(
    asset: ResearchAsset,
    record: ProviderRecord | dict,
    *,
    automatic: bool,
) -> bool:
    """Apply a whitelisted provider record while preserving manual titles."""
    validated_record = ProviderRecord.model_validate(record)
    title = " ".join(validated_record.title.split()).strip()
    if not title or len(title) > 500:
        return False

    metadata = dict(asset.catalog_metadata_json or {})
    bibliographic = dict(metadata.get("bibliographic") or {})
    bibliographic.update(
        {
            key: value
            for key, value in validated_record.model_dump(exclude_none=True).items()
            if key
            in {
                "authors",
                "container_title",
                "published_date",
                "doi",
                "pmid",
                "pmcid",
                "arxiv_id",
                "record_url",
            }
        }
    )
    bibliographic.update(
        {
            "source": validated_record.provider,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "verification_status": "verified",
        }
    )
    metadata["bibliographic"] = bibliographic
    if automatic and asset.title_locked:
        asset.catalog_metadata_json = metadata
        return False

    metadata["title"] = title
    asset.title = title
    asset.title_source = validated_record.provider
    asset.title_locked = not automatic
    asset.catalog_metadata_json = metadata
    return True


async def enrich_bibliographic_metadata(
    db: AsyncSession,
    *,
    source_id: str,
    contact_email: str,
    auto_apply: bool,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Resolve one source's local candidates against exact provider records."""
    extraction = await db.scalar(
        select(SourceExtraction).where(SourceExtraction.source_id == source_id)
    )
    if extraction is None:
        return "not_applicable"

    structured = deepcopy(extraction.structured_json or {})
    bibliographic = structured.get("bibliographic")
    if not isinstance(bibliographic, dict):
        extraction.metadata_status = "no_identifier"
        return extraction.metadata_status

    raw_candidates = bibliographic.get("identifier_candidates")
    eligible_candidates = select_primary_identifier_candidates(raw_candidates)
    if not eligible_candidates:
        extraction.metadata_status = "no_identifier"
        bibliographic["resolution"] = {
            "status": "no_identifier",
            "reason_codes": ["no_eligible_identifier"],
        }
        extraction.structured_json = structured
        return extraction.metadata_status

    records: list[ProviderRecord] = []
    for candidate in eligible_candidates:
        identifier = NormalizedIdentifier(
            identifier_type=str(candidate["identifier_type"]),
            value=str(candidate["value"]),
        )
        record = await lookup_provider_record_cached(
            db,
            identifier=identifier,
            contact_email=contact_email,
            client=client,
        )
        if record is not None:
            records.append(record)

    extraction.metadata_attempts += 1
    extraction.metadata_checked_at = datetime.now(UTC)
    merged_records = _merge_provider_records(records)
    bibliographic["provider_candidates"] = [
        record.model_dump(exclude_none=True) for record in merged_records
    ]
    if not merged_records:
        status = "needs_review"
        reason_codes = ["provider_record_not_found"]
    elif len(merged_records) > 1:
        status = "needs_review"
        reason_codes = ["conflicting_provider_records"]
    else:
        record = merged_records[0]
        local_title = _local_title_candidate(bibliographic)
        title_matches = bool(
            local_title
            and _title_similarity(local_title, record.title)
            >= _AUTO_APPLY_TITLE_SIMILARITY
        )
        asset = await db.scalar(
            select(ResearchAsset).where(ResearchAsset.source_id == source_id)
        )
        if asset is not None and (asset.title_locked or (auto_apply and title_matches)):
            apply_provider_record(asset, record, automatic=True)
            status = "resolved"
            reason_codes = []
        else:
            status = "needs_review"
            reason_codes = (
                ["auto_apply_disabled"] if not auto_apply else ["title_mismatch"]
            )

    bibliographic["resolution"] = {
        "status": status,
        "reason_codes": reason_codes,
    }
    extraction.structured_json = structured
    extraction.metadata_status = status
    extraction.metadata_error = None
    extraction.metadata_next_attempt_at = None
    await db.flush()
    return status


async def lookup_provider_record_cached(
    db: AsyncSession,
    *,
    identifier: NormalizedIdentifier,
    contact_email: str,
    client: httpx.AsyncClient | None = None,
) -> ProviderRecord | None:
    """Use a durable cache for exact public identifier lookups."""
    provider = {
        "doi": "crossref",
        "pmid": "pubmed",
        "pmcid": "pmc",
        "arxiv": "arxiv",
    }[identifier.identifier_type]
    now = datetime.now(UTC)
    cached = await db.scalar(
        select(BibliographicMetadataCache).where(
            BibliographicMetadataCache.provider == provider,
            BibliographicMetadataCache.identifier_type == identifier.identifier_type,
            BibliographicMetadataCache.normalized_identifier == identifier.value,
            BibliographicMetadataCache.expires_at > now,
        )
    )
    if cached is not None:
        if cached.result_status == "not_found":
            return None
        return ProviderRecord.model_validate(cached.record_json)

    record = await lookup_provider_record(
        identifier,
        contact_email=contact_email,
        client=client,
    )
    expires_at = now + timedelta(days=30 if record is not None else 1)
    existing = await db.scalar(
        select(BibliographicMetadataCache).where(
            BibliographicMetadataCache.provider == provider,
            BibliographicMetadataCache.identifier_type == identifier.identifier_type,
            BibliographicMetadataCache.normalized_identifier == identifier.value,
        )
    )
    values = {
        "record_json": record.model_dump(exclude_none=True) if record else {},
        "result_status": "found" if record else "not_found",
        "fetched_at": now,
        "expires_at": expires_at,
    }
    if existing is None:
        db.add(
            BibliographicMetadataCache(
                provider=provider,
                identifier_type=identifier.identifier_type,
                normalized_identifier=identifier.value,
                **values,
            )
        )
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    await db.flush()
    return record


def _local_title_candidate(bibliographic: dict) -> str | None:
    candidate = bibliographic.get("local_title_candidate")
    if not isinstance(candidate, dict):
        return None
    value = candidate.get("value")
    return str(value).strip() if value else None


def _merge_provider_records(records: list[ProviderRecord]) -> list[ProviderRecord]:
    merged: dict[str, ProviderRecord] = {}
    for record in records:
        key = (
            f"doi:{record.doi.lower()}"
            if record.doi
            else f"title:{_normalize_title(record.title)}"
        )
        current = merged.get(key)
        if current is None:
            merged[key] = record
            continue
        preferred = record if record.provider == "crossref" else current
        secondary = current if preferred is record else record
        merged[key] = preferred.model_copy(
            update={
                "pmid": preferred.pmid or secondary.pmid,
                "pmcid": preferred.pmcid or secondary.pmcid,
                "arxiv_id": preferred.arxiv_id or secondary.arxiv_id,
                "authors": preferred.authors or secondary.authors,
                "container_title": preferred.container_title
                or secondary.container_title,
                "published_date": preferred.published_date or secondary.published_date,
            }
        )
    return list(merged.values())


def _title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None, _normalize_title(left), _normalize_title(right)
    ).ratio()


def _normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


def build_local_bibliographic_metadata(
    *,
    text: str,
    title: str,
    title_source: str = "parsed_text",
    title_confidence: str = "medium",
    embedded_keywords: str | None = None,
) -> dict:
    """Extract deterministic local bibliographic candidates from parsed text."""
    reference_match = _REFERENCES_PATTERN.search(text)
    references_start = reference_match.start() if reference_match else None
    abstract_match = _TOPIC_ABSTRACT_PATTERN.search(text)
    front_matter_end = (
        abstract_match.start() if abstract_match is not None else _FRONT_MATTER_LIMIT
    )
    candidates: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    def add_candidate(
        identifier_type: str,
        value: str,
        position: int,
        *,
        explicit: bool,
    ) -> None:
        normalized_value = _normalize_identifier(identifier_type, value)
        key = (identifier_type, normalized_value)
        if not normalized_value or key in seen:
            return
        seen.add(key)

        if references_start is not None and position >= references_start:
            source = "references"
            confidence = "low"
            eligible_for_lookup = False
        elif position <= front_matter_end and explicit:
            source = "front_matter"
            confidence = "high"
            eligible_for_lookup = True
        else:
            source = "body"
            confidence = "low"
            eligible_for_lookup = False

        candidates.append(
            {
                "identifier_type": identifier_type,
                "value": normalized_value,
                "source": source,
                "confidence": confidence,
                "eligible_for_lookup": eligible_for_lookup,
            }
        )

    for match in _DOI_PATTERN.finditer(text):
        prefix = text[max(0, match.start() - 32) : match.start()].lower()
        explicit = "doi" in prefix
        add_candidate("doi", match.group(0), match.start(), explicit=explicit)

    for match in _PMID_PATTERN.finditer(text):
        add_candidate("pmid", match.group(1), match.start(), explicit=True)

    for match in _PMCID_PATTERN.finditer(text):
        add_candidate("pmcid", f"PMC{match.group(1)}", match.start(), explicit=True)

    for match in _ARXIV_PATTERN.finditer(text):
        base_identifier = match.group(1)
        version = match.group(2) or ""
        add_candidate(
            "arxiv",
            f"{base_identifier}{version}",
            match.start(),
            explicit=True,
        )

    has_lookup_candidate = any(
        candidate["eligible_for_lookup"] for candidate in candidates
    )
    return {
        "local_title_candidate": {
            "value": title,
            "source": title_source,
            "confidence": title_confidence,
        },
        "identifier_candidates": candidates,
        "keywords": extract_topic_keywords(
            title=title,
            text=text,
            embedded_keywords=embedded_keywords,
        ),
        "provider_candidates": [],
        "resolution": {
            "status": "pending" if has_lookup_candidate else "no_identifier",
            "reason_codes": [],
        },
    }


def select_primary_identifier_candidates(raw_candidates: object) -> list[dict]:
    """Return at most one high-confidence paper identifier per identifier type."""
    if not isinstance(raw_candidates, list):
        return []

    selected: list[dict] = []
    seen_types: set[str] = set()
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        identifier_type = str(candidate.get("identifier_type") or "").strip()
        if (
            not identifier_type
            or identifier_type in seen_types
            or candidate.get("source") != "front_matter"
            or candidate.get("confidence") != "high"
            or candidate.get("eligible_for_lookup") is not True
        ):
            continue
        seen_types.add(identifier_type)
        selected.append(dict(candidate))
    return selected


def extract_topic_keywords(
    *,
    title: str,
    text: str,
    embedded_keywords: str | None = None,
    limit: int = 10,
) -> list[str]:
    """Extract conservative academic keyphrases supported by the paper title."""
    if limit <= 0:
        return []

    cleaned_text = _clean_topic_text(text[:_FRONT_MATTER_LIMIT])
    explicit_keywords = _extract_explicit_keywords(
        embedded_keywords,
        cleaned_text,
    )
    abstract_text = _extract_abstract_text(cleaned_text)
    title_candidates = Counter(_extract_phrase_candidates(title))
    abstract_candidates = Counter(_extract_phrase_candidates(abstract_text))

    explicit_keyword_set = set(explicit_keywords)
    scored: list[tuple[float, int, str]] = []
    for keyword in (
        title_candidates.keys()
        | abstract_candidates.keys()
        | explicit_keyword_set
    ):
        if title_candidates[keyword] <= 0:
            continue
        if abstract_candidates[keyword] <= 0 and keyword not in explicit_keyword_set:
            continue
        word_count = len(keyword.split())
        score = (
            title_candidates[keyword] * 12
            + abstract_candidates[keyword] * 4
            + (20 if keyword in explicit_keyword_set else 0)
            + word_count * 2
        )
        scored.append((score, word_count, keyword))

    selected: list[str] = []
    for _, _, keyword in sorted(
        scored,
        key=lambda item: (-item[1], -item[0], item[2]),
    ):
        _append_non_redundant_keyword(selected, keyword, limit=limit)
        if len(selected) >= limit:
            break
    return selected[:limit]


def _clean_topic_text(value: str) -> str:
    cleaned = unescape(value)
    cleaned = _TOPIC_HTML_TAG_PATTERN.sub(" ", cleaned)
    return "\n".join(" ".join(line.split()) for line in cleaned.splitlines())


def _extract_explicit_keywords(
    embedded_keywords: str | None,
    cleaned_text: str,
) -> list[str]:
    values: list[str] = []
    if embedded_keywords:
        values.append(embedded_keywords)
    match = _TOPIC_EXPLICIT_KEYWORDS_PATTERN.search(cleaned_text)
    if match is not None:
        values.append(match.group(1))

    keywords: list[str] = []
    seen: set[str] = set()
    for value in values:
        for raw_keyword in _TOPIC_KEYWORD_SEPARATOR_PATTERN.split(value):
            keyword = _normalize_topic_phrase(raw_keyword)
            if (
                not keyword
                or keyword in seen
                or len(keyword) > 100
                or not _is_meaningful_topic_phrase(keyword)
            ):
                continue
            seen.add(keyword)
            keywords.append(keyword)
    return keywords


def _extract_abstract_text(cleaned_text: str) -> str:
    reference_match = _REFERENCES_PATTERN.search(cleaned_text)
    front_matter = (
        cleaned_text[: reference_match.start()]
        if reference_match is not None
        else cleaned_text
    )
    abstract_match = _TOPIC_ABSTRACT_PATTERN.search(front_matter)
    if abstract_match is None:
        return front_matter[:4_000]
    abstract = front_matter[abstract_match.end() :]
    end_match = _TOPIC_ABSTRACT_END_PATTERN.search(abstract)
    return abstract[: end_match.start()] if end_match is not None else abstract[:4_000]


def _extract_phrase_candidates(value: str) -> list[str]:
    candidates: list[str] = []
    normalized_value = _clean_topic_text(value).replace("\n", " ")
    for segment in _TOPIC_SEGMENT_PATTERN.split(normalized_value):
        run: list[str] = []
        for raw_token in _TOPIC_TOKEN_PATTERN.findall(segment):
            token_parts = re.split(r"[-\u2010-\u2015]+", raw_token.casefold())
            for token in token_parts:
                if (
                    len(token) < 2
                    or token in _TOPIC_STOPWORDS
                    or token in _TOPIC_BOUNDARY_WORDS
                    or token in _TOPIC_NOISE_TERMS
                ):
                    candidates.extend(_phrase_windows(run))
                    run = []
                    continue
                run.append(token)
        candidates.extend(_phrase_windows(run))
    return candidates


def _phrase_windows(tokens: list[str]) -> list[str]:
    if len(tokens) < 2:
        return []
    max_size = min(8, len(tokens))
    phrases: list[str] = []
    for size in range(max_size, 1, -1):
        for start in range(0, len(tokens) - size + 1):
            phrase = " ".join(tokens[start : start + size])
            if _is_meaningful_topic_phrase(phrase):
                phrases.append(phrase)
    return phrases


def _normalize_topic_phrase(value: str) -> str:
    cleaned = _clean_topic_text(value).casefold()
    tokens: list[str] = []
    for raw_token in _TOPIC_TOKEN_PATTERN.findall(cleaned):
        tokens.extend(
            token
            for token in re.split(r"[-\u2010-\u2015]+", raw_token)
            if token
        )
    return " ".join(tokens)


def _is_meaningful_topic_phrase(keyword: str) -> bool:
    tokens = keyword.split()
    return bool(
        tokens
        and len(tokens) <= 8
        and any(len(token) >= 3 for token in tokens)
        and not any(token in _TOPIC_NOISE_TERMS for token in tokens)
        and not all(token in _TOPIC_STOPWORDS for token in tokens)
        and not (
            len(tokens) == 2
            and tokens[1] in _TOPIC_GENERIC_HEADS
        )
    )


def _append_non_redundant_keyword(
    selected: list[str],
    keyword: str,
    *,
    limit: int,
) -> None:
    if len(selected) >= limit or keyword in selected:
        return
    keyword_tokens = keyword.split()
    for selected_keyword in selected:
        selected_tokens = selected_keyword.split()
        if _contains_token_sequence(selected_tokens, keyword_tokens):
            return
        if _contains_token_sequence(keyword_tokens, selected_tokens):
            return
    selected.append(keyword)


def _contains_token_sequence(container: list[str], candidate: list[str]) -> bool:
    if len(candidate) > len(container):
        return False
    return any(
        container[index : index + len(candidate)] == candidate
        for index in range(len(container) - len(candidate) + 1)
    )


def _normalize_identifier(identifier_type: str, value: str) -> str:
    normalized = value.strip()
    if identifier_type == "doi":
        normalized = normalized.rstrip(".,;:").lower()
        while normalized.endswith(")") and normalized.count("(") < normalized.count(
            ")"
        ):
            normalized = normalized[:-1]
        return normalized
    if identifier_type == "pmcid":
        return normalized.upper()
    if identifier_type == "arxiv":
        return normalized.lower()
    return normalized
