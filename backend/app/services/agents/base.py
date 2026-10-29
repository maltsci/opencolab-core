from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession


class AgentStepRecord(TypedDict):
    name: str
    status: str
    summary: str


class AgentExecutionResult(TypedDict):
    output: dict[str, Any]
    steps: list[AgentStepRecord]
    trace_payload: "AgentTracePayload"

AgentInputPayload = dict[str, Any]


class AgentTracePayload(TypedDict):
    inputs: dict[str, Any]
    retrieval: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    summary_steps: list[str]


class AgentRunner(Protocol):
    def __call__(
        self,
        *,
        source_ids: list[str],
        agent_input: AgentInputPayload,
        db: AsyncSession | None,
        llm_model: str | None,
        llm_api_base: str | None,
        llm_api_key: str | None,
        access_user_id: str | None,
        access_project_id: str | None,
        access_agent_run_id: str | None,
    ) -> Awaitable[AgentExecutionResult]: ...


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    name: str
    runner: AgentRunner


def is_chinese_locale(locale: str | None) -> bool:
    normalized_locale = (locale or "").strip().lower()
    return normalized_locale.startswith("zh")


def get_input_locale(agent_input: AgentInputPayload) -> str | None:
    value = agent_input.get("locale")
    return value.strip() if isinstance(value, str) and value.strip() else None


def build_step_record(
    name: str,
    summary: str,
    status: str = "completed",
) -> AgentStepRecord:
    return {
        "name": name,
        "status": status,
        "summary": summary,
    }


def build_agent_step_summary(
    key: str,
    *,
    locale: str | None,
    chunk_count: int | None = None,
) -> str:
    if is_chinese_locale(locale):
        if key == "retrieve" and chunk_count is not None:
            return f"检索到 {chunk_count} 个片段"
        if key == "synthesize_literature":
            return "已生成文献综合草稿"
        if key == "validate_literature":
            return "已完成文献综合校验"
        if key == "synthesize_reviewer":
            return "已生成审稿回复草稿"
        if key == "validate_reviewer":
            return "已完成审稿回复校验"
        if key == "format_output":
            return "已整理结构化输出"
        raise KeyError(f"Unknown agent step summary key: {key}")

    if key == "retrieve" and chunk_count is not None:
        return f"retrieved {chunk_count} chunks"
    if key == "synthesize_literature":
        return "generated synthesis draft"
    if key == "validate_literature":
        return "validated synthesis draft"
    if key == "synthesize_reviewer":
        return "generated reviewer response draft"
    if key == "validate_reviewer":
        return "validated reviewer response draft"
    if key == "format_output":
        return "prepared structured response"
    raise KeyError(f"Unknown agent step summary key: {key}")
