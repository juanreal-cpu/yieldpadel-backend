from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.slot import TimeSlot


class PlayerIncident(Base):
    __tablename__ = "player_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    player_phone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    player_name: Mapped[str] = mapped_column(String(100), nullable=False)
    slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("time_slots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    incident_type: Mapped[str] = mapped_column(String(50), default="late_cancellation", nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    slot: Mapped["TimeSlot"] = relationship("TimeSlot", back_populates="incidents")
