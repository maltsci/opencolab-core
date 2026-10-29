import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMProfile(Base):
    __tablename__ = "llm_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(50))
    api_base: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_key: Mapped[str] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_test_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
