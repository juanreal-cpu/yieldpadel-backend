from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class RadarMatch(BaseModel):
    message_date: Optional[str] = None
    message_time: Optional[str] = None
    organizer: str
    time_slot: Optional[str] = None
    category: Optional[str] = None
    court: Optional[str] = None
    match_type: str = "ESTANDAR_4"
    price_per_player: int = 0
    spots_count: int = 0
    players: List[str] = Field(default_factory=list)
    is_closed: bool = False
    estimated_revenue: int = 0
    raw_snippet: Optional[str] = None


class RadarKPIs(BaseModel):
    total_matches_detected: int = 0
    closed_matches: int = 0
    open_matches: int = 0
    closure_rate_percent: float = 0.0
    estimated_total_revenue: int = 0
    unique_players_count: int = 0
    standard_matches: int = 0
    americano_matches: int = 0
    top_time_slots: Dict[str, int] = Field(default_factory=dict)


class RadarUploadResponse(BaseModel):
    status: str = "success"
    filename: str
    raw_file_path: str
    processed_csv_path: str
    kpis: RadarKPIs
    matches: List[RadarMatch] = Field(default_factory=list)


class ClubSummary(BaseModel):
    club_name: str
    total_matches: int = 0
    closed_matches: int = 0
    open_matches: int = 0
    closure_rate_percent: float = 0.0
    estimated_revenue: int = 0
    unique_players: int = 0
    standard_matches: int = 0
    americano_matches: int = 0
    top_time_slots: Dict[str, int] = Field(default_factory=dict)


class GlobalMarketMetrics(BaseModel):
    total_clubs: int = 0
    total_matches: int = 0
    closed_matches: int = 0
    open_matches: int = 0
    closure_rate_percent: float = 0.0
    total_estimated_revenue: int = 0
    total_unique_players: int = 0
    top_time_slots: Dict[str, int] = Field(default_factory=dict)


class RadarBatchConsolidatedResponse(BaseModel):
    status: str = "success"
    files_processed: List[str] = Field(default_factory=list)
    master_csv_path: str
    total_records: int = 0
    clubs_summary: Dict[str, ClubSummary] = Field(default_factory=dict)
    global_market_metrics: GlobalMarketMetrics


class CompetitorClubItem(BaseModel):
    id: int
    name: str
    city: str
    zone: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    courts_count: int = 4
    rating: Optional[float] = 4.5
    phone: Optional[str] = None
    website: Optional[str] = None
    price_valle: float
    price_pico: float
    current_price: float
    is_target_partner: bool = False
    diff_pct: float = 0.0
    diff_cop: float = 0.0


class RadarClubsResponse(BaseModel):
    status: str = "success"
    city: str
    franja: str
    target_price: float
    avg_competitor_price: float
    competitiveness_pct: float
    total_clubs: int
    total_national_clubs: int
    clubs: List[CompetitorClubItem] = Field(default_factory=list)