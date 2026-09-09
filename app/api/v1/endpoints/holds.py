from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.timezone import validate_slot_not_past
from app.models.booking import Booking
from app.models.slot import (
    ClientTier,
    HoldStatus,
    PaymentStatus,
    SlotMode,
    SlotStatus,
    TimeSlot,
    SlotHold,
)
from app.schemas.hold import (
    HoldExpirationCheckResponse,
    SlotHoldCreate,
    SlotHoldResponse,
)
from app.api.v1.endpoints.slots import to_participants_list

router = APIRouter()


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.post("", response_model=SlotHoldResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=SlotHoldResponse, status_code=status.HTTP_201_CREATED)
@router.post("/create", response_model=SlotHoldResponse, status_code=status.HTTP_201_CREATED)
async def create_hold(
    payload: SlotHoldCreate,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.holds))
        .where(TimeSlot.id == payload.slot_id)
        .with_for_update()
    )
    result = await db.execute(stmt)
    slot = result.scalar_one_or_none()

    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El slot especificado no existe",
        )

    validate_slot_not_past(slot)

    if slot.status == SlotStatus.BLOCKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="⚠️ Cancha ocupada: Ya existe una reserva en este horario.",
        )

    now_utc = datetime.now(timezone.utc)

    # Calcular cupos retenidos activos no expirados
    active_holds_spots = sum(
        hold.spots_held
        for hold in slot.holds
        if hold.status == HoldStatus.ACTIVE and ensure_utc(hold.expires_at) > now_utc
    )

    available_spots = slot.capacity - slot.booked_spots - active_holds_spots

    # Validaciones según modalidad
    if slot.mode == SlotMode.FULL_COURT:
        if payload.spots_held != slot.capacity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Para modalidad Cancha Completa (FULL_COURT) se deben reservar exactamente {slot.capacity} cupos.",
            )
        if available_spots < slot.capacity or slot.status == SlotStatus.FULLY_BOOKED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="⚠️ Cancha ocupada: Ya existe una reserva en este horario.",
            )
        amount_to_pay = slot.total_price
    else:  # SPLIT_MATCH
        if payload.spots_held > available_spots or available_spots <= 0 or slot.status == SlotStatus.FULLY_BOOKED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="⚠️ Cancha ocupada: Ya existe una reserva en este horario.",
            )
        price_per_spot = slot.total_price / Decimal(slot.capacity)
        amount_to_pay = (price_per_spot * Decimal(payload.spots_held)).quantize(Decimal("0.01"))

    # Procesamiento según ClientTier
    if payload.client_tier == ClientTier.MEMBER:
        # Bypass de pasarela: Membresía costo $0
        booking_ref = f"MEM-{uuid.uuid4().hex[:8].upper()}"
        new_booking = Booking(
            slot_id=slot.id,
            customer_phone=payload.customer_phone,
            customer_name=payload.customer_name,
            spots_booked=payload.spots_held,
            amount_paid=Decimal("0.00"),
            payment_reference=booking_ref,
            transaction_id=f"MEM-TX-{uuid.uuid4().hex[:8].upper()}",
            created_at=now_utc,
            client_tier=ClientTier.MEMBER,
            payment_status=PaymentStatus.MEMBER_EXEMPT,
        )
        db.add(new_booking)

        # Actualizar TimeSlot con participantes canónicos
        slot.booked_spots += payload.spots_held
        current_participants = to_participants_list(slot.players_names)
        current_participants.append({
            "spot_index": len(current_participants) + 1,
            "phone": payload.customer_phone,
            "display_name": payload.customer_name,
            "client_tier": ClientTier.MEMBER.value,
            "host_phone": None,
        })
        for g in range(2, payload.spots_held + 1):
            current_participants.append({
                "spot_index": len(current_participants) + 1,
                "phone": f"{payload.customer_phone}#GUEST{g}",
                "display_name": f"{payload.customer_name} (Invitado {g})",
                "client_tier": ClientTier.MEMBER.value,
                "host_phone": payload.customer_phone,
            })
        slot.players_names = current_participants

        if slot.booked_spots >= slot.capacity:
            slot.status = SlotStatus.FULLY_BOOKED
        else:
            slot.status = SlotStatus.PARTIALLY_BOOKED

        # Crear Hold representativo marcado como CONFIRMED
        new_hold = SlotHold(
            slot_id=slot.id,
            customer_phone=payload.customer_phone,
            customer_name=payload.customer_name,
            spots_held=payload.spots_held,
            amount_to_pay=Decimal("0.00"),
            expires_at=now_utc + timedelta(hours=24),
            status=HoldStatus.CONFIRMED,
            payment_reference=booking_ref,
            client_tier=ClientTier.MEMBER,
            payment_status=PaymentStatus.MEMBER_EXEMPT,
        )
        db.add(new_hold)
        await db.commit()
        await db.refresh(new_hold)
        return new_hold

    elif payload.client_tier == ClientTier.VIP_PAY_ON_SITE:
        # Reserva directa VIP: Cobro en recepción sin expiración de 15 minutos
        booking_ref = f"VIP-{uuid.uuid4().hex[:8].upper()}"
        new_booking = Booking(
            slot_id=slot.id,
            customer_phone=payload.customer_phone,
            customer_name=payload.customer_name,
            spots_booked=payload.spots_held,
            amount_paid=amount_to_pay,
            payment_reference=booking_ref,
            transaction_id=f"VIP-TX-{uuid.uuid4().hex[:8].upper()}",
            created_at=now_utc,
            client_tier=ClientTier.VIP_PAY_ON_SITE,
            payment_status=PaymentStatus.PENDING_ON_SITE,
        )
        db.add(new_booking)

        # Actualizar TimeSlot con participantes canónicos
        slot.booked_spots += payload.spots_held
        current_participants = to_participants_list(slot.players_names)
        current_participants.append({
            "spot_index": len(current_participants) + 1,
            "phone": payload.customer_phone,
            "display_name": payload.customer_name,
            "client_tier": ClientTier.VIP_PAY_ON_SITE.value,
            "host_phone": None,
        })
        for g in range(2, payload.spots_held + 1):
            current_participants.append({
                "spot_index": len(current_participants) + 1,
                "phone": f"{payload.customer_phone}#GUEST{g}",
                "display_name": f"{payload.customer_name} (Invitado {g})",
                "client_tier": ClientTier.VIP_PAY_ON_SITE.value,
                "host_phone": payload.customer_phone,
            })
        slot.players_names = current_participants

        if slot.booked_spots >= slot.capacity:
            slot.status = SlotStatus.FULLY_BOOKED
        else:
            slot.status = SlotStatus.PARTIALLY_BOOKED

        # Crear Hold representativo marcado como CONFIRMED con estado PENDING_ON_SITE
        new_hold = SlotHold(
            slot_id=slot.id,
            customer_phone=payload.customer_phone,
            customer_name=payload.customer_name,
            spots_held=payload.spots_held,
            amount_to_pay=amount_to_pay,
            expires_at=now_utc + timedelta(hours=24),
            status=HoldStatus.CONFIRMED,
            payment_reference=booking_ref,
            client_tier=ClientTier.VIP_PAY_ON_SITE,
            payment_status=PaymentStatus.PENDING_ON_SITE,
        )
        db.add(new_hold)
        await db.commit()
        await db.refresh(new_hold)
        return new_hold

    else:
        # Flujo estándar: Hold temporal con TTL de 15 minutos habitual
        expires_at = now_utc + timedelta(minutes=settings.HOLD_EXPIRATION_MINUTES)
        payment_reference = f"HOLD-{uuid.uuid4().hex[:10].upper()}"

        new_hold = SlotHold(
            slot_id=slot.id,
            customer_phone=payload.customer_phone,
            customer_name=payload.customer_name,
            spots_held=payload.spots_held,
            amount_to_pay=amount_to_pay,
            expires_at=expires_at,
            status=HoldStatus.ACTIVE,
            payment_reference=payment_reference,
            client_tier=ClientTier.STANDARD,
            payment_status=PaymentStatus.PAID,
        )
        db.add(new_hold)

        new_remaining = available_spots - payload.spots_held
        if new_remaining == 0:
            slot.status = SlotStatus.FULLY_BOOKED
        else:
            slot.status = SlotStatus.PARTIALLY_BOOKED

        await db.commit()
        await db.refresh(new_hold)
        return new_hold


