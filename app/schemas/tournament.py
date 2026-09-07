from datetime import date as dt_date, time as dt_time
from decimal import Decimal
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class RecordWinnersRequest(BaseModel):
    slot_id: Optional[int] = None
    slot_ids: Optional[List[int]] = None
    tournament_id: Optional[str] = None
    tournament_name: Optional[str] = None
    date: Optional[Union[dt_date, str]] = None
    start_time: Optional[Union[dt_time, str]] = None
    winner_names: List[str] = Field(default_factory=list, description="Nombres de los campeones (+100 pts)")
    winner_phones: Optional[List[str]] = None
    runner_up_names: Optional[List[str]] = Field(default_factory=list, description="Nombres de los subcampeones (+50 pts)")
    runner_up_phones: Optional[List[str]] = None


class TournamentCourtActionRequest(BaseModel):
    tournament_name: str
    date: Union[dt_date, str]
    start_time: Union[dt_time, str]
    court_id: str


class CancelTournamentRequest(BaseModel):
    tournament_name: str
    date: Union[dt_date, str]
    start_time: Union[dt_time, str]


class TournamentCardItem(BaseModel):
    id: str  # Unique composite identifier
    tournament_name: str
    date: dt_date
    start_time: dt_time
    end_time: dt_time
    sport_type: str = "PADEL"
    modality: str = "PAREJA_FIJA"
    courts_count: int = 2
    court_names: List[str] = Field(default_factory=list)
    court_ids: List[str] = Field(default_factory=list)
    slot_ids: List[int] = Field(default_factory=list)
    booked_spots: int = 0
    total_capacity: int = 8
    price_per_player: float = 45000.0
    prize_pool: float = 250000.0
    is_finished: bool = False
    winners_names: Optional[str] = None
    runner_up_names: Optional[str] = None
    is_active_or_upcoming: bool = True


class TournamentListResponse(BaseModel):
    status: str = "success"
    sport: str = "ALL"
    upcoming: List[TournamentCardItem] = Field(default_factory=list)
    past: List[TournamentCardItem] = Field(default_factory=list)
    total_count: int = 0
