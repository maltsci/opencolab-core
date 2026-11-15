import asyncio
import json
import logging
import re
from typing import Any

from app.models.project import Project
from app.services.agents.base import (
    AgentExecutionResult,
    AgentInputPayload,
    build_agent_step_summary,
    build_step_record,
    get_input_locale,
)
from app.services.llm_service import complete_llm_response, get_response_language_instruction
from app.services.rag_service import retrieve_chunks
from app.services.trace_service import build_agent_trace_payload


def _serialize_chunks(chunks: list[dict[str, Any]]) -> str:
    return json.dumps(
        [
            {
                "source_id": chunk.get("source_id"),
                "chunk_id": chunk.get("chunk_id"),
                "score": chunk.get("score"),
                "text": chunk.get("text", ""),
            }
            for chunk in chunks
        ],
        ensure_ascii=False,
    )


def _parse_json_object(
    raw_text: str,
    *,
    fallback: dict[str, Any],
    raw_field: str,
) -> dict[str, Any]:
    candidates = [raw_text.strip()]
    fenced_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, flags=re.DOTALL)
    candidates.extend(block.strip() for block in fenced_blocks if block.strip())

    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidates.append(raw_text[first_brace : last_brace + 1].strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    fallback[raw_field] = raw_text
    return fallback


def _normalize_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []

    items: list[str] = []
    for item in value:
        if isinstance(item, str):
            normalized = item.strip()
        elif item is None:
            normalized = ""
        else:
            normalized = str(item).strip()
        if normalized:
            items.append(normalized)
    return items


def _normalize_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return default


def _normalize_synthesis(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "summary": _normalize_string(payload.get("summary")),
        "action_items": _normalize_string_list(payload.get("action_items")),
        "response_outline": _normalize_string_list(payload.get("response_outline")),
    }
    if "raw_synthesis" in payload:
        normalized["raw_synthesis"] = payload["raw_synthesis"]
    return normalized


def _normalize_validation(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "is_valid": _normalize_bool(payload.get("is_valid"), default=False),
        "notes": _normalize_string_list(payload.get("notes")),
    }
    if "raw_validation" in payload:
        normalized["raw_validation"] = payload["raw_validation"]
    return normalized


def _build_trace_summary_steps(steps: list[dict[str, str]]) -> list[str]:
    return [step["summary"] for step in steps]


async def run_reviewer_assistant(
    *,
    source_ids: list[str],
    agent_input: AgentInputPayload,
    db,
    llm_model: str | None,
    llm_api_base: str | None,
    llm_api_key: str | None,
    access_user_id: str | None = None,
    access_project_id: str | None = None,
    access_agent_run_id: str | None = None,
) -> AgentExecutionResult:
    review_comments = str(agent_input.get("review_comments", "")).strip()
    locale = get_input_locale(agent_input)
    language_instruction = get_response_language_instruction(locale)
    retrieval_query = f"Reviewer comments: {review_comments}"
    retrieved_chunks = await retrieve_chunks(
        query=retrieval_query,
        source_ids=source_ids,
        db=db,
        mode="rag",
        top_k=5,
        user_id=access_user_id,
        project_id=access_project_id,
        agent_run_id=access_agent_run_id,
    )
    steps = [
        build_step_record(
            "retrieve",
            build_agent_step_summary("retrieve", locale=locale, chunk_count=len(retrieved_chunks)),
        ),
    ]

    project_instructions = ""
    if access_project_id:
        project = await db.get(Project, access_project_id)
        if project and project.instructions and project.instructions.strip():
            project_instructions = (
                f"\nProject instructions: {project.instructions.strip()}"
            )

    synthesis_response = await complete_llm_response(
        [
            {
                "role": "system",
                "content": (
                    "You are a reviewer response assistant. "
                    "Return JSON only with keys: summary, action_items, response_outline. "
                    f"{language_instruction}"
                    f"{project_instructions}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Review comments: {review_comments}\n"
                    f"Source IDs: {json.dumps(source_ids)}\n"
                    f"Retrieved chunks: {_serialize_chunks(retrieved_chunks)}"
                ),
            },
        ],
        model=llm_model,
        api_base=llm_api_base,
        api_key=llm_api_key,
    )
    synthesis = _normalize_synthesis(
        _parse_json_object(
            synthesis_response,
            fallback={
                "summary": "",
                "action_items": [],
                "response_outline": [],
            },
            raw_field="raw_synthesis",
        )
    )
    steps.append(
        build_step_record(
            "synthesize",
            build_agent_step_summary("synthesize_reviewer", locale=locale),
        )
    )

    validation_response = await complete_llm_response(
        [
            {
                "role": "system",
                "content": (
                    "You validate reviewer response drafts. "
                    "Return JSON only with keys: is_valid, notes. "
                    f"{language_instruction}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Review comments: {review_comments}\n"
                    f"Draft JSON: {json.dumps(synthesis, ensure_ascii=False)}\n"
                    f"Retrieved chunks: {_serialize_chunks(retrieved_chunks)}"
                ),
            },
        ],
        model=llm_model,
        api_base=llm_api_base,
        api_key=llm_api_key,
    )
    validation = _normalize_validation(
        _parse_json_object(
            validation_response,
            fallback={"is_valid": False, "notes": []},
            raw_field="raw_validation",
        )
    )
    steps.append(
        build_step_record(
            "validate",
            build_agent_step_summary("validate_reviewer", locale=locale),
        )
    )

    steps.append(
        build_step_record(
            "format_output",
            build_agent_step_summary("format_output", locale=locale),
        )
    )
    trace_payload = build_agent_trace_payload(
        inputs={"review_comments": review_comments, "source_ids": source_ids},
        retrieved_chunks=retrieved_chunks,
        summary_steps=_build_trace_summary_steps(steps),
    )
    output = {
        "agent": "reviewer_assistant",
        "review_comments": review_comments,
        "source_ids": source_ids,
        "summary": synthesis["summary"],
        "action_items": synthesis["action_items"],
        "response_outline": synthesis["response_outline"],
        "validation": validation,
        "citations": trace_payload["citations"],
    }
    if "raw_synthesis" in synthesis:
        output["raw_synthesis"] = synthesis["raw_synthesis"]

    return {
        "output": output,
        "steps": steps,
        "trace_payload": trace_payload,
    }


REVIEWER_SYSTEM_PROMPT_NEG = (
    "You are an AI researcher who is reviewing a paper that was submitted to a prestigious "
    "scientific venue. Be a critical and rigorous reviewer: if a paper is flawed, lacks "
    "traceable evidence, or you are unsure of its validity, give it bad scores and reject it! "
    "Return compact JSON only (no markdown fences) with keys: Summary (under 60 words), "
    "Strengths (2-3 concise strings), Weaknesses (2-3 concise strings), Questions (2-3 concise strings), "
    "Soundness (1-4), Presentation (1-4), Contribution (1-4), Overall (1-10), Confidence (1-5), "
    "Decision ('Accept' or 'Reject')."
)

AREA_CHAIR_SYSTEM_PROMPT = (
    "You are an Area Chair at a top scientific venue. Aggregate the ensemble of reviewer reports "
    "into a single calibrated meta-review compact JSON only (no markdown fences) with keys: "
    "Summary (under 60 words), Strengths (2-3 concise strings), Weaknesses (2-3 concise strings), "
    "Questions (2-3 concise strings), Decision ('Accept' or 'Reject'). Be conservative: if reviewers "
    "raise unaddressed methodological or provenance flaws, default to 'Reject'."
)


def _clamp_int(val: Any, low: int, high: int, default: int) -> int:
    try:
        num = int(round(float(val)))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, num))


