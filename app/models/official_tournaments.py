import enum
import uuid
from datetime import date, datetime, time, timezone
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    Column,
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


class TournamentFormatType(str, enum.Enum):
    GROUPS_PLAYOFFS = "GROUPS_PLAYOFFS"
    DIRECT_ELIMINATION_BACKDRAW = "DIRECT_ELIMINATION_BACKDRAW"


class TournamentMatchRule(str, enum.Enum):
    BEST_OF_3 = "BEST_OF_3"
    BEST_OF_3_SHORT = "BEST_OF_3_SHORT"
    ONE_LONG_SET_8 = "ONE_LONG_SET_8"
    TIMED_MATCH = "TIMED_MATCH"


class TournamentTiebreakRule(str, enum.Enum):
    SETS_DIFF = "SETS_DIFF"
    GAMES_DIFF = "GAMES_DIFF"
    HEAD_TO_HEAD = "HEAD_TO_HEAD"


class OfficialTournamentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ENROLLMENT = "ENROLLMENT"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"


class OfficialTournament(Base):
    __tablename__ = "official_tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    club_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    sport_type: Mapped[str] = mapped_column(String(50), default="PADEL", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="4ta", nullable=False)
    format_type: Mapped[TournamentFormatType] = mapped_column(
        Enum(TournamentFormatType, name="tournament_format_enum", native_enum=False),
        default=TournamentFormatType.GROUPS_PLAYOFFS,
        nullable=False,
    )
    match_rule: Mapped[TournamentMatchRule] = mapped_column(
        Enum(TournamentMatchRule, name="tournament_match_rule_enum", native_enum=False),
        default=TournamentMatchRule.BEST_OF_3,
        nullable=False,
    )
    match_duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    tiebreak_rule: Mapped[TournamentTiebreakRule] = mapped_column(
        Enum(TournamentTiebreakRule, name="tournament_tiebreak_rule_enum", native_enum=False),
        default=TournamentTiebreakRule.SETS_DIFF,
        nullable=False,
    )
    status: Mapped[OfficialTournamentStatus] = mapped_column(
        Enum(OfficialTournamentStatus, name="official_tournament_status_enum", native_enum=False),
        default=OfficialTournamentStatus.DRAFT,
        nullable=False,
    )

    # Fechas y programación
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    assigned_court_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # Resultados y podio
    champion_team: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    runner_up_team: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    groups = relationship("TournamentGroup", back_populates="tournament", cascade="all, delete-orphan", lazy="selectin")
    matches = relationship("TournamentMatch", back_populates="tournament", cascade="all, delete-orphan", lazy="selectin")
    teams = relationship("TournamentTeam", back_populates="tournament", cascade="all, delete-orphan", lazy="selectin")


class TournamentTeam(Base):
    __tablename__ = "tournament_teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("official_tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_name: Mapped[str] = mapped_column(String(150), nullable=False)
    customer_id_1: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id_2: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tournament_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    tournament = relationship("OfficialTournament", back_populates="teams", lazy="selectin")
    player1 = relationship("Customer", foreign_keys=[customer_id_1], lazy="selectin")
    player2 = relationship("Customer", foreign_keys=[customer_id_2], lazy="selectin")


class TournamentGroup(Base):
    __tablename__ = "tournament_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("official_tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # "Grupo A", "Grupo B"

    # Estadísticas dinámicas acumuladas de equipos en el grupo:
    # Formato JSON: [{ "team_id": 1, "team_name": "...", "pj": 3, "pg": 2, "pp": 1, "sf": 4, "sc": 2, "gf": 24, "gc": 16, "pts": 6 }]
    standings_json: Mapped[List[dict]] = mapped_column(JSON, default=list, nullable=False)

    tournament = relationship("OfficialTournament", back_populates="groups", lazy="selectin")
    matches = relationship("TournamentMatch", back_populates="group", cascade="all, delete-orphan", lazy="selectin")


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("official_tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tournament_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stage: Mapped[str] = mapped_column(String(50), default="GROUP_STAGE", nullable=False)  # GROUP_STAGE, QUARTERS, SEMIS, FINAL, BACKDRAW
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    team1_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tournament_teams.id", ondelete="SET NULL"), nullable=True
    )
    team2_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tournament_teams.id", ondelete="SET NULL"), nullable=True
    )
    team1_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Ej: "1ro Grupo A"
    team2_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Ej: "2do Grupo B"

    court_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    slot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("time_slots.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_time: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # "18:00"

    # Marcador en vivo y por sets: ej: [{"set": 1, "t1": 6, "t2": 4}, {"set": 2, "t1": 6, "t2": 3}]
    scores_json: Mapped[List[dict]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="SCHEDULED", nullable=False)  # SCHEDULED, IN_PROGRESS, COMPLETED, WALK_OVER
    winner_team_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    tournament = relationship("OfficialTournament", back_populates="matches", lazy="selectin")
    group = relationship("TournamentGroup", back_populates="matches", lazy="selectin")
    team1 = relationship("TournamentTeam", foreign_keys=[team1_id], lazy="selectin")
    team2 = relationship("TournamentTeam", foreign_keys=[team2_id], lazy="selectin")
