import uuid
from typing import TYPE_CHECKING, List
from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.slot import TimeSlot


class Court(Base):
    __tablename__ = "courts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    slots: Mapped[List["TimeSlot"]] = relationship(
        "TimeSlot", back_populates="court", cascade="all, delete-orphan"
    )