from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    user: "UserResponse"


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    role: str

    model_config = {"from_attributes": True}
