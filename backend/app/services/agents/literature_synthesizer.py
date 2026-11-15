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


def _clamp_score(value: Any, *, default: int = 5) -> int:
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(1, min(10, numeric))


def _normalize_hypothesis_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return {
            "name": text[:60],
            "title": text[:120],
            "statement": text,
            "interestingness": 5,
            "feasibility": 5,
            "novelty": 5,
            "composite_score": 5.0,
        }
    if not isinstance(item, dict):
        return None
    statement = _normalize_string(
        item.get("statement") or item.get("Hypothesis") or item.get("experiment") or item.get("title") or item.get("Title")
    )
    title = _normalize_string(item.get("title") or item.get("Title") or item.get("name") or item.get("Name")) or statement[:120]
    name = _normalize_string(item.get("name") or item.get("Name")) or title[:60]
    if not statement and not title:
        return None
    interestingness = _clamp_score(
        item.get("interestingness", item.get("Interestingness")), default=5
    )
    feasibility = _clamp_score(
        item.get("feasibility", item.get("Feasibility")), default=5
    )
    novelty = _clamp_score(
        item.get("novelty", item.get("Novelty")), default=5
    )
    composite = round((interestingness + feasibility + novelty) / 3.0, 2)
    return {
        "name": name,
        "title": title,
        "statement": statement or title,
        "thought": _normalize_string(item.get("thought") or item.get("Thought")),
        "interestingness": interestingness,
        "feasibility": feasibility,
        "novelty": novelty,
        "composite_score": composite,
    }


