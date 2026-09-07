from datetime import date, time
from decimal import Decimal
from typing import List, Optional, Union
import uuid
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.slot import SlotMode, SlotStatus


class CourtBase(BaseModel):
    name: str
    is_active: bool = True
    sport_type: str = "PADEL"
    max_capacity: int = 4
    court_number: Optional[int] = None


class CourtCreate(CourtBase):
    pass


class CourtResponse(CourtBase):
    id: Union[uuid.UUID, int, str]
    sport: Optional[str] = None

    @model_validator(mode="after")
    def populate_sport(self):
        if not self.sport and self.sport_type:
            self.sport = self.sport_type
        return self

    model_config = ConfigDict(from_attributes=True)


class TimeSlotBase(BaseModel):
    court_id: Union[uuid.UUID, int, str]
    date: date
    start_time: time
    end_time: time
    total_price: Decimal
    mode: SlotMode = SlotMode.FULL_COURT
    capacity: int = 4
    category: str = "4ta"
    sport_type: str = "PADEL"


class TimeSlotCreate(TimeSlotBase):
    pass


class SlotParticipant(BaseModel):
    spot_index: int
    phone: str
    display_name: str
    client_tier: str = "STANDARD"
    host_phone: Optional[str] = None
    is_first_visit: bool = False
    onboarding_status: str = "PENDING"
    customer_id: Optional[int] = None


class TimeSlotResponse(BaseModel):
    id: int
    court_id: Union[uuid.UUID, int, str]
    court_name: Optional[str] = None
    date: date
    start_time: time
    end_time: time
    total_price: Decimal
    price_per_spot: Decimal
    mode: SlotMode
    capacity: int
    booked_spots: int
    held_spots: int
    available_spots: int
    status: SlotStatus
    players_names: List[str] = Field(default_factory=list)
    participants: List[SlotParticipant] = Field(default_factory=list)
    category: str = "4ta"
    slot_type: str = "MATCH"
    instructor_name: Optional[str] = None
    is_promo: bool = False
    recommended_price: Optional[Decimal] = None
    pricing_tier: Optional[str] = None
    tournament_type: Optional[str] = None
    prize_pool: Optional[Decimal] = None
    tournament_name: Optional[str] = None
    sport_type: str = "PADEL"

    model_config = ConfigDict(from_attributes=True)


class ReserveOrBlockRequest(BaseModel):
    slot_type: str = "MATCH"  # FULL_COURT, SPLIT_MATCH, MEMBER, PAY_AT_VENUE, CLASS, MAINTENANCE, AMERICANO
    instructor_name: Optional[str] = None
    custom_price: Optional[Decimal] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    client_category: Optional[str] = None
    client_type: Optional[str] = None
    mode: Optional[SlotMode] = None
    notes: Optional[str] = None
    tournament_type: Optional[str] = None
    prize_pool: Optional[Decimal] = None


class CreateAmericanoRequest(BaseModel):
    name: Optional[str] = None
    tournament_name: Optional[str] = None
    modality: Optional[str] = None
    tournament_type: Optional[str] = "PAREJA_FIJA"
    date: date
    start_time: time
    duration_hours: Optional[float] = None
    duration_minutes: Optional[int] = None
    court_ids: List[str]  # 2 a 5 canchas
    price_per_player: Optional[Decimal] = None
    price_per_participant: Optional[Decimal] = None
    price_per_spot: Optional[Decimal] = None
    prize_pool: Optional[Decimal] = Decimal("300000.00")

    def get_name(self) -> str:
        return self.tournament_name or self.name or "Torneo Americano"

    def get_modality(self) -> str:
        return self.modality or self.tournament_type or "PAREJA_FIJA"

    def get_duration_minutes(self) -> int:
        if self.duration_minutes is not None:
            return self.duration_minutes
        if self.duration_hours is not None:
            return int(self.duration_hours * 60)
        return 120

    def get_price(self) -> Decimal:
        return self.price_per_player or self.price_per_spot or self.price_per_participant or Decimal("45000.00")


class ClubConfigRequest(BaseModel):
    valle_price: Optional[Decimal] = None
    base_valle: Optional[Decimal] = None
    pico_price: Optional[Decimal] = None
    base_pico: Optional[Decimal] = None
    min_safety_price: Optional[Decimal] = None
    safety_floor: Optional[Decimal] = None
    promo_discount_percent: Optional[int] = None
    cancellation_grace_minutes: Optional[int] = None
    confirmation_grace_minutes: Optional[int] = None
    whatsapp_group_id: Optional[str] = None
    broadcast_group_id: Optional[str] = None
    courts: Optional[List[dict]] = None
    padel_valle: Optional[Decimal] = None
    padel_pico: Optional[Decimal] = None
    padel_floor: Optional[Decimal] = None
    pickleball_valle: Optional[Decimal] = None
    pickleball_pico: Optional[Decimal] = None
    volleyball_base: Optional[Decimal] = None
    pilates_per_mat: Optional[Decimal] = None



class WhatsAppConvocatoriaRequest(BaseModel):
    raw_text: str
    sender_phone: Optional[str] = None


class WhatsAppConvocatoriaResponse(BaseModel):
    date: str
    start_time: str
    end_time: str
    category: str
    price_per_spot: Decimal
    players: List[str]
    participants: List[SlotParticipant] = Field(default_factory=list)
    spots_count: int
    free_spots: int
    is_closed: bool
    slot_id: Optional[int] = None
    whatsapp_reply: str


class DropPlayerRequest(BaseModel):
    slot_id: int
    sender_phone: str


class DropPlayerResponse(BaseModel):
    message: str
    slot_id: int
    freed_spot: int
    freed_player_name: str
    freed_phone: str
    available_spots: int
    status: SlotStatus