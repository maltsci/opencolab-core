from pydantic import BaseModel


class PaginatedResponse(BaseModel):
    items: list
    next_cursor: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
