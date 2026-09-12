import enum
import uuid
from datetime import date, time, datetime
from typing import TYPE_CHECKING, List, Optional
from decimal import Decimal
from sqlalchemy import (
    Boolean,
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
    from app.models.incident import PlayerIncident


class SlotMode(str, enum.Enum):
    FULL_COURT = "FULL_COURT"
    SPLIT_MATCH = "SPLIT_MATCH"


class SlotStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    PARTIALLY_BOOKED = "PARTIALLY_BOOKED"
    FULLY_BOOKED = "FULLY_BOOKED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class HoldStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class ClientTier(str, enum.Enum):
    STANDARD = "STANDARD"
    VIP_PAY_ON_SITE = "VIP_PAY_ON_SITE"
    MEMBER = "MEMBER"
    TAPIA = "TAPIA"
    COELLO = "COELLO"
    GALAN = "GALAN"
    CHINGOTTO = "CHINGOTTO"
    LEBRON = "LEBRON"
    ESTANDAR = "ESTANDAR"


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
        Enum(SlotMode, name="slot_mode_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=SlotMode.FULL_COURT,
        nullable=False,
    )
    capacity: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    booked_spots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus, name="slot_status_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=SlotStatus.AVAILABLE,
        nullable=False,
    )

    # Nuevos campos para jugadores y categoría
    players_names: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="4ta", nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Campos para academia, yield y promociones
    slot_type: Mapped[str] = mapped_column(String(50), default="MATCH", nullable=False)
    instructor_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_promo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # Campos para Torneos Americanos y Eventos
    tournament_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    prize_pool: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    prize_money_cop: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    prize_points: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    tournament_category: Mapped[Optional[str]] = mapped_column(String(50), default="5ta", nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    spots_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    match_type: Mapped[Optional[str]] = mapped_column(String(50), default="MATCH", nullable=True)
    tournament_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    winners_names: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    runner_up_names: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_finished: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Soporte Multideporte
    sport_type: Mapped[str] = mapped_column(String(50), default="PADEL", nullable=False)

    # Campos de Retos Oficiales (Challenge State Machine)
    is_challenge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    challenge_bet: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    team_a_names: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    team_b_names: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Campos de compatibilidad y control por club
    club_id: Mapped[Optional[int]] = mapped_column(Integer, default=1, nullable=True)
    price_total_cop: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    price_per_player_cop: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    @property
    def price_val(self) -> Decimal:
        return self.total_price

    @price_val.setter
    def price_val(self, value: Decimal):
        self.total_price = value
        self.price = value
        self.price_total_cop = value
        if self.capacity:
            self.price_per_player_cop = value / self.capacity


    court: Mapped["Court"] = relationship("Court", back_populates="slots", lazy="selectin")
    holds: Mapped[List["SlotHold"]] = relationship(
        "SlotHold", back_populates="slot", cascade="all, delete-orphan"
    )
    bookings: Mapped[List["Booking"]] = relationship(
        "Booking", back_populates="slot", cascade="all, delete-orphan"
    )
    incidents: Mapped[List["PlayerIncident"]] = relationship(
        "PlayerIncident", back_populates="slot", cascade="all, delete-orphan"
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
        Enum(HoldStatus, name="hold_status_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=HoldStatus.ACTIVE,
        nullable=False,
    )
    payment_reference: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )

    # Nuevos campos de tipo de cliente y estado de pago
    client_tier: Mapped[ClientTier] = mapped_column(
        Enum(ClientTier, name="client_tier_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=ClientTier.STANDARD,
        nullable=False,
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=PaymentStatus.PAID,
        nullable=False,
    )

    slot: Mapped["TimeSlot"] = relationship("TimeSlot", back_populates="holds")