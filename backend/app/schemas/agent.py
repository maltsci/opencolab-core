from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.research_object import ResearchObjectResponse
from app.schemas.research_object_relation import (
    ResearchObjectRelationResponse,
    ResearchRelationType,
)


AgentName = Literal["literature_synthesizer", "reviewer_assistant"]


class AgentRunTracePayload(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    retrieval: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    summary_steps: list[str] = Field(default_factory=list)


class AgentRunStepResponse(BaseModel):
    name: str
    status: str
    summary: str


class AgentRunCreateRequest(BaseModel):
    session_id: str
    agent: str
    source_ids: list[str] = Field(default_factory=list)
    input: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_agent_specific_rules(self) -> "AgentRunCreateRequest":
        if self.agent == "literature_synthesizer" and len(self.source_ids) < 2:
            raise ValueError("Literature Synthesizer requires at least 2 sources.")
        if self.agent == "literature_synthesizer":
            self._require_non_empty_input_text("query")
        elif self.agent == "reviewer_assistant":
            self._require_non_empty_input_text("review_comments")
        return self

    def _require_non_empty_input_text(self, key: str) -> None:
        value = self.input.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is required.")


class AgentRunResponse(BaseModel):
    id: str
    session_id: str
    user_id: str | None = None
    workflow_run_id: str | None = None
    agent_name: str
    status: str
    input: dict[str, Any] = Field(default_factory=dict, validation_alias="input_json")
    steps: list[AgentRunStepResponse] = Field(
        default_factory=list,
        validation_alias="steps_json",
    )
    output: dict[str, Any] = Field(default_factory=dict, validation_alias="output_json")
    error_message: str | None = None
    trace: AgentRunTracePayload | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def resolve_trace_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            data = {
                "id": getattr(data, "id"),
                "session_id": getattr(data, "session_id"),
                "user_id": getattr(data, "user_id", None),
                "workflow_run_id": getattr(data, "workflow_run_id", None),
                "agent_name": getattr(data, "agent_name"),
                "status": getattr(data, "status"),
                "input_json": getattr(data, "input_json", {}),
                "steps_json": getattr(data, "steps_json", []),
                "output_json": getattr(data, "output_json", {}),
                "error_message": getattr(data, "error_message", None),
                "trace": getattr(data, "trace", None),
                "traces": getattr(data, "traces", None),
                "created_at": getattr(data, "created_at", None),
                "updated_at": getattr(data, "updated_at", None),
            }

        if data.get("trace") is None:
            data["trace"] = cls._resolve_trace_from_collection(data.get("traces"))
        else:
            data["trace"] = cls._normalize_trace_payload(data["trace"])
        return data

    model_config = {"from_attributes": True}

    @classmethod
    def _resolve_trace_from_collection(
        cls,
        traces: Any,
    ) -> dict[str, Any] | None:
        if not traces:
            return None

        selected = max(traces, key=cls._trace_sort_key)
        return cls._normalize_trace_payload(selected)

    @staticmethod
    def _trace_sort_key(trace: Any) -> tuple[str, str]:
        created_at = AgentRunResponse._read_value(trace, "created_at")
        trace_id = AgentRunResponse._read_value(trace, "id") or ""
        return (created_at.isoformat() if created_at is not None else "", str(trace_id))

    @staticmethod
    def _normalize_trace_payload(trace: Any) -> dict[str, Any] | None:
        if trace is None:
            return None
        if isinstance(trace, AgentRunTracePayload):
            return trace.model_dump()

        inputs = AgentRunResponse._read_value(trace, "inputs")
        if inputs is not None:
            return {
                "inputs": inputs,
                "retrieval": AgentRunResponse._read_value(trace, "retrieval") or [],
                "citations": AgentRunResponse._read_value(trace, "citations") or [],
                "summary_steps": AgentRunResponse._read_value(trace, "summary_steps") or [],
            }

        return {
            "inputs": AgentRunResponse._read_value(trace, "inputs_json") or {},
            "retrieval": AgentRunResponse._read_value(trace, "retrieval_json") or [],
            "citations": AgentRunResponse._read_value(trace, "citations_json") or [],
            "summary_steps": AgentRunResponse._read_value(trace, "summary_steps_json") or [],
        }

    @staticmethod
    def _read_value(data: Any, key: str) -> Any:
        if isinstance(data, dict):
            return data.get(key)
        return getattr(data, key, None)


class AgentRunSaveMemoryRelationRequest(BaseModel):
    enabled: bool = False
    relation_type: ResearchRelationType | None = None
    target_object_id: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_when_enabled(self) -> "AgentRunSaveMemoryRelationRequest":
        if self.enabled and (
            self.relation_type is None or not self.target_object_id
        ):
            raise ValueError(
                "relation_type and target_object_id are required when relation is enabled"
            )
        return self


class AgentRunSaveMemoryRequest(BaseModel):
    type: Literal["hypothesis", "discussion"]
    title: str | None = Field(default=None, max_length=500)
    content: str
    relation: AgentRunSaveMemoryRelationRequest = Field(
        default_factory=AgentRunSaveMemoryRelationRequest
    )


class AgentRunSaveMemoryResponse(BaseModel):
    research_object: ResearchObjectResponse
    relation: ResearchObjectRelationResponse | None = None
