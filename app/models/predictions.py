import enum
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PredictedWinner(str, enum.Enum):
    TEAM_A = "TEAM_A"
    TEAM_B = "TEAM_B"


class PredictionStatus(str, enum.Enum):
    PENDING = "PENDING"
    HIT = "HIT"
    MISSED = "MISSED"


class MatchPrediction(Base):
    __tablename__ = "match_predictions"
    __table_args__ = (
        UniqueConstraint("slot_id", "customer_id", name="uq_match_prediction_slot_customer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("time_slots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    predicted_winner: Mapped[PredictedWinner] = mapped_column(
        Enum(PredictedWinner, name="predicted_winner_enum", native_enum=False),
        nullable=False,
    )
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[PredictionStatus] = mapped_column(
        Enum(PredictionStatus, name="prediction_status_enum", native_enum=False),
        default=PredictionStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    slot = relationship("TimeSlot", backref="predictions", lazy="selectin")
    customer = relationship("Customer", backref="predictions", lazy="selectin")


class PredictionLeaderboard(Base):
    __tablename__ = "prediction_leaderboards"
    __table_args__ = (
        UniqueConstraint("club_id", "year", "month", "customer_id", name="uq_prediction_leaderboard_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    monthly_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hits_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_predictions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    customer = relationship("Customer", backref="monthly_leaderboards", lazy="selectin")


class SlotChallengeVote(Base):
    __tablename__ = "slot_challenges_votes"
    __table_args__ = (
        UniqueConstraint("slot_id", "player_phone", name="uq_slot_challenge_vote_slot_phone"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("time_slots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_phone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    vote: Mapped[str] = mapped_column(String(20), nullable=False)  # 'POINTS', 'GATORADE', 'FRIENDLY'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    slot = relationship("TimeSlot", backref="challenge_votes", lazy="selectin")
