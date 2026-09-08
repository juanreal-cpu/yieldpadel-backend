import enum
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.membership import MembershipPlan
    from app.models.academy import AcademyEnrollment


class MembershipTier(str, enum.Enum):
    TAPIA = "TAPIA"
    COELLO = "COELLO"
    GALAN = "GALAN"
    CHINGOTTO = "CHINGOTTO"
    LEBRON = "LEBRON"
    ESTANDAR = "ESTANDAR"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), default="4ta", nullable=False)
    client_type: Mapped[str] = mapped_column(String(50), default="Estándar", nullable=False)
    membership_tier: Mapped[str] = mapped_column(String(50), default="ESTANDAR", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Perfil Enriquecido de Jugador
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # MASCULINO, FEMENINO, OTRO
    preferred_music: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    preferred_play_time: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Vinculación y Vigencia de Membresía
    membership_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("membership_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    membership_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    membership_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    academy_classes_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Perfil de Menor de Edad / Dependiente (Kid Apadrinado)
    is_minor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    guardian_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    guardian_relationship: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # PADRE, MADRE, TUTOR

    # Módulo de Primera Visita y Onboarding
    total_bookings_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_first_visit: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    onboarding_status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)  # PENDING, WELCOMED, MEMBER_OFFERED

    # Sistema de Ranking, Títulos y Ascensos Automáticos
    ranking_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    titles_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    category_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    promotion_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recommended_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    membership_plan: Mapped[Optional["MembershipPlan"]] = relationship(
        "MembershipPlan", back_populates="customers", lazy="joined"
    )
    guardian: Mapped[Optional["Customer"]] = relationship(
        "Customer",
        remote_side="Customer.id",
        foreign_keys=[guardian_id],
        backref="dependents",
        lazy="selectin",
    )
    academy_enrollments: Mapped[List["AcademyEnrollment"]] = relationship(
        "AcademyEnrollment", back_populates="customer", cascade="all, delete-orphan", lazy="selectin", overlaps="player"
    )


# Alias Player para soporte semántico
Player = Customer