def _normalize_peer_review_scorecard(payload: dict[str, Any]) -> dict[str, Any]:
    soundness = _clamp_int(payload.get("Soundness", payload.get("soundness")), 1, 4, 2)
    presentation = _clamp_int(payload.get("Presentation", payload.get("presentation")), 1, 4, 2)
    contribution = _clamp_int(payload.get("Contribution", payload.get("contribution")), 1, 4, 2)
    overall = _clamp_int(payload.get("Overall", payload.get("overall")), 1, 10, 4)
    confidence = _clamp_int(payload.get("Confidence", payload.get("confidence")), 1, 5, 3)
    raw_decision = _normalize_string(payload.get("Decision") or payload.get("decision"))
    decision = "Accept" if raw_decision.lower() == "accept" and overall >= 6 else "Reject"
    return {
        "Summary": _normalize_string(payload.get("Summary") or payload.get("summary")),
        "Strengths": _normalize_string_list(payload.get("Strengths") or payload.get("strengths")),
        "Weaknesses": _normalize_string_list(payload.get("Weaknesses") or payload.get("weaknesses")),
        "Questions": _normalize_string_list(payload.get("Questions") or payload.get("questions")),
        "Soundness": soundness,
        "Presentation": presentation,
        "Contribution": contribution,
        "Overall": overall,
        "Confidence": confidence,
        "Decision": decision,
    }


