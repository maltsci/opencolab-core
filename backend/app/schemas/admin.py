from pydantic import BaseModel

from app.core.constants import ROLE_RESEARCHER


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = ROLE_RESEARCHER
    display_name: str | None = None


class UpdateUserRequest(BaseModel):
    role: str | None = None
    password: str | None = None
    display_name: str | None = None


class LLMKeyCreate(BaseModel):
    provider: str
    key: str
    name: str
    api_base: str | None = None


class LLMKeyUpdate(BaseModel):
    provider: str
    name: str
    api_base: str | None = None
    key: str | None = None


class LLMKeyResponse(BaseModel):
    id: str
    provider: str
    name: str
    api_base: str | None
    masked_key: str

    model_config = {"from_attributes": True}