def _normalize_hypotheses(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for raw_item in value:
        parsed = _normalize_hypothesis_item(raw_item)
        if parsed is None:
            continue
        dedup_key = parsed["title"].casefold()
        if dedup_key in seen_titles:
            continue
        seen_titles.add(dedup_key)
        normalized.append(parsed)
    normalized.sort(key=lambda h: h["composite_score"], reverse=True)
    return normalized


def _normalize_synthesis(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "overview": _normalize_string(payload.get("overview")),
        "key_points": _normalize_string_list(payload.get("key_points")),
        "contradictions": _normalize_string_list(payload.get("contradictions")),
        "gaps": _normalize_string_list(payload.get("gaps")),
    }
    if "hypotheses" in payload:
        normalized["hypotheses"] = _normalize_hypotheses(payload.get("hypotheses"))
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


async def run_literature_synthesizer(
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
    query = str(agent_input.get("query", "")).strip()
    locale = get_input_locale(agent_input)
    language_instruction = get_response_language_instruction(locale)
    retrieved_chunks = await retrieve_chunks(
        query=query,
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

    raw_reflections = agent_input.get("num_reflections", 1)
    try:
        num_reflections = max(1, min(5, int(raw_reflections)))
    except (TypeError, ValueError):
        num_reflections = 1
    idea_archive = agent_input.get("idea_archive") or []
    archive_block = ""
    if isinstance(idea_archive, list) and idea_archive:
        serialized_archive = "\n".join(
            json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
            for item in idea_archive[:10]
        )
        archive_block = (
            "\nPreviously generated ideas/hypotheses (do not duplicate these):\n"
            f"{serialized_archive}\n"
        )

    score_instruction = ""
    if num_reflections > 1 or agent_input.get("score_hypotheses"):
        score_instruction = (
            "Also include key 'hypotheses' (list of objects with keys: name, title, thought, statement, "
            "interestingness (1-10), feasibility (1-10), novelty (1-10)). "
        )

    synthesis_response = await complete_llm_response(
        [
            {
                "role": "system",
                "content": (
                    "You are a literature synthesis assistant. "
                    "Return JSON only with keys: overview, key_points, contradictions, gaps. "
                    f"{score_instruction}"
                    "Keep the overview concise and each list to at most three short items. "
                    f"{language_instruction}"
                    f"{project_instructions}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Query: {query}\n"
                    f"Source IDs: {json.dumps(source_ids)}\n"
                    f"Retrieved chunks: {_serialize_chunks(retrieved_chunks)}"
                    f"{archive_block}"
                ),
            },
        ],
        model=llm_model,
        api_base=llm_api_base,
        api_key=llm_api_key,
        max_tokens=1200,
    )
    synthesis_payload = _parse_json_object(
        synthesis_response,
        fallback={
            "overview": "",
            "key_points": [],
            "contradictions": [],
            "gaps": [],
        },
        raw_field="raw_synthesis",
    )
    if "raw_synthesis" in synthesis_payload and synthesis_response.lstrip().startswith("{"):
        retry_response = await complete_llm_response(
            [
                {
                    "role": "system",
                    "content": (
                        "Return a compact, valid JSON object only with keys: overview, key_points, contradictions, gaps. "
                        f"{score_instruction}"
                        "Use one short overview and at most three short items in each list. "
                        f"{language_instruction}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Query: {query}\n"
                        f"Source IDs: {json.dumps(source_ids)}\n"
                        f"Retrieved chunks: {_serialize_chunks(retrieved_chunks)}"
                        f"{archive_block}"
                    ),
                },
            ],
            model=llm_model,
            api_base=llm_api_base,
            api_key=llm_api_key,
            max_tokens=1200,
        )
        synthesis_payload = _parse_json_object(
            retry_response,
            fallback={
                "overview": "",
                "key_points": [],
                "contradictions": [],
                "gaps": [],
            },
            raw_field="raw_synthesis",
        )

    reflection_rounds_completed = 1
    early_stopped = False
    if num_reflections > 1 and "raw_synthesis" not in synthesis_payload:
        for round_idx in range(2, num_reflections + 1):
            reflection_response = await complete_llm_response(
                [
                    {
                        "role": "system",
                        "content": (
                            f"Round {round_idx}/{num_reflections}. Carefully evaluate the quality, novelty, and feasibility "
                            "of the synthesis and hypotheses you just created. Include any factors that affect the "
                            "Interestingness (1-10), Feasibility (1-10), and Novelty (1-10) ratings. Ensure the hypotheses "
                            "are clear, concise, and non-overlapping with the archive. "
                            "Return the updated JSON object (keys: overview, key_points, contradictions, gaps, hypotheses). "
                            'If the synthesis and hypotheses are already converged and require no major changes, include "I am done" '
                            "at the end of your response after the JSON block. "
                            f"{language_instruction}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Query: {query}\n"
                            f"Previous synthesis JSON: {json.dumps(synthesis_payload, ensure_ascii=False)}\n"
                            f"Retrieved chunks: {_serialize_chunks(retrieved_chunks)}"
                            f"{archive_block}"
                        ),
                    },
                ],
                model=llm_model,
                api_base=llm_api_base,
                api_key=llm_api_key,
                max_tokens=1200,
            )
            reflection_rounds_completed = round_idx
            reflected_payload = _parse_json_object(
                reflection_response,
                fallback=synthesis_payload,
                raw_field="raw_reflection",
            )
            if "raw_reflection" not in reflected_payload:
                synthesis_payload = reflected_payload
            if "I am done" in reflection_response:
                early_stopped = True
                break

    synthesis = _normalize_synthesis(synthesis_payload)
    steps.append(
        build_step_record(
            "synthesize",
            build_agent_step_summary("synthesize_literature", locale=locale),
        )
    )

    validation_response = await complete_llm_response(
        [
            {
                "role": "system",
                "content": (
                    "You validate literature synthesis outputs. "
                    "Return JSON only with keys: is_valid, notes. "
                    f"{language_instruction}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Query: {query}\n"
                    f"Synthesis JSON: {json.dumps(synthesis, ensure_ascii=False)}\n"
                    f"Retrieved chunks: {_serialize_chunks(retrieved_chunks)}"
                ),
            },
        ],
        model=llm_model,
        api_base=llm_api_base,
        api_key=llm_api_key,
        max_tokens=600,
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
            build_agent_step_summary("validate_literature", locale=locale),
        )
    )

    steps.append(
        build_step_record(
            "format_output",
            build_agent_step_summary("format_output", locale=locale),
        )
    )
    trace_payload = build_agent_trace_payload(
        inputs={"query": query, "source_ids": source_ids},
        retrieved_chunks=retrieved_chunks,
        summary_steps=_build_trace_summary_steps(steps),
    )
    output = {
        "agent": "literature_synthesizer",
        "query": query,
        "source_ids": source_ids,
        "overview": synthesis["overview"],
        "key_points": synthesis["key_points"],
        "contradictions": synthesis["contradictions"],
        "gaps": synthesis["gaps"],
        "validation": validation,
        "citations": trace_payload["citations"],
    }
    if "hypotheses" in synthesis or num_reflections > 1 or agent_input.get("score_hypotheses"):
        output["hypotheses"] = synthesis.get("hypotheses", [])
        output["reflection_rounds"] = reflection_rounds_completed
        output["early_stopped"] = early_stopped
    if "raw_synthesis" in synthesis:
        output["raw_synthesis"] = synthesis["raw_synthesis"]

    return {
        "output": output,
        "steps": steps,
        "trace_payload": trace_payload,
    }


NOVELTY_CRITIC_SYSTEM_PROMPT = (
    "You are an ambitious AI researcher who is looking to publish a paper that will contribute "
    "significantly to the field. You have an idea and you want to check if it is novel or not. "
    "I.e., not overlapping significantly with existing literature or already well explored. "
    "Be a harsh critic for novelty, ensure there is a sufficient contribution in the idea for a "
    "new conference or workshop paper. You will be given access to the literature search engine "
    "to decide on novelty. If you have made your decision, include 'Decision made: novel' or "
    "'Decision made: not novel' at the end of your response. Otherwise, return a JSON object "
    'with keys {"Thought": "...", "Query": "..."} to run the next literature search.'
)


async def check_idea_novelty(
    idea: dict[str, Any],
    *,
    source_ids: list[str],
    db,
    llm_model: str | None = None,
    llm_api_base: str | None = None,
    llm_api_key: str | None = None,
    max_num_iterations: int = 10,
    allow_external_lookup: bool | None = None,
) -> dict[str, Any]:
    """Autonomous multi-round novelty check loop with air-gap local Qdrant fallback."""
    from app.core.config import settings

    outbound_allowed = (
        bool(settings.bibliographic_lookup_enabled)
        if allow_external_lookup is None
        else (bool(allow_external_lookup) and bool(settings.bibliographic_lookup_enabled))
    )
    max_rounds = max(1, min(10, int(max_num_iterations)))
    messages: list[dict[str, str]] = [
        {"role": "system", "content": NOVELTY_CRITIC_SYSTEM_PROMPT}
    ]
    last_search_results = "No papers queried yet."
    queries_issued: list[str] = []
    novel = False
    decision_made = False
    rounds_used = 0

    for idx in range(max_rounds):
        rounds_used = idx + 1
        user_prompt = (
            f"Round {rounds_used}/{max_rounds}.\n"
            f"You have this idea:\n{json.dumps(idea, ensure_ascii=False)}\n\n"
            f"The results of the last query are:\n{last_search_results}\n\n"
            "Respond with your Thought and either a JSON object {\"Thought\": \"...\", \"Query\": \"...\"} "
            "for the next search, or conclude with 'Decision made: novel' or 'Decision made: not novel'."
        )
        messages.append({"role": "user", "content": user_prompt})
        reply = await complete_llm_response(
            messages,
            model=llm_model,
            api_base=llm_api_base,
            api_key=llm_api_key,
            max_tokens=600,
        )
        messages.append({"role": "assistant", "content": reply})

        if "decision made: novel" in reply.lower():
            novel = True
            decision_made = True
            break
        if "decision made: not novel" in reply.lower():
            novel = False
            decision_made = True
            break

        parsed = _parse_json_object(reply, fallback={"Query": ""}, raw_field="raw_reply")
        query_str = _normalize_string(parsed.get("Query") or parsed.get("query"))
        if not query_str:
            break
        queries_issued.append(query_str)

        chunks = await retrieve_chunks(
            query=query_str,
            source_ids=source_ids,
            db=db,
            mode="rag",
            top_k=5,
        )
        formatted_hits = [
            f"[{i}] (Local Qdrant Source {c.get('source_id')}): {c.get('text', '')[:300]}"
            for i, c in enumerate(chunks, start=1)
        ]

        if outbound_allowed:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=6.0, trust_env=False) as client:
                    resp = await client.get(
                        "https://api.crossref.org/works",
                        params={"query": query_str, "rows": 3},
                    )
                    if resp.status_code == 200:
                        items = (resp.json().get("message") or {}).get("items") or []
                        for item in items[:3]:
                            title_list = item.get("title") or []
                            title = title_list[0] if title_list else "Untitled"
                            doi = item.get("DOI") or ""
                            abstract = re.sub(r"<[^>]+>", "", str(item.get("abstract") or ""))[:300]
                            formatted_hits.append(
                                f"[Crossref DOI:{doi}] {title} — {abstract or 'No abstract'}"
                            )
            except Exception:
                pass

        last_search_results = (
            "\n".join(formatted_hits) if formatted_hits else "No matching papers found."
        )

    idea["novel"] = novel
    idea["novelty_check"] = {
        "novel": novel,
        "decision_made": decision_made,
        "rounds_used": rounds_used,
        "queries": queries_issued,
        "outbound_used": outbound_allowed,
    }
    return idea

