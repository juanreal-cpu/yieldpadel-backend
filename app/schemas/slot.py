from datetime import date, time
from decimal import Decimal
from typing import List, Optional, Union
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.models.slot import SlotMode, SlotStatus


class CourtBase(BaseModel):
    name: str
    is_active: bool = True


class CourtCreate(CourtBase):
    pass


class CourtResponse(CourtBase):
    id: Union[uuid.UUID, int, str]

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


class TimeSlotCreate(TimeSlotBase):
    pass


class SlotParticipant(BaseModel):
    spot_index: int
    phone: str
    display_name: str
    client_tier: str = "STANDARD"
    host_phone: Optional[str] = None


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

    model_config = ConfigDict(from_attributes=True)


class ReserveOrBlockRequest(BaseModel):
    slot_type: str = "MATCH"  # MATCH, CLASS, ACADEMY, MAINTENANCE
    instructor_name: Optional[str] = None
    custom_price: Optional[Decimal] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    mode: Optional[SlotMode] = None
    notes: Optional[str] = None


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