from pydantic import BaseModel


class TagCreate(BaseModel):
    name: str
    type: str = "custom"


class TagResponse(BaseModel):
    id: str
    name: str
    type: str

    model_config = {"from_attributes": True}
