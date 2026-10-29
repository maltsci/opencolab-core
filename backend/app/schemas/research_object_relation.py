from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

ALLOWED_RELATION_TYPES = ("supports", "contradicts")
ResearchRelationType = Literal["supports", "contradicts"]


def _normalize_optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_optional_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _normalize_confidence(value: Any) -> float:
    score = _normalize_optional_score(value)
    if score is None or not 0 <= score <= 1:
        return 0.0
    return score


def _normalize_citations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "source_id": _normalize_optional_string(item.get("source_id")),
                "chunk_id": _normalize_optional_string(item.get("chunk_id")),
                "snippet": _normalize_optional_string(item.get("snippet")),
                "score": _normalize_optional_score(item.get("score")),
            }
        )
    return normalized


class ResearchRelationCitation(BaseModel):
    source_id: str | None = None
    chunk_id: str | None = None
    snippet: str | None = None
    score: float | None = None


class ResearchRelationEvidence(BaseModel):
    trace_id: str | None = None
    citations: list[ResearchRelationCitation] = Field(default_factory=list)
    note: str | None = None


class ResearchRelationMetadata(BaseModel):
    confidence: float = Field(ge=0, le=1)
    evidence: ResearchRelationEvidence = Field(default_factory=ResearchRelationEvidence)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {
                "confidence": 0.0,
                "evidence": {"citations": []},
            }

        evidence = value.get("evidence")
        normalized_evidence = evidence.copy() if isinstance(evidence, dict) else {}

        legacy_reason = value.get("reason")
        if (
            isinstance(legacy_reason, str)
            and legacy_reason
            and not normalized_evidence.get("note")
        ):
            normalized_evidence["note"] = legacy_reason

        normalized_evidence = {
            "trace_id": _normalize_optional_string(normalized_evidence.get("trace_id")),
            "citations": _normalize_citations(normalized_evidence.get("citations")),
            "note": _normalize_optional_string(normalized_evidence.get("note")),
        }

        return {
            "confidence": _normalize_confidence(value.get("confidence", 0)),
            "evidence": normalized_evidence,
        }


def normalize_relation_metadata(metadata_json: Any) -> dict[str, Any]:
    try:
        return ResearchRelationMetadata.model_validate(metadata_json or {}).model_dump()
    except ValidationError:
        return ResearchRelationMetadata.model_validate(
            {"confidence": 0.0, "evidence": {"citations": []}}
        ).model_dump()


class ResearchObjectRelationCreate(BaseModel):
    relation_type: ResearchRelationType
    target_object_id: str
    metadata_json: ResearchRelationMetadata


class ResearchObjectRelationTarget(BaseModel):
    id: str
    type: str
    title: str | None


class ResearchObjectRelationResponse(BaseModel):
    id: str
    relation_type: ResearchRelationType
    source_object_id: str
    target_object_id: str
    metadata_json: ResearchRelationMetadata
    created_by: str | None
    created_by_type: str
    target_object: ResearchObjectRelationTarget
    created_at: datetime

    model_config = {"from_attributes": True}
