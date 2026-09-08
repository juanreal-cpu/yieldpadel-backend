import enum
from datetime import time, datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, Integer, String, Time, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer


class MembershipPlan(Base):
    __tablename__ = "membership_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, default=time(6, 0), nullable=False)
    end_time: Mapped[time] = mapped_column(Time, default=time(23, 59), nullable=False)
    max_daily_hours: Mapped[float] = mapped_column(Float, default=1.5, nullable=False)
    includes_academy_classes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    monthly_classes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    includes_beverage_perk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    americano_discount_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    monthly_price_cop: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    badge_label: Mapped[Optional[str]] = mapped_column(String(50), default="PLAN SOCIO", nullable=True)
    card_gradient: Mapped[Optional[str]] = mapped_column(
        String(100), default="from-slate-800 to-indigo-900", nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    customers: Mapped[List["Customer"]] = relationship("Customer", back_populates="membership_plan")
