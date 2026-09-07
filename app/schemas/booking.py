from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class PaymentMockWebhook(BaseModel):
    payment_reference: str
    status: str = Field(default="APPROVED")
    transaction_id: Optional[str] = None


class BookingResponse(BaseModel):
    id: int
    slot_id: int
    customer_phone: str
    customer_name: str
    spots_booked: int
    amount_paid: Decimal
    payment_reference: str
    transaction_id: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)