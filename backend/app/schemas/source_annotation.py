from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class SourceAnnotationCreate(BaseModel):
    selected_text: str = Field(min_length=1, max_length=5000)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_offsets(self) -> "SourceAnnotationCreate":
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        self.selected_text = self.selected_text.strip()
        if not self.selected_text:
            raise ValueError("selected_text must not be blank")
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class SourceAnnotationResponse(BaseModel):
    id: str
    source_id: str
    selected_text: str
    start_offset: int
    end_offset: int
    note: str | None
    color: str
    created_at: datetime
    updated_at: datetime
    author_name: str | None = None
    can_delete: bool = False

    model_config = {"from_attributes": True}
