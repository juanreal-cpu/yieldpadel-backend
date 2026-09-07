from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), default="4ta", nullable=False)
    client_type: Mapped[str] = mapped_column(String(50), default="Estándar", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

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

