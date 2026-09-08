from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timezone import get_bogota_now

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.slot import TimeSlot


class ClubPresence(Base):
    __tablename__ = "club_presences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    player_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    player_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=False, default="", index=True)
    check_in_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_bogota_now, nullable=False
    )
    check_out_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_inside: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    membership_tier: Mapped[str] = mapped_column(String(50), default="ESTANDAR", nullable=False)
    current_slot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("time_slots.id", ondelete="SET NULL"), nullable=True, index=True
    )

    customer: Mapped[Optional["Customer"]] = relationship("Customer", lazy="joined")
    slot: Mapped[Optional["TimeSlot"]] = relationship("TimeSlot", lazy="joined")
