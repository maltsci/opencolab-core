import json
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
