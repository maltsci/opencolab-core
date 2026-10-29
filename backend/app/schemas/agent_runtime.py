from pydantic import BaseModel, Field


class CodexRuntimeStatusResponse(BaseModel):
    enabled: bool
    available: bool
    provider: str | None = None
    model: str | None = None
    api_base: str | None = None
    sandbox_url: str
    source: str
    message: str


class CodexRuntimeRunRequest(BaseModel):
    prompt: str = Field(min_length=1)
    cwd: str | None = None
    sandbox: str | None = None


class CodexRuntimeRunResponse(BaseModel):
    status: str
    content: str
    raw_events: list[dict] = Field(default_factory=list)
