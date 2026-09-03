import enum
import uuid
from datetime import date, time, datetime
from typing import TYPE_CHECKING, List
from decimal import Decimal
from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.court import Court
    from app.models.booking import Booking


class SlotMode(str, enum.Enum):
    FULL_COURT = "FULL_COURT"
    SPLIT_MATCH = "SPLIT_MATCH"


class SlotStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    PARTIALLY_BOOKED = "PARTIALLY_BOOKED"
    FULLY_BOOKED = "FULLY_BOOKED"
    BLOCKED = "BLOCKED"


class HoldStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class ClientTier(str, enum.Enum):
    STANDARD = "STANDARD"
    VIP_PAY_ON_SITE = "VIP_PAY_ON_SITE"
    MEMBER = "MEMBER"


class PaymentStatus(str, enum.Enum):
    PAID = "PAID"
    PENDING_ON_SITE = "PENDING_ON_SITE"
    MEMBER_EXEMPT = "MEMBER_EXEMPT"


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    court_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    mode: Mapped[SlotMode] = mapped_column(
        Enum(SlotMode, name="slot_mode_enum", values_callable=lambda x: [e.value for e in x]),
        default=SlotMode.FULL_COURT,
        nullable=False,
    )
    capacity: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    booked_spots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus, name="slot_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=SlotStatus.AVAILABLE,
        nullable=False,
    )

    # Nuevos campos para jugadores y categoría
    players_names: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="4ta", nullable=False)

    court: Mapped["Court"] = relationship("Court", back_populates="slots")
    holds: Mapped[List["SlotHold"]] = relationship(
        "SlotHold", back_populates="slot", cascade="all, delete-orphan"
    )
    bookings: Mapped[List["Booking"]] = relationship(
        "Booking", back_populates="slot", cascade="all, delete-orphan"
    )


class SlotHold(Base):
    __tablename__ = "slot_holds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("time_slots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    spots_held: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    amount_to_pay: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[HoldStatus] = mapped_column(
        Enum(HoldStatus, name="hold_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=HoldStatus.ACTIVE,
        nullable=False,
    )
    payment_reference: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )

    # Nuevos campos de tipo de cliente y estado de pago
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

    slot: Mapped["TimeSlot"] = relationship("TimeSlot", back_populates="holds")