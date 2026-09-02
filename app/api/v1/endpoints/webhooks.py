from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.booking import Booking
from app.models.slot import HoldStatus, SlotStatus, TimeSlot, SlotHold
from app.schemas.booking import BookingResponse, PaymentMockWebhook
from app.api.v1.endpoints.slots import normalize_phone, to_participants_list

router = APIRouter()


@router.post("/payment-mock", response_model=BookingResponse, status_code=status.HTTP_200_OK)
async def mock_payment_webhook(
    payload: PaymentMockWebhook,
    db: AsyncSession = Depends(get_db),
):
    """Simula la confirmación de pago de pasarela (Bold / Wompi) y consolida la reserva."""
    stmt = (
        select(SlotHold)
        .options(selectinload(SlotHold.slot))
        .where(SlotHold.payment_reference == payload.payment_reference)
    )
    result = await db.execute(stmt)
    hold = result.scalar_one_or_none()

    if not hold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró ningún hold con la referencia {payload.payment_reference}",
        )

    if hold.status == HoldStatus.CONFIRMED:
        # Si ya fue confirmado, retornar la reserva existente
        existing_booking = await db.scalar(
            select(Booking).where(Booking.payment_reference == payload.payment_reference)
        )
        if existing_booking:
            return existing_booking
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La retención ya se encuentra confirmada.",
        )

    if hold.status == HoldStatus.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La retención temporal (hold) ha expirado y los cupos fueron liberados.",
        )

    if payload.status != "APPROVED":
        hold.status = HoldStatus.CANCELLED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pago no aprobado por la pasarela: {payload.status}",
        )

    # 1. Marcar hold como CONFIRMED
    hold.status = HoldStatus.CONFIRMED

    # 2. Registrar Booking
    tx_id = payload.transaction_id or f"TX-{uuid.uuid4().hex[:12].upper()}"
    booking = Booking(
        slot_id=hold.slot_id,
        customer_phone=hold.customer_phone,
        customer_name=hold.customer_name,
        spots_booked=hold.spots_held,
        amount_paid=hold.amount_to_pay,
        payment_reference=hold.payment_reference,
        transaction_id=tx_id,
        created_at=datetime.now(timezone.utc),
        client_tier=hold.client_tier,
        payment_status=hold.payment_status,
    )
    db.add(booking)

    # 3. Incrementar booked_spots y registrar jugador en el TimeSlot
    slot = hold.slot
    slot.booked_spots += hold.spots_held
    
    current_participants = to_participants_list(slot.players_names)
    existing_phones = [normalize_phone(p.get("phone")) for p in current_participants]
    
    if normalize_phone(hold.customer_phone) not in existing_phones:
        current_participants.append({
            "spot_index": len(current_participants) + 1,
            "phone": hold.customer_phone,
            "display_name": hold.customer_name,
            "client_tier": hold.client_tier.value,
            "host_phone": None,
        })
        for g in range(2, hold.spots_held + 1):
            current_participants.append({
                "spot_index": len(current_participants) + 1,
                "phone": f"{hold.customer_phone}#GUEST{g}",
                "display_name": f"{hold.customer_name} (Invitado {g})",
                "client_tier": hold.client_tier.value,
                "host_phone": hold.customer_phone,
            })
    slot.players_names = current_participants

    if slot.booked_spots >= slot.capacity:
        slot.status = SlotStatus.FULLY_BOOKED
    else:
        slot.status = SlotStatus.PARTIALLY_BOOKED

    await db.commit()
    await db.refresh(booking)

    return booking