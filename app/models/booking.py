from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.slot import ClientTier, PaymentStatus

if TYPE_CHECKING:
    from app.models.slot import TimeSlot


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("time_slots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    spots_booked: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_reference: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    client_tier: Mapped[ClientTier] = mapped_column(
        Enum(ClientTier, name="client_tier_enum", values_callable=lambda x: [e.value for e in x]),
        default=ClientTier.STANDARD,
        nullable=False,
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=PaymentStatus.PAID,
        nullable=False,
    )

    slot: Mapped["TimeSlot"] = relationship("TimeSlot", back_populates="bookings")