from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TaskDefinitionRecord(Base):
    __tablename__ = "task_definitions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    workflow_id: Mapped[str] = mapped_column(String(100), index=True)
    skill_pack_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    starter_prompts: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    project_context_policy: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        server_default="{}",
    )
    result_presentation: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        server_default="{}",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
    )
    project_ids: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