logger = logging.getLogger(__name__)


async def run_peer_review_ensemble(
    manuscript_text: str,
    *,
    num_reviews_ensemble: int = 5,
    pessimistic: bool = True,
    llm_model: str | None = None,
    llm_api_base: str | None = None,
    llm_api_key: str | None = None,
) -> dict[str, Any]:
    """Run N-way reviewer ensemble with pessimistic prompt and Area Chair score aggregation."""
    ensemble_size = max(1, min(5, int(num_reviews_ensemble)))
    system_prompt = (
        REVIEWER_SYSTEM_PROMPT_NEG
        if pessimistic
        else REVIEWER_SYSTEM_PROMPT_NEG.replace(
            "if a paper is flawed, lacks traceable evidence, or you are unsure of its validity, give it bad scores and reject it!",
            "evaluate the paper fairly and objectively.",
        )
    )
    truncated_manuscript = manuscript_text[:12000]

    async def _run_single_review(idx: int) -> dict[str, Any] | None:
        try:
            raw_resp = await complete_llm_response(
                [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Reviewer #{idx + 1}/{ensemble_size}. Review this manuscript:\n\n"
                            f"{truncated_manuscript}"
                        ),
                    },
                ],
                model=llm_model,
                api_base=llm_api_base,
                api_key=llm_api_key,
                max_tokens=1600,
            )
        except Exception as exc:
            logger.warning("Reviewer #%s failed during ensemble call: %s", idx + 1, exc)
            return None

        parsed = _parse_json_object(
            raw_resp,
            fallback={},
            raw_field="raw_review",
        )
        has_review_key = any(
            k in parsed
            for k in ("Overall", "overall", "Soundness", "soundness", "Summary", "summary")
        )
        if not has_review_key:
            logger.warning("Reviewer #%s returned unparseable review payload", idx + 1)
            return None
        return _normalize_peer_review_scorecard(parsed)

    review_results = await asyncio.gather(
        *[_run_single_review(idx) for idx in range(ensemble_size)]
    )
    individual_reviews = [r for r in review_results if r is not None]
    if not individual_reviews:
        raise ValueError("Peer review ensemble produced no valid reviewer JSON")

    if len(individual_reviews) == 1:
        aggregated = dict(individual_reviews[0])
        aggregated["ensemble_size"] = 1
        aggregated["individual_reviews"] = individual_reviews
        return aggregated

    meta_raw = await complete_llm_response(
        [
            {"role": "system", "content": AREA_CHAIR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Aggregate these {len(individual_reviews)} reviewer reports into a meta-review JSON:\n"
                    f"{json.dumps(individual_reviews, ensure_ascii=False)}"
                ),
            },
        ],
        model=llm_model,
        api_base=llm_api_base,
        api_key=llm_api_key,
        max_tokens=1600,
    )
    meta_parsed = _parse_json_object(
        meta_raw,
        fallback=dict(individual_reviews[0]),
        raw_field="raw_meta_review",
    )
    meta_norm = _normalize_peer_review_scorecard(meta_parsed)

    # Numeric scores are aggregated by ensemble mean (per AI-Scientist perform_review.py:169-189)
    for score_key, low, high in (
        ("Soundness", 1, 4),
        ("Presentation", 1, 4),
        ("Contribution", 1, 4),
        ("Overall", 1, 10),
        ("Confidence", 1, 5),
    ):
        vals = [r[score_key] for r in individual_reviews]
        mean_val = round(sum(vals) / len(vals), 2)
        meta_norm[score_key] = mean_val
    meta_norm["Decision"] = (
        "Accept"
        if str(meta_parsed.get("Decision") or "").strip().lower() == "accept"
        and meta_norm["Overall"] >= 5.5
        else "Reject"
    )
    meta_norm["ensemble_size"] = len(individual_reviews)
    meta_norm["individual_reviews"] = individual_reviews
    return meta_norm

