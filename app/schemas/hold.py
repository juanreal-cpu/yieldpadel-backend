from datetime import datetime
from decimal import Decimal
from typing import List
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.slot import ClientTier, HoldStatus, PaymentStatus


class SlotHoldCreate(BaseModel):
    slot_id: int
    customer_phone: str = Field(..., min_length=7, max_length=20)
    customer_name: str = Field(..., min_length=2, max_length=100)
    spots_held: int = Field(default=1, ge=1, le=4)
    client_tier: ClientTier = Field(default=ClientTier.STANDARD)

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data):
        if isinstance(data, dict):
            if "customer_phone" not in data:
                data["customer_phone"] = data.get("phone") or data.get("client_phone")
            if "customer_name" not in data:
                data["customer_name"] = data.get("player_name") or data.get("client_name")
            if "spots_held" not in data and "spots_count" in data:
                data["spots_held"] = data["spots_count"]
            if "client_tier" not in data and "payment_mode" in data:
                pm = str(data.get("payment_mode")).upper()
                if pm == "MEMBERSHIP":
                    data["client_tier"] = ClientTier.MEMBER
                elif pm == "COUNTER":
                    data["client_tier"] = ClientTier.VIP_PAY_ON_SITE
        return data


class SlotHoldResponse(BaseModel):
    id: int
    slot_id: int
    customer_phone: str
    customer_name: str
    spots_held: int
    amount_to_pay: Decimal
    expires_at: datetime
    status: HoldStatus
    payment_reference: str
    client_tier: ClientTier = ClientTier.STANDARD
    payment_status: PaymentStatus = PaymentStatus.PAID

    model_config = ConfigDict(from_attributes=True)


class HoldExpirationCheckResponse(BaseModel):
    expired_count: int
    released_holds: List[str]
    message: str