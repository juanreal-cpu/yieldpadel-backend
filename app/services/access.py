from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import cast, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.timezone import get_bogota_now, get_bogota_today
from app.models.access import ClubPresence
from app.models.booking import Booking
from app.models.customer import Customer
from app.models.product import Order
from app.models.slot import HoldStatus, PaymentStatus, SlotHold, TimeSlot

logger = logging.getLogger("yieldpadel.access")


async def calculate_player_debt(
    db: AsyncSession, presence: ClubPresence
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Calcula el saldo pendiente total del jugador buscando en:
    1. Consumos en barra/tienda (POS Orders con payment_status == 'PENDING').
    2. Turnos de canchas / slot holds sin pagar (payment_status == 'PENDING_ON_SITE').
    3. Reservas de canchas sin pagar (payment_status == 'PENDING_ON_SITE').
    """
    breakdown: List[Dict[str, Any]] = []
    seen_order_ids = set()
    seen_slot_ids = set()

    # 1. Consumos en Barra / Tienda (POS Orders PENDIENTES)
    order_conds = []
    if presence.player_id:
        order_conds.append(Order.customer_id == presence.player_id)
    if presence.player_name and presence.player_name.strip():
        order_conds.append(Order.customer_name.ilike(f"%{presence.player_name.strip()}%"))
    if presence.current_slot_id:
        order_conds.append(Order.slot_id == presence.current_slot_id)

    if order_conds:
        stmt_orders = select(Order).where(
            or_(*order_conds),
            Order.payment_status == "PENDING",
        )
        res_orders = await db.execute(stmt_orders)
        orders = res_orders.scalars().all()
        for ord in orders:
            if ord.id in seen_order_ids:
                continue
            seen_order_ids.add(ord.id)
            breakdown.append({
                "type": "POS_BAR",
                "reference_id": ord.id,
                "description": f"Consumo Barra/Tienda #{ord.id} - {ord.customer_name}",
                "amount": float(ord.total_amount),
            })

    # 2. Turnos de Cancha en Holds (SlotHold PENDIENTES)
    hold_conds = []
    if presence.phone and presence.phone.strip():
        hold_conds.append(SlotHold.customer_phone == presence.phone.strip())
    if presence.player_name and presence.player_name.strip():
        hold_conds.append(SlotHold.customer_name.ilike(f"%{presence.player_name.strip()}%"))
    if presence.current_slot_id:
        hold_conds.append(SlotHold.slot_id == presence.current_slot_id)

    if hold_conds:
        stmt_holds = select(SlotHold).where(
            or_(*hold_conds),
            cast(SlotHold.status, String).in_(["CONFIRMED", "ACTIVE"]),
            cast(SlotHold.payment_status, String).in_([
                "PENDING_ON_SITE",
                "PENDING",
            ]),
        )
        res_holds = await db.execute(stmt_holds)
        holds = res_holds.scalars().all()
        for h in holds:
            seen_slot_ids.add(h.slot_id)
            breakdown.append({
                "type": "COURT_HOLD",
                "reference_id": h.id,
                "slot_id": h.slot_id,
                "description": f"Turno Cancha #{h.slot_id} (Pendiente en Sede)",
                "amount": float(h.amount_to_pay),
            })

    # 3. Reservas de Cancha (Yield Booking PENDIENTES)
    booking_conds = []
    if presence.phone and presence.phone.strip():
        booking_conds.append(Booking.customer_phone == presence.phone.strip())
    if presence.player_name and presence.player_name.strip():
        booking_conds.append(Booking.customer_name.ilike(f"%{presence.player_name.strip()}%"))

    if booking_conds:
        stmt_bookings = select(Booking).where(
            or_(*booking_conds),
            cast(Booking.payment_status, String).in_([
                "PENDING_ON_SITE",
                "PENDING",
            ]),
        )
        res_bookings = await db.execute(stmt_bookings)
        bookings = res_bookings.scalars().all()
        for b in bookings:
            if b.slot_id in seen_slot_ids:
                continue
            seen_slot_ids.add(b.slot_id)
            breakdown.append({
                "type": "COURT_BOOKING",
                "reference_id": b.id,
                "slot_id": b.slot_id,
                "description": f"Reserva Cancha #{b.slot_id} (Pendiente en Sede)",
                "amount": float(b.amount_paid),
            })

    total_pending = round(sum(item["amount"] for item in breakdown), 2)
    return total_pending, breakdown


async def perform_check_in(
    db: AsyncSession,
    player_id: Optional[int] = None,
    player_name: Optional[str] = None,
    phone: Optional[str] = None,
    current_slot_id: Optional[int] = None,
    membership_tier: Optional[str] = None,
) -> ClubPresence:
    """Registra la entrada (Check-in) de un jugador en el club."""
    # Resolver desde Customer si player_id está presente
    if player_id:
        cust_stmt = select(Customer).where(Customer.id == player_id)
        cust_res = await db.execute(cust_stmt)
        customer = cust_res.scalar_one_or_none()
        if customer:
            player_name = player_name or customer.name
            phone = phone or customer.phone
            membership_tier = membership_tier or customer.membership_tier or "ESTANDAR"

    if not player_id and phone:
        # Intentar enlazar con Customer existente por teléfono
        cust_stmt = select(Customer).where(Customer.phone == phone)
        cust_res = await db.execute(cust_stmt)
        customer = cust_res.scalar_one_or_none()
        if customer:
            player_id = customer.id
            player_name = player_name or customer.name
            membership_tier = membership_tier or customer.membership_tier or "ESTANDAR"

    player_name = player_name or "Visitante Mostrador"
    phone = phone or ""
    membership_tier = membership_tier or "ESTANDAR"

    # Si no se pasó current_slot_id, buscar si tiene turno hoy en rango actual
    if not current_slot_id and phone:
        today = get_bogota_today()
        slot_stmt = (
            select(SlotHold.slot_id)
            .where(
                SlotHold.customer_phone == phone,
                SlotHold.status.in_([HoldStatus.CONFIRMED, HoldStatus.ACTIVE]),
            )
            .limit(1)
        )
        slot_res = await db.execute(slot_stmt)
        matched_slot_id = slot_res.scalar_one_or_none()
        if matched_slot_id:
            current_slot_id = matched_slot_id

    # Verificar si el jugador ya está marcado adentro
    existing_stmt = select(ClubPresence).where(
        ClubPresence.is_inside == True,
        or_(
            ClubPresence.player_id == player_id if player_id else False,
            ClubPresence.phone == phone if phone else False,
            ClubPresence.player_name.ilike(player_name),
        ),
    )
    existing_res = await db.execute(existing_stmt)
    existing = existing_res.scalar_one_or_none()

    now_b = get_bogota_now()

    if existing:
        # Reactualizar registro activo
        existing.check_in_time = now_b
        existing.check_out_time = None
        existing.is_inside = True
        if current_slot_id:
            existing.current_slot_id = current_slot_id
        if membership_tier:
            existing.membership_tier = membership_tier
        await db.commit()
        await db.refresh(existing)
        return existing

    presence = ClubPresence(
        player_id=player_id,
        player_name=player_name,
        phone=phone,
        check_in_time=now_b,
        check_out_time=None,
        is_inside=True,
        membership_tier=membership_tier,
        current_slot_id=current_slot_id,
    )
    db.add(presence)
    await db.commit()
    await db.refresh(presence)
    return presence


async def perform_check_out(
    db: AsyncSession,
    presence_id: Optional[int] = None,
    player_id: Optional[int] = None,
    force_clear: bool = False,
) -> Dict[str, Any]:
    """
    Evalúa la salida del jugador.
    Si tiene deuda acumulada (pending_balance > 0) y no es force_clear:
        SALIDA BLOQUEADA. is_inside permanece en True.
    Si pending_balance == 0 (o force_clear=True):
        SALIDA AUTORIZADA. is_inside = False, check_out_time = now().
    """
    stmt = select(ClubPresence).where(ClubPresence.is_inside == True)
    if presence_id:
        stmt = stmt.where(ClubPresence.id == presence_id)
    elif player_id:
        stmt = stmt.where(ClubPresence.player_id == player_id)
    else:
        raise HTTPException(status_code=400, detail="Debe especificar presence_id o player_id")

    res = await db.execute(stmt)
    presence = res.scalar_one_or_none()

    if not presence:
        raise HTTPException(
            status_code=404,
            detail="No se encontró registro de presencia activo para este usuario dentro del club.",
        )

    # Calcular saldo pendiente
    total_pending, breakdown = await calculate_player_debt(db, presence)

    if total_pending > 0 and not force_clear:
        # Bloqueo financiero de salida
        formatted_amount = f"${int(total_pending):,} COP".replace(",", ".")
        return {
            "status": "BLOCKED",
            "authorized": False,
            "message": f"SALIDA DENEGADA: El usuario tiene pagos pendientes por {formatted_amount}. Liquide su cuenta en counter para autorizar la salida.",
            "pending_balance": total_pending,
            "breakdown": breakdown,
            "presence_id": presence.id,
            "player_name": presence.player_name,
            "phone": presence.phone,
        }

    # Salida autorizada
    now_b = get_bogota_now()
    presence.is_inside = False
    presence.check_out_time = now_b
    await db.commit()
    await db.refresh(presence)

    return {
        "status": "AUTHORIZED",
        "authorized": True,
        "message": "Salida autorizada con éxito. ¡Hasta pronto!",
        "pending_balance": 0.0,
        "breakdown": [],
        "presence_id": presence.id,
        "player_name": presence.player_name,
        "phone": presence.phone,
        "check_out_time": presence.check_out_time.isoformat() if presence.check_out_time else None,
    }


async def clear_debt_in_counter(
    db: AsyncSession, presence_id: int
) -> Dict[str, Any]:
    """
    Liquida en counter las órdenes de POS y turnos pendientes asociados a la presencia.
    """
    stmt = select(ClubPresence).where(ClubPresence.id == presence_id)
    res = await db.execute(stmt)
    presence = res.scalar_one_or_none()
    if not presence:
        raise HTTPException(status_code=404, detail="Presencia no encontrada")

    # Marcar órdenes de barra asociadas como PAID
    order_conds = []
    if presence.player_id:
        order_conds.append(Order.customer_id == presence.player_id)
    if presence.player_name:
        order_conds.append(Order.customer_name.ilike(f"%{presence.player_name.strip()}%"))
    if presence.current_slot_id:
        order_conds.append(Order.slot_id == presence.current_slot_id)

    if order_conds:
        stmt_orders = select(Order).where(
            or_(*order_conds),
            Order.payment_status == "PENDING",
        )
        res_orders = await db.execute(stmt_orders)
        for ord in res_orders.scalars().all():
            ord.payment_status = "PAID"

    # Marcar holds como PAID
    hold_conds = []
    if presence.phone:
        hold_conds.append(SlotHold.customer_phone == presence.phone.strip())
    if presence.player_name:
        hold_conds.append(SlotHold.customer_name.ilike(f"%{presence.player_name.strip()}%"))
    if presence.current_slot_id:
        hold_conds.append(SlotHold.slot_id == presence.current_slot_id)

    if hold_conds:
        stmt_holds = select(SlotHold).where(
            or_(*hold_conds),
            cast(SlotHold.status, String).in_(["CONFIRMED", "ACTIVE"]),
            cast(SlotHold.payment_status, String).in_([
                "PENDING_ON_SITE",
                "PENDING",
            ]),
        )
        res_holds = await db.execute(stmt_holds)
        for h in res_holds.scalars().all():
            h.payment_status = PaymentStatus.PAID

    await db.commit()
    return {"success": True, "message": "Deudas liquidadas exitosamente en counter"}


async def ensure_seed_presences(db: AsyncSession):
    """Puebla presencias iniciales para demostración si la tabla está vacía."""
    stmt = select(ClubPresence).limit(1)
    res = await db.execute(stmt)
    if res.first() is not None:
        return

    now_b = get_bogota_now()

    # Presencia 1: Deudor con orden de barra pendiente
    p1 = ClubPresence(
        player_name="Mateo Restrepo",
        phone="3104567890",
        check_in_time=now_b - timedelta(minutes=85),
        is_inside=True,
        membership_tier="ESTANDAR",
        current_slot_id=None,
    )
    db.add(p1)

    # Presencia 2: Jugador en cancha con horario Chingotto excedido si es tarde
    p2 = ClubPresence(
        player_name="Federico Chingotto",
        phone="3129876543",
        check_in_time=now_b - timedelta(minutes=60),
        is_inside=True,
        membership_tier="CHINGOTTO",
        current_slot_id=1,
    )
    db.add(p2)

    # Presencia 3: Jugador al día
    p3 = ClubPresence(
        player_name="Camila Morales",
        phone="3001234567",
        check_in_time=now_b - timedelta(minutes=30),
        is_inside=True,
        membership_tier="TAPIA",
        current_slot_id=2,
    )
    db.add(p3)

    # Presencia 4: Sobretiempo sin cancha
    p4 = ClubPresence(
        player_name="Santiago Gómez",
        phone="3159988776",
        check_in_time=now_b - timedelta(minutes=55),
        is_inside=True,
        membership_tier="LEBRON",
        current_slot_id=None,
    )
    db.add(p4)

    await db.commit()

    # Crear una orden pendiente para Mateo Restrepo para activar el deudor
    order1 = Order(
        customer_name="Mateo Restrepo",
        total_amount=Decimal("35000.00"),
        payment_status="PENDING",
    )
    db.add(order1)
    await db.commit()


async def get_active_now_data(db: AsyncSession) -> Dict[str, Any]:
    """Retorna listado en tiempo real de personas en el club, alertas y métricas KPI."""
    await ensure_seed_presences(db)

    stmt = (
        select(ClubPresence)
        .options(selectinload(ClubPresence.slot).selectinload(TimeSlot.court))
        .where(ClubPresence.is_inside == True)
        .order_by(ClubPresence.check_in_time.desc())
    )
    res = await db.execute(stmt)
    presences = res.scalars().all()

    now_b = get_bogota_now()
    active_list: List[Dict[str, Any]] = []

    for p in presences:
        stay_seconds = max(0, int((now_b - p.check_in_time).total_seconds()))
        stay_minutes = stay_seconds // 60

        total_pending, breakdown = await calculate_player_debt(db, p)

        # Reglas de Alertas Operativas
        alerts: List[Dict[str, Any]] = []
        tier = (p.membership_tier or "").upper()

        # 1. MEMBERSHIP_TIME_EXCEEDED (Chingotto > 15:00 o Lebrón > 18:00 jugando)
        if tier == "CHINGOTTO" and (now_b.hour > 15 or (now_b.hour == 15 and now_b.minute > 0)):
            if p.current_slot_id is not None:
                alerts.append({
                    "code": "MEMBERSHIP_TIME_EXCEEDED",
                    "severity": "WARNING",
                    "badge": "⚠️ Exceso Horario Chingotto (Límite 15:00)",
                    "message": "Jugador Chingotto en cancha después del límite de las 15:00.",
                })
        elif tier == "LEBRON" and (now_b.hour > 18 or (now_b.hour == 18 and now_b.minute > 0)):
            if p.current_slot_id is not None:
                alerts.append({
                    "code": "MEMBERSHIP_TIME_EXCEEDED",
                    "severity": "WARNING",
                    "badge": "⚠️ Exceso Horario Lebrón (Límite 18:00)",
                    "message": "Jugador Lebrón en cancha después del límite de las 18:00.",
                })

        # 2. OVERSTAY_NO_COURT (>45 min en el club sin reserva de cancha)
        if p.current_slot_id is None and stay_minutes > 45:
            alerts.append({
                "code": "OVERSTAY_NO_COURT",
                "severity": "INFO",
                "badge": f"⏱️ >45 min sin cancha ({stay_minutes} min)",
                "message": f"Lleva {stay_minutes} minutos en las instalaciones sin reserva activa.",
            })

        # Info de Cancha
        court_label = "Sin Cancha (Solo Club)"
        if p.slot:
            court_name = p.slot.court.name if p.slot.court else f"Pista #{p.slot.court_id}"
            start_fmt = p.slot.start_time.strftime("%H:%M") if hasattr(p.slot.start_time, "strftime") else str(p.slot.start_time)
            end_fmt = p.slot.end_time.strftime("%H:%M") if hasattr(p.slot.end_time, "strftime") else str(p.slot.end_time)
            court_label = f"{court_name} ({start_fmt} - {end_fmt})"
        elif p.current_slot_id:
            court_label = f"Pista Slot #{p.current_slot_id}"

        exit_status = "BLOCKED" if total_pending > 0 else "AUTHORIZED"

        active_list.append({
            "id": p.id,
            "player_id": p.player_id,
            "player_name": p.player_name,
            "phone": p.phone,
            "membership_tier": p.membership_tier,
            "check_in_time": p.check_in_time.isoformat(),
            "check_in_time_formatted": p.check_in_time.strftime("%I:%M %p"),
            "stay_minutes": stay_minutes,
            "stay_formatted": f"{stay_minutes} min",
            "current_slot_id": p.current_slot_id,
            "court_label": court_label,
            "pending_balance": total_pending,
            "pending_balance_formatted": f"${int(total_pending):,} COP".replace(",", "."),
            "breakdown": breakdown,
            "exit_status": exit_status,
            "alerts": alerts,
        })

    # KPIs
    people_inside_count = len(active_list)
    avg_stay = round(sum(p["stay_minutes"] for p in active_list) / max(1, people_inside_count)) if people_inside_count > 0 else 0
    blocked_debtors = sum(1 for p in active_list if p["pending_balance"] > 0)

    return {
        "kpis": {
            "people_inside_count": people_inside_count,
            "avg_stay_minutes": avg_stay,
            "avg_stay_formatted": f"{avg_stay} min",
            "blocked_debtors_count": blocked_debtors,
        },
        "presences": active_list,
    }
