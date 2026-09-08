import uuid
from datetime import date, time, datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.court import Court
    from app.models.customer import Customer


class AcademyClass(Base):
    __tablename__ = "academy_classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)  # KIDS_INICIACION, KIDS_INTERMEDIO, INICIACION_6_7, MEDIO_4_5, AVANZADO
    target_age: Mapped[str] = mapped_column(String(50), default="ADULTOS", nullable=False)  # ADULTOS, KIDS_SUB10, KIDS_SUB14, JUNIOR
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    court_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coach_name: Mapped[str] = mapped_column(String(100), nullable=False)
    max_students: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    price_per_student: Mapped[int] = mapped_column(Integer, default=35000, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    court: Mapped["Court"] = relationship("Court", lazy="joined")
    enrollments: Mapped[List["AcademyEnrollment"]] = relationship(
        "AcademyEnrollment", back_populates="academy_class", cascade="all, delete-orphan", lazy="selectin"
    )


class AcademyEnrollment(Base):
    __tablename__ = "academy_enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    academy_class_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("academy_classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False
    )  # INCLUDED_IN_MEMBERSHIP, PENDING, PAID
    amount_charged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    academy_class: Mapped["AcademyClass"] = relationship("AcademyClass", back_populates="enrollments")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="academy_enrollments", lazy="joined", overlaps="player")
    player: Mapped["Customer"] = relationship("Customer", lazy="joined", overlaps="customer,academy_enrollments")
