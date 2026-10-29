from datetime import datetime

from pydantic import BaseModel


class LLMProfileCreate(BaseModel):
    name: str
    provider: str
    api_base: str | None = None
    key: str
    model: str


class LLMProfileUpdate(BaseModel):
    name: str
    provider: str
    api_base: str | None = None
    key: str | None = None
    model: str


class LLMProfileResponse(BaseModel):
    id: str
    name: str
    provider: str
    api_base: str | None
    model: str
    status: str
    last_tested_at: datetime | None
    last_test_result: str | None
    masked_key: str

    model_config = {"from_attributes": True}


class LLMProfileProbeRequest(BaseModel):
    profile_id: str | None = None
    provider: str
    api_base: str | None = None
    key: str | None = None


class LLMProfileModelProbeRequest(LLMProfileProbeRequest):
    model: str


class LLMProfileModelsResponse(BaseModel):
    models: list[str]


class LLMProfileProbeResponse(BaseModel):
    ok: bool
    status: str
    message: str
    models: list[str] | None = None