@router.post("/check-expirations", response_model=HoldExpirationCheckResponse)
async def check_expirations(db: AsyncSession = Depends(get_db)):
    """Libera los holds activos cuya fecha de expiración haya pasado y restaura cupos."""
    now_utc = datetime.now(timezone.utc)

    stmt = (
        select(SlotHold)
        .options(selectinload(SlotHold.slot).selectinload(TimeSlot.holds))
        .where(SlotHold.status == HoldStatus.ACTIVE)
    )
    result = await db.execute(stmt)
    active_holds = result.scalars().all()

    expired_holds = [h for h in active_holds if ensure_utc(h.expires_at) <= now_utc]

    released_refs = []
    affected_slots = set()

    for hold in expired_holds:
        hold.status = HoldStatus.EXPIRED
        released_refs.append(hold.payment_reference)
        if hold.slot:
            affected_slots.add(hold.slot)

    # Reevaluar estados de los slots afectados
    for slot in affected_slots:
        if slot.status != SlotStatus.BLOCKED:
            active_spots = sum(
                h.spots_held
                for h in slot.holds
                if h.status == HoldStatus.ACTIVE and ensure_utc(h.expires_at) > now_utc and h.id not in [eh.id for eh in expired_holds]
            )
            total_taken = slot.booked_spots + active_spots
            if total_taken == 0:
                slot.status = SlotStatus.AVAILABLE
            elif total_taken < slot.capacity:
                slot.status = SlotStatus.PARTIALLY_BOOKED
            else:
                slot.status = SlotStatus.FULLY_BOOKED

    await db.commit()

    return HoldExpirationCheckResponse(
        expired_count=len(expired_holds),
        released_holds=released_refs,
        message=f"Se liberaron {len(expired_holds)} holds expirados satisfactoriamente.",
    )