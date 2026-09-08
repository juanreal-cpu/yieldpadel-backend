from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status, Request
from app.services.audit import log_activity
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.timezone import get_bogota_now, get_bogota_today, validate_slot_not_past
from app.services import calculate_recommended_price, get_club_config, update_club_config
from app.services.whatsapp import detect_sport_from_text, get_sport_emoji, get_sport_default_capacity, format_whatsapp_reply
import uuid
from app.models.court import Court
from app.models.customer import Customer
from app.models.booking import Booking
from app.models.slot import HoldStatus, SlotMode, SlotStatus, TimeSlot, SlotHold, ClientTier, PaymentStatus
from app.schemas.hold import SlotHoldCreate, SlotHoldResponse
from app.schemas.slot import (
    CourtResponse,
    DropPlayerRequest,
    DropPlayerResponse,
    SlotParticipant,
    TimeSlotResponse,
    WhatsAppConvocatoriaRequest,
    WhatsAppConvocatoriaResponse,
    ReserveOrBlockRequest,
    CreateAmericanoRequest,
    ClubConfigRequest,
    WeeklyTemplateSeedRequest,
)

router = APIRouter()



def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_phone(phone: Optional[str]) -> str:
    """Normaliza un teléfono para comparaciones canónicas."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", str(phone))
    if digits.startswith("57") and len(digits) == 12:
        return "+" + digits
    elif len(digits) == 10:
        return "+57" + digits
    elif str(phone).startswith("+"):
        return "+" + digits
    return digits


def to_participants_list(raw_players: any) -> List[dict]:
    """Normaliza participantes a una lista de diccionarios canónicos."""
    if not raw_players:
        return []
    result = []
    for i, item in enumerate(raw_players, start=1):
        if isinstance(item, dict):
            p = {
                "spot_index": item.get("spot_index", i),
                "phone": item.get("phone", f"+57-unknown-{i}"),
                "display_name": item.get("display_name", f"Jugador {i}"),
                "client_tier": item.get("client_tier", "STANDARD"),
                "host_phone": item.get("host_phone"),
                "is_first_visit": bool(item.get("is_first_visit", False)),
                "onboarding_status": item.get("onboarding_status", "PENDING"),
                "customer_id": item.get("customer_id"),
            }
        else:
            name = str(item).strip()
            p = {
                "spot_index": i,
                "phone": f"+57-WA-{name.lower().replace(' ', '')}",
                "display_name": name,
                "client_tier": "STANDARD",
                "host_phone": None,
                "is_first_visit": False,
                "onboarding_status": "PENDING",
                "customer_id": None,
            }
        result.append(p)
    return result


async def get_or_create_booking_customer(
    db: AsyncSession,
    name: Optional[str],
    phone: Optional[str],
    category: Optional[str] = "4ta",
    client_type: Optional[str] = "Estándar",
) -> dict:
    """Busca o registra un cliente evaluando automáticamente si es su primera visita."""
    norm_phone = normalize_phone(phone)
    if not norm_phone or norm_phone.startswith("+57-WA-") or norm_phone.startswith("+57-unknown-") or norm_phone.startswith("+57-MANT"):
        if name and not name.startswith("Mantenimiento"):
            stmt = select(Customer).where(Customer.name.ilike(f"%{name.strip()}%")).limit(1)
            res = await db.execute(stmt)
            cust = res.scalars().first()
            if cust:
                is_first = bool(cust.is_first_visit or cust.total_bookings_completed == 0)
                return {
                    "is_first_visit": is_first,
                    "onboarding_status": cust.onboarding_status or "PENDING",
                    "customer_id": cust.id,
                }
        return {
            "is_first_visit": False,
            "onboarding_status": "PENDING",
            "customer_id": None,
        }

    stmt = select(Customer).where(Customer.phone == norm_phone)
    res = await db.execute(stmt)
    cust = res.scalars().first()
    if cust:
        is_first = bool(cust.is_first_visit or cust.total_bookings_completed == 0)
        return {
            "is_first_visit": is_first,
            "onboarding_status": cust.onboarding_status or "PENDING",
            "customer_id": cust.id,
        }

    # Nuevo cliente registrado automáticamente en su primera visita
    new_cust = Customer(
        name=name or "Nuevo Cliente",
        phone=norm_phone,
        category=category or "4ta",
        client_type=client_type or "Estándar",
        total_bookings_completed=0,
        is_first_visit=True,
        onboarding_status="PENDING",
        notes="Cliente nuevo registrado automáticamente (1ra Visita)",
        ranking_points=0,
        titles_count=0,
        category_wins=0,
        consecutive_wins=0,
    )
    db.add(new_cust)
    await db.flush()
    return {
        "is_first_visit": True,
        "onboarding_status": "PENDING",
        "customer_id": new_cust.id,
    }


def compute_slot_response(slot: TimeSlot, now_utc: datetime) -> TimeSlotResponse:
    # Active unexpired holds
    held_spots = sum(
        hold.spots_held
        for hold in slot.holds
        if hold.status == HoldStatus.ACTIVE and ensure_utc(hold.expires_at) > now_utc
    )
    available = max(0, slot.capacity - slot.booked_spots - held_spots)

    # Dynamic status
    if slot.status == SlotStatus.BLOCKED:
        dyn_status = SlotStatus.BLOCKED
    elif available == 0:
        dyn_status = SlotStatus.FULLY_BOOKED
    elif slot.booked_spots > 0 or held_spots > 0:
        dyn_status = SlotStatus.PARTIALLY_BOOKED
    else:
        dyn_status = SlotStatus.AVAILABLE

    participants_raw = to_participants_list(slot.players_names)
    participants_objs = [SlotParticipant(**p) for p in participants_raw]
    display_names = [p.display_name for p in participants_objs]

    sport = getattr(slot, "sport_type", None) or (slot.court.sport_type if getattr(slot, "court", None) and getattr(slot.court, "sport_type", None) else "PADEL")

    if sport == "VOLLEYBALL":
        total_court_price = slot.total_price if slot.total_price > 0 else Decimal("120000.00")
        count_p = len(participants_objs)
        if count_p > 0:
            price_per_spot = (total_court_price / Decimal(count_p)).quantize(Decimal("0.01"))
        else:
            price_per_spot = (total_court_price / Decimal(slot.capacity or 12)).quantize(Decimal("0.01"))
    else:
        price_per_spot = (slot.total_price / Decimal(slot.capacity or 4)).quantize(Decimal("0.01"))

    yield_info = calculate_recommended_price(slot)

    return TimeSlotResponse(
        id=slot.id,
        court_id=slot.court_id,
        court_name=slot.court.name if slot.court else None,
        date=slot.date,
        start_time=slot.start_time,
        end_time=slot.end_time,
        total_price=slot.total_price,
        price_per_spot=price_per_spot,
        mode=slot.mode,
        capacity=slot.capacity,
        booked_spots=slot.booked_spots,
        held_spots=held_spots,
        available_spots=available,
        status=dyn_status,
        players_names=display_names,
        participants=participants_objs,
        category=slot.category or "4ta",
        slot_type=getattr(slot, "slot_type", "MATCH") or "MATCH",
        instructor_name=getattr(slot, "instructor_name", None),
        is_promo=bool(yield_info.get("is_promo", False) or getattr(slot, "is_promo", False)),
        recommended_price=yield_info.get("recommended_price"),
        pricing_tier=yield_info.get("pricing_tier"),
        tournament_type=getattr(slot, "tournament_type", None),
        prize_pool=getattr(slot, "prize_pool", None),
        tournament_name=getattr(slot, "tournament_name", None),
        sport_type=sport,
    )


@router.get("/", response_model=List[TimeSlotResponse])
async def list_slots(
    slot_date: Optional[date] = Query(None, alias="date", description="Filtrar por fecha"),
    mode: Optional[SlotMode] = Query(None, description="Filtrar por modo FULL_COURT o SPLIT_MATCH"),
    sport: Optional[str] = Query(None, description="Filtrar por deporte (PADEL, PICKLEBALL, VOLLEYBALL, PILATES, CONSOLE)"),
    only_available: bool = Query(False, description="Mostrar únicamente slots con cupos disponibles"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TimeSlot).options(
        selectinload(TimeSlot.court),
        selectinload(TimeSlot.holds),
    ).order_by(TimeSlot.date, TimeSlot.start_time)

    if slot_date:
        stmt = stmt.where(TimeSlot.date == slot_date)
    if mode:
        stmt = stmt.where(TimeSlot.mode == mode)
    if sport:
        s_upper = sport.upper()
        if s_upper == "PADEL":
            stmt = stmt.where((TimeSlot.sport_type == "PADEL") | (TimeSlot.sport_type.is_(None)))
        else:
            stmt = stmt.where(TimeSlot.sport_type == s_upper)

    result = await db.execute(stmt)
    slots = result.scalars().all()

    now_utc = datetime.now(timezone.utc)
    response_list: List[TimeSlotResponse] = []

    for slot in slots:
        slot_resp = compute_slot_response(slot, now_utc)
        if only_available:
            if slot_resp.available_spots > 0 and slot_resp.status != SlotStatus.BLOCKED:
                response_list.append(slot_resp)
        else:
            response_list.append(slot_resp)

    return response_list


async def ensure_five_courts(db: AsyncSession) -> List[Court]:
    """Garantiza la existencia y numeración de todas las canchas multideporte del club (Pádel, Pickleball, Vóley y Pilates) sin duplicados."""
    import uuid
    res = await db.execute(select(Court))
    all_courts = list(res.scalars().all())

    # Deduplicar en BD: Agrupar por (nombre limpio, deporte)
    seen_db_keys = set()
    active_courts = []
    changed = False

    for c in all_courts:
        st = (getattr(c, "sport_type", None) or getattr(c, "sport", "PADEL") or "PADEL").upper()
        name_clean = (c.name or "").strip().lower()
        key = (name_clean, st)

        if key in seen_db_keys:
            # Pista duplicada en base de datos: desactivarla
            if c.is_active:
                c.is_active = False
                changed = True
        else:
            seen_db_keys.add(key)
            if c.is_active:
                active_courts.append(c)

    court_map = {c.name.strip().lower(): c for c in active_courts}
    num_map = {c.court_number: c for c in active_courts if getattr(c, "court_number", None) is not None}

    sample_club_id = None
    for c in active_courts:
        if getattr(c, "club_id", None):
            sample_club_id = c.club_id
            break
    if not sample_club_id:
        sample_club_id = uuid.uuid4()

    court_definitions = [
        (1, "Cancha Central 1", "PADEL", 4),
        (2, "Cancha 2", "PADEL", 4),
        (3, "Cancha 3", "PADEL", 4),
        (4, "Cancha 4", "PADEL", 4),
        (5, "Cancha 5", "PADEL", 4),
        (6, "Pista Pickleball 1", "PICKLEBALL", 4),
        (7, "Pista Pickleball 2", "PICKLEBALL", 4),
        (8, "Cancha Arena Vóley", "VOLLEYBALL", 12),
        (9, "Estudio Pilates", "PILATES", 10),
        (10, "Sala Gaming / Consola", "CONSOLE", 4),
    ]

    for num, name, s_type, max_cap in court_definitions:
        existing = num_map.get(num) or court_map.get(name.strip().lower())
        # Si no coincide exactamente pero ya existe pista de Pádel con número o nombre similar
        if not existing:
            for c in active_courts:
                c_sport = (getattr(c, "sport_type", None) or getattr(c, "sport", "PADEL") or "PADEL").upper()
                if c_sport == s_type and (getattr(c, "court_number", None) == num or c.name.strip().lower() == name.strip().lower()):
                    existing = c
                    break

        if existing:
            if existing.name != name:
                existing.name = name
                changed = True
            if getattr(existing, "court_number", None) != num:
                existing.court_number = num
                changed = True
            if getattr(existing, "sport_type", None) != s_type:
                existing.sport_type = s_type
                changed = True
            if getattr(existing, "max_capacity", None) != max_cap:
                existing.max_capacity = max_cap
                changed = True
            if not existing.is_active:
                existing.is_active = True
                changed = True
        else:
            # Prohibir duplicados: Solo crear si NO existe pista para este deporte y número/nombre
            new_court = Court(
                id=uuid.uuid4(),
                club_id=sample_club_id,
                court_number=num,
                name=name,
                sport_type=s_type,
                max_capacity=max_cap,
                is_active=True,
            )
            db.add(new_court)
            active_courts.append(new_court)
            court_map[name.strip().lower()] = new_court
            num_map[num] = new_court
            changed = True

    if changed:
        await db.commit()
        res = await db.execute(select(Court).where(Court.is_active == True))
        all_active = list(res.scalars().all())
    else:
        all_active = active_courts

    # Deduplicación final estricta por (nombre, deporte) y court_id único
    final_seen = set()
    final_courts = []
    for c in all_active:
        st = (getattr(c, "sport_type", None) or getattr(c, "sport", "PADEL") or "PADEL").upper()
        nm = (c.name or "").strip().lower()
        key = (nm, st)
        if key not in final_seen:
            final_seen.add(key)
            final_courts.append(c)

    final_courts.sort(key=lambda c: (getattr(c, "court_number", None) or 99, c.name))
    return final_courts

ensure_multisport_courts = ensure_five_courts


@router.get("/courts", response_model=List[CourtResponse])
async def get_courts(
    sport: Optional[str] = Query(None, description="Filtrar por deporte (PADEL, PICKLEBALL, VOLLEYBALL, PILATES, CONSOLE)"),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene el listado ordenado de las canchas activas del club, deduplicado y con filtro opcional de deporte."""
    courts = await ensure_five_courts(db)
    if sport and sport.upper() not in ["ALL", "TODAS", ""]:
        courts = [c for c in courts if (getattr(c, "sport_type", "PADEL") or "PADEL").upper() == sport.strip().upper()]
    # Deduplicación por id y nombre+deporte
    seen_ids = set()
    seen_keys = set()
    deduped = []
    for c in courts:
        cid = str(c.id)
        st = (getattr(c, "sport_type", None) or getattr(c, "sport", "PADEL") or "PADEL").upper()
        nm = (c.name or "").strip().lower()
        key = (nm, st)
        if cid not in seen_ids and key not in seen_keys:
            seen_ids.add(cid)
            seen_keys.add(key)
            deduped.append(c)
    return deduped


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_demo_data(
    target_date: Optional[date] = Query(None, alias="date", description="Fecha inicial para sembrar 7 días"),
    db: AsyncSession = Depends(get_db),
):
    """
    Generación Automática a 7 Días (Intervalos de 1:30):
    Puebla los próximos 7 días calendario para las 5 canchas en la franja operativa
    de 06:00 a 24:00 en 12 bloques consecutivos de 90 minutos:
    (06:00-07:30, 07:30-09:00, ..., 22:30-24:00).
    Estado inicial: AVAILABLE con precios de Yield Management (Valle $80.000 / Pico $120.000).
    """
    courts = await ensure_five_courts(db)
    today = get_bogota_today()
    start_d = target_date or today
    dates_to_seed = [start_d + timedelta(days=i) for i in range(7)]

    # 12 bloques consecutivos de 90 minutos (1:30) de 06:00 a 24:00
    BLOCKS_90_MIN = [
        (time(6, 0), time(7, 30)),
        (time(7, 30), time(9, 0)),
        (time(9, 0), time(10, 30)),
        (time(10, 30), time(12, 0)),
        (time(12, 0), time(13, 30)),
        (time(13, 30), time(15, 0)),
        (time(15, 0), time(16, 30)),
        (time(16, 30), time(18, 0)),
        (time(18, 0), time(19, 30)),
        (time(19, 30), time(21, 0)),
        (time(21, 0), time(22, 30)),
        (time(22, 30), time(23, 59)),
    ]

    total_created = 0
    for day_idx, d in enumerate(dates_to_seed):
        is_weekend = d.weekday() in (5, 6)

        for court_idx, court in enumerate(courts, start=1):
            court_num = getattr(court, "court_number", None) or court_idx
            c_sport = getattr(court, "sport_type", "PADEL") or "PADEL"
            c_cap = getattr(court, "max_capacity", 4) or 4

            existing_res = await db.execute(
                select(TimeSlot.start_time).where(TimeSlot.court_id == court.id, TimeSlot.date == d)
            )
            existing_times = set(existing_res.scalars().all())

            to_add = []
            for b_idx, (start_t, end_t) in enumerate(BLOCKS_90_MIN):
                if start_t in existing_times:
                    continue

                is_pico = is_weekend or (start_t.hour >= 18)
                slot_cap = c_cap
                slot_type = "MATCH"
                instructor_name = None
                booked_spots = 0
                status_val = SlotStatus.AVAILABLE
                players = []

                if c_sport == "VOLLEYBALL":
                    base_price = Decimal("120000.00")
                    slot_mode = SlotMode.SPLIT_MATCH
                    category = "Vóley Arena Mixto"
                elif c_sport == "PILATES":
                    base_price = Decimal("180000.00")
                    slot_mode = SlotMode.SPLIT_MATCH
                    category = "Pilates Mat & Reformer"
                elif c_sport == "PICKLEBALL":
                    base_price = Decimal("120000.00") if is_pico else Decimal("80000.00")
                    slot_mode = SlotMode.SPLIT_MATCH if (start_t.hour in (18, 19, 20)) else SlotMode.FULL_COURT
                    category = "Pickleball Abierto"
                elif c_sport in ("CONSOLE", "GAMING"):
                    base_price = Decimal("20000.00")
                    slot_mode = SlotMode.SPLIT_MATCH
                    category = "Gaming / Consola"
                else:
                    # PADEL
                    base_price = Decimal("120000.00") if is_pico else Decimal("80000.00")
                    slot_mode = SlotMode.SPLIT_MATCH if (start_t.hour in (18, 19, 20) and court_num <= 3) else SlotMode.FULL_COURT
                    category = "4ta"

                to_add.append(
                    TimeSlot(
                        court_id=court.id,
                        date=d,
                        start_time=start_t,
                        end_time=end_t,
                        total_price=base_price,
                        mode=slot_mode,
                        capacity=slot_cap,
                        booked_spots=0,
                        category=category,
                        players_names=[],
                        status=SlotStatus.AVAILABLE,
                        slot_type="MATCH",
                        instructor_name=None,
                        is_promo=False,
                        sport_type=c_sport,
                    )
                )

            if to_add:
                db.add_all(to_add)
                total_created += len(to_add)

    if total_created > 0:
        await db.commit()
        return {
            "message": f"Se sembraron {total_created} turnos de 90 min exitosamente para los próximos 7 días en las {len(courts)} canchas",
            "courts_count": len(courts),
            "days_count": len(dates_to_seed),
            "slots_created": total_created,
        }

    return {
        "message": f"Los 7 días de turnos de 90 minutos ya se encontraban presentes para todas las {len(courts)} canchas",
        "courts_count": len(courts),
        "days_count": len(dates_to_seed),
        "slots_created": 0,
    }


MALOKA_WEEKLY_EVENTS = [
    {
        "id": "lun_20_22",
        "weekday": 0,  # Lunes
        "day_name": "Lunes",
        "start_time": time(20, 0),
        "end_time": time(22, 0),
        "time_str": "20:00 - 22:00",
        "name": "Americano 5ta",
        "modality": "PAREJA_FIJA",
        "modality_label": "Pareja fija",
        "category": "5ta",
        "entry_fee": Decimal("60000.00"),
        "prize_pool": Decimal("200000.00"),
        "prize_label": "$200.000 COP",
    },
    {
        "id": "mar_14_16",
        "weekday": 1,  # Martes
        "day_name": "Martes",
        "start_time": time(14, 0),
        "end_time": time(16, 0),
        "time_str": "14:00 - 16:00",
        "name": "Americano 6ta",
        "modality": "INDIVIDUAL",
        "modality_label": "Individual",
        "category": "6ta",
        "entry_fee": Decimal("25000.00"),
        "prize_pool": Decimal("100000.00"),
        "prize_label": "Premio sorpresa",
    },
    {
        "id": "mar_20_22",
        "weekday": 1,  # Martes
        "day_name": "Martes",
        "start_time": time(20, 0),
        "end_time": time(22, 0),
        "time_str": "20:00 - 22:00",
        "name": "Americano 4ta-5ta",
        "modality": "PAREJA_FIJA",
        "modality_label": "Pareja fija",
        "category": "4ta-5ta",
        "entry_fee": Decimal("60000.00"),
        "prize_pool": Decimal("200000.00"),
        "prize_label": "$200.000 COP",
    },
    {
        "id": "mie_20_22",
        "weekday": 2,  # Miércoles
        "day_name": "Miércoles",
        "start_time": time(20, 0),
        "end_time": time(22, 0),
        "time_str": "20:00 - 22:00",
        "name": "Americano 6ta",
        "modality": "PAREJA_FIJA",
        "modality_label": "Pareja fija",
        "category": "6ta",
        "entry_fee": Decimal("60000.00"),
        "prize_pool": Decimal("200000.00"),
        "prize_label": "$200.000 COP",
    },
    {
        "id": "jue_14_16",
        "weekday": 3,  # Jueves
        "day_name": "Jueves",
        "start_time": time(14, 0),
        "end_time": time(16, 0),
        "time_str": "14:00 - 16:00",
        "name": "Americano 6ta-7ma",
        "modality": "INDIVIDUAL",
        "modality_label": "Individual",
        "category": "6ta-7ma",
        "entry_fee": Decimal("30000.00"),
        "prize_pool": Decimal("90000.00"),
        "prize_label": "$90.000 COP",
    },
    {
        "id": "vie_18_20",
        "weekday": 4,  # Viernes
        "day_name": "Viernes",
        "start_time": time(18, 0),
        "end_time": time(20, 0),
        "time_str": "18:00 - 20:00",
        "name": "Americano Femenino",
        "modality": "INDIVIDUAL",
        "modality_label": "Individual",
        "category": "Femenino",
        "entry_fee": Decimal("50000.00"),
        "prize_pool": Decimal("150000.00"),
        "prize_label": "Chingotto",
    },
    {
        "id": "sab_10_12",
        "weekday": 5,  # Sábado
        "day_name": "Sábado",
        "start_time": time(10, 0),
        "end_time": time(12, 0),
        "time_str": "10:00 - 12:00",
        "name": "Americano 6ta",
        "modality": "INDIVIDUAL",
        "modality_label": "Individual",
        "category": "6ta",
        "entry_fee": Decimal("60000.00"),
        "prize_pool": Decimal("170000.00"),
        "prize_label": "$170.000 COP",
    },
    {
        "id": "sab_19_21",
        "weekday": 5,  # Sábado
        "day_name": "Sábado",
        "start_time": time(19, 0),
        "end_time": time(21, 0),
        "time_str": "19:00 - 21:00",
        "name": "Americano 5ta",
        "modality": "PAREJA_FIJA",
        "modality_label": "Pareja fija",
        "category": "5ta",
        "entry_fee": Decimal("60000.00"),
        "prize_pool": Decimal("250000.00"),
        "prize_label": "$250.000 COP",
    },
    {
        "id": "dom_18_20",
        "weekday": 6,  # Domingo
        "day_name": "Domingo",
        "start_time": time(18, 0),
        "end_time": time(20, 0),
        "time_str": "18:00 - 20:00",
        "name": "Americano 6-8",
        "modality": "PAREJA_FIJA",
        "modality_label": "Pareja fija",
        "category": "6ta-8va",
        "entry_fee": Decimal("60000.00"),
        "prize_pool": Decimal("250000.00"),
        "prize_label": "$250.000 COP",
    },
    {
        "id": "dom_20_22",
        "weekday": 6,  # Domingo
        "day_name": "Domingo",
        "start_time": time(20, 0),
        "end_time": time(22, 0),
        "time_str": "20:00 - 22:00",
        "name": "Ranking 4ta",
        "modality": "PAREJA_FIJA",
        "modality_label": "Pareja fija",
        "category": "4ta",
        "entry_fee": Decimal("100000.00"),
        "prize_pool": Decimal("600000.00"),
        "prize_label": "$600.000 COP",
    },
]


@router.get("/weekly-template", status_code=status.HTTP_200_OK)
async def get_weekly_template():
    """Retorna la plantilla semanal oficial de torneos y eventos de Capital Pádel Maloka."""
    return {
        "template_name": "Semillero Oficial Capital Pádel Maloka",
        "events": [
            {
                "id": ev["id"],
                "weekday": ev["weekday"],
                "day_name": ev["day_name"],
                "start_time": ev["start_time"].strftime("%H:%M"),
                "end_time": ev["end_time"].strftime("%H:%M"),
                "time_str": ev["time_str"],
                "name": ev["name"],
                "modality": ev["modality"],
                "modality_label": ev["modality_label"],
                "category": ev["category"],
                "entry_fee": float(ev["entry_fee"]),
                "prize_pool": float(ev["prize_pool"]),
                "prize_label": ev["prize_label"],
            }
            for ev in MALOKA_WEEKLY_EVENTS
        ],
    }


@router.post("/seed-weekly-template", status_code=status.HTTP_201_CREATED)
async def seed_weekly_template(
    payload: Optional[WeeklyTemplateSeedRequest] = Body(None),
    target_date: Optional[date] = Query(None, alias="date", description="Fecha inicial para sembrar 7 días"),
    db: AsyncSession = Depends(get_db),
):
    """
    Programador Semanal Inteligente (Semillero Oficial Capital Pádel Maloka):
    - Puebla los próximos 7 días calendario para todas las canchas (Pádel, Pickleball, Vóley, Pilates, Consola).
    - Franja operativa: 06:00 a 24:00 con bloques de 90 minutos y tarifas Valle ($80.000) / Pico ($120.000).
    - Reserva automáticamente los eventos seleccionados de la plantilla semanal de torneos en pistas de pádel (Canchas 1 a 4)
      con slot_type='AMERICANO' y status='FULLY_BOOKED'.
    - CERO reservas ficticias: players_names=[] en todos los turnos disponibles y de torneo.
    """
    courts = await ensure_five_courts(db)
    today = get_bogota_today()
    raw_d = (payload.date if payload and payload.date else None) or target_date or today
    if isinstance(raw_d, str):
        try:
            start_d = datetime.strptime(raw_d, "%Y-%m-%d").date()
        except Exception:
            start_d = today
    else:
        start_d = raw_d
    dates_to_seed = [start_d + timedelta(days=i) for i in range(7)]


    selected_ids = (
        set(payload.selected_events)
        if (payload and payload.selected_events is not None)
        else {ev["id"] for ev in MALOKA_WEEKLY_EVENTS}
    )

    def parse_time_val(t_val) -> time:
        if isinstance(t_val, time):
            return t_val
        if isinstance(t_val, str):
            parts = t_val.strip().split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return time(h, m)
        return time(20, 0)

    def parse_prize_to_decimal(val) -> Optional[Decimal]:
        if val is None:
            return None
        if isinstance(val, (int, float, Decimal)):
            return Decimal(str(val))
        val_str = str(val).replace("$", "").replace("COP", "").replace(".", "").replace(",", "").replace("k", "000").replace("K", "000").strip()
        digits = re.findall(r"\d+", val_str)
        if digits:
            try:
                return Decimal("".join(digits))
            except Exception:
                return Decimal("0.00")
        return Decimal("0.00")

    active_events = []
    if payload and payload.events:
        for ev in payload.events:
            w_start = parse_time_val(ev.get("start_time"))
            w_end = parse_time_val(ev.get("end_time"))
            e_fee = Decimal(str(ev.get("entry_fee", 60000)))
            p_pool = parse_prize_to_decimal(ev.get("prize") or ev.get("prize_pool"))
            ev_courts = [int(x) for x in ev.get("courts", [1, 2, 3, 4])]
            active_events.append({
                "id": str(ev.get("id", f"ev_{ev.get('weekday', 0)}_{w_start.hour}")),
                "weekday": int(ev.get("weekday", 0)),
                "name": str(ev.get("name", "Torneo Americano")),
                "modality": str(ev.get("modality", "PAREJA_FIJA")),
                "category": str(ev.get("category", "5ta")),
                "start_time": w_start,
                "end_time": w_end,
                "courts": ev_courts,
                "entry_fee": e_fee,
                "prize_pool": p_pool,
                "prize_label": str(ev.get("prize") or ev.get("prize_pool") or f"${p_pool:,.0f} COP"),
            })
    else:
        for ev in MALOKA_WEEKLY_EVENTS:
            if ev["id"] in selected_ids:
                active_events.append({
                    "id": ev["id"],
                    "weekday": ev["weekday"],
                    "name": ev["name"],
                    "modality": ev["modality"],
                    "category": ev["category"],
                    "start_time": ev["start_time"],
                    "end_time": ev["end_time"],
                    "courts": [1, 2, 3, 4],
                    "entry_fee": ev["entry_fee"],
                    "prize_pool": ev["prize_pool"],
                    "prize_label": ev["prize_label"],
                })

    BLOCKS_90_MIN = [
        (time(6, 0), time(7, 30)),
        (time(7, 30), time(9, 0)),
        (time(9, 0), time(10, 30)),
        (time(10, 30), time(12, 0)),
        (time(12, 0), time(13, 30)),
        (time(13, 30), time(15, 0)),
        (time(15, 0), time(16, 30)),
        (time(16, 30), time(18, 0)),
        (time(18, 0), time(19, 30)),
        (time(19, 30), time(21, 0)),
        (time(21, 0), time(22, 30)),
        (time(22, 30), time(23, 59)),
    ]

    padel_courts = [c for c in courts if (getattr(c, "sport_type", "PADEL") or "PADEL").upper() == "PADEL"]
    padel_courts.sort(key=lambda c: (getattr(c, "court_number", 99) or 99, c.name))
    padel_court_num_map = {}
    for idx, c in enumerate(padel_courts):
        c_num = getattr(c, "court_number", None) or (idx + 1)
        padel_court_num_map[c.id] = c_num

    # 1. Limpieza en lote de turnos no reservados/sin jugadores para el rango de 7 días
    res_existing = await db.execute(
        select(TimeSlot)
        .options(selectinload(TimeSlot.holds))
        .where(TimeSlot.date.in_(dates_to_seed))
    )
    all_existing = res_existing.scalars().all()
    unbooked_ids = []
    for s in all_existing:
        has_active_holds = any(
            str(getattr(h, "status", "")).upper() in ("ACTIVE", "HOLDSTATUS.ACTIVE") for h in s.holds
        )
        real_players = [
            p for p in (s.players_names or [])
            if not (isinstance(p, dict) and p.get("phone") == "+57-AMERICANO")
        ]
        has_real_players = (
            (s.booked_spots > 0 and (s.slot_type or "MATCH") not in ("AMERICANO", "TOURNAMENT"))
            or (len(real_players) > 0)
        )
        if not has_active_holds and not has_real_players:
            unbooked_ids.append(s.id)

    if unbooked_ids:
        await db.execute(delete(TimeSlot).where(TimeSlot.id.in_(unbooked_ids)))
        await db.flush()

    # 2. Generación en lote de turnos regulares y eventos de plantilla
    all_to_add = []
    scheduled_events = []

    for d in dates_to_seed:
        is_weekend = d.weekday() in (5, 6)

        for court in courts:
            c_sport = (getattr(court, "sport_type", "PADEL") or "PADEL").upper()
            c_cap = getattr(court, "max_capacity", 4) or 4
            c_num = padel_court_num_map.get(court.id, getattr(court, "court_number", 1) or 1)

            # Torneos aplican EXCLUSIVAMENTE a Pádel
            if c_sport == "PADEL":
                court_day_events = [
                    ev for ev in active_events
                    if ev["weekday"] == d.weekday() and c_num in ev["courts"]
                ]
            else:
                court_day_events = []

            for start_t, end_t in BLOCKS_90_MIN:
                # Si es cancha de Pádel y se solapa con un torneo de la plantilla, no generar turno regular
                if court_day_events:
                    overlaps = any(
                        start_t < ev["end_time"] and end_t > ev["start_time"]
                        for ev in court_day_events
                    )
                    if overlaps:
                        continue

                is_pico = is_weekend or (start_t.hour >= 18)
                slot_cap = c_cap
                if c_sport == "VOLLEYBALL":
                    base_price = Decimal("120000.00")
                    slot_mode = SlotMode.SPLIT_MATCH
                    category = "Vóley Arena Mixto"
                elif c_sport == "PILATES":
                    base_price = Decimal("180000.00")
                    slot_mode = SlotMode.SPLIT_MATCH
                    category = "Pilates Mat & Reformer"
                elif c_sport == "PICKLEBALL":
                    base_price = Decimal("120000.00") if is_pico else Decimal("80000.00")
                    slot_mode = SlotMode.SPLIT_MATCH if (start_t.hour in (18, 19, 20)) else SlotMode.FULL_COURT
                    category = "Pickleball Abierto"
                elif c_sport in ("CONSOLE", "GAMING"):
                    base_price = Decimal("20000.00")
                    slot_mode = SlotMode.SPLIT_MATCH
                    category = "Gaming / Consola"
                else:
                    base_price = Decimal("120000.00") if is_pico else Decimal("80000.00")
                    slot_mode = SlotMode.SPLIT_MATCH if (start_t.hour in (18, 19, 20) and c_num <= 3) else SlotMode.FULL_COURT
                    category = "4ta"

                all_to_add.append(
                    TimeSlot(
                        court_id=court.id,
                        date=d,
                        start_time=start_t,
                        end_time=end_t,
                        total_price=base_price,
                        mode=slot_mode,
                        capacity=slot_cap,
                        booked_spots=0,
                        category=category,
                        players_names=[],
                        status=SlotStatus.AVAILABLE,
                        slot_type="MATCH",
                        instructor_name=None,
                        is_promo=False,
                        sport_type=c_sport,
                    )
                )

            # Insertar los torneos seleccionados exclusivamente en las pistas de Pádel designadas
            if court_day_events:
                for ev in court_day_events:
                    mod_label = "Pareja Fija" if ev["modality"] == "PAREJA_FIJA" else "Individual"
                    cat_label = f"Americano {ev.get('category', '5ta')} ({mod_label})"
                    all_to_add.append(
                        TimeSlot(
                            court_id=court.id,
                            date=d,
                            start_time=ev["start_time"],
                            end_time=ev["end_time"],
                            total_price=ev["entry_fee"] * 4,
                            mode=SlotMode.FULL_COURT,
                            capacity=4,
                            booked_spots=4,
                            category=cat_label,
                            status=SlotStatus.FULLY_BOOKED,
                            slot_type="AMERICANO",
                            tournament_type=ev["modality"],
                            tournament_name=ev["name"],
                            prize_pool=ev["prize_pool"],
                            players_names=[],
                            is_promo=False,
                            sport_type="PADEL",
                        )
                    )
                    ev_desc = f"{d.strftime('%Y-%m-%d')}: {ev['name']} ({ev['start_time'].strftime('%H:%M')} - {ev['end_time'].strftime('%H:%M')})"
                    if ev_desc not in scheduled_events:
                        scheduled_events.append(ev_desc)

    if all_to_add:
        db.add_all(all_to_add)

    await db.commit()

    return {
        "status": "success",
        "message": f"Se sembraron exitosamente {len(all_to_add)} turnos para los 7 días con la plantilla de torneos Capital Pádel Maloka.",
        "courts_count": len(courts),
        "days_count": len(dates_to_seed),
        "slots_created": len(all_to_add),
        "tournaments_scheduled": len(scheduled_events),
        "scheduled_events": scheduled_events,
    }


@router.get("/{slot_id}/yield-recommendation")

async def get_yield_recommendation(
    slot_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Consulta en tiempo real la recomendación de precio del motor de Yield Management."""
    stmt = select(TimeSlot).options(selectinload(TimeSlot.court)).where(TimeSlot.id == slot_id)
    res = await db.execute(stmt)
    slot = res.scalars().first()
    if not slot:
        raise HTTPException(status_code=404, detail=f"Turno #{slot_id} no encontrado")

    yield_data = calculate_recommended_price(slot)
    return {
        "slot_id": slot.id,
        "court_id": str(slot.court_id),
        "court_name": slot.court.name if slot.court else "Cancha",
        "date": slot.date.isoformat(),
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "current_price": slot.total_price,
        "status": slot.status.value if hasattr(slot.status, "value") else str(slot.status),
        "slot_type": getattr(slot, "slot_type", "MATCH") or "MATCH",
        "instructor_name": getattr(slot, "instructor_name", None),
        **yield_data,
    }


@router.post("/{slot_id}/reserve-or-block", response_model=TimeSlotResponse)
@router.post("/{slot_id}/set-type", response_model=TimeSlotResponse)
async def reserve_or_block_slot(
    slot_id: int,
    payload: ReserveOrBlockRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Permite a recepción crear una reserva manual, bloquear la cancha por mantenimiento,
    o programar una clase/academia con profesor asignado y precio recomendado o personalizado.
    """
    stmt = select(TimeSlot).options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds)).where(TimeSlot.id == slot_id)
    res = await db.execute(stmt)
    slot = res.scalars().first()
    if not slot:
        raise HTTPException(status_code=404, detail=f"Turno #{slot_id} no encontrado")

    validate_slot_not_past(slot)

    stype = (payload.slot_type or "MATCH").upper()
    slot.slot_type = stype

    if payload.instructor_name:
        slot.instructor_name = payload.instructor_name

    if payload.mode:
        slot.mode = payload.mode

    # Asignar precio personalizado o recomendado por Yield
    # Asignar precio personalizado o recomendado por Yield
    if payload.custom_price is not None and payload.custom_price >= 0:
        slot.total_price = payload.custom_price
    else:
        yield_data = calculate_recommended_price(slot)
        slot.total_price = yield_data["recommended_price"]

    # Detección automática de Primera Visita en Customer
    c_info = await get_or_create_booking_customer(
        db=db,
        name=payload.client_name,
        phone=payload.client_phone,
        category=payload.client_category,
        client_type=payload.client_type,
    )

    # Procesar según tipo de turno (6 opciones operativas completas)
    if stype == "MAINTENANCE":
        slot.mode = SlotMode.FULL_COURT
        slot.status = SlotStatus.BLOCKED
        slot.booked_spots = slot.capacity
        slot.players_names = [{
            "spot_index": 1,
            "phone": "+57-MANT",
            "display_name": payload.client_name or "Mantenimiento / Lluvia",
            "client_tier": "BLOCKED",
            "host_phone": None,
            "is_first_visit": False,
            "onboarding_status": "PENDING",
            "customer_id": None,
        }]
    elif stype in ("CLASS", "ACADEMY"):
        slot.mode = SlotMode.FULL_COURT
        slot.status = SlotStatus.FULLY_BOOKED
        slot.booked_spots = slot.capacity
        prof_title = payload.instructor_name or "Profesor Asignado"
        student_label = payload.client_name or f"Clase con {prof_title}"
        slot.players_names = [{
            "spot_index": 1,
            "phone": payload.client_phone or "+57-ACADEMY",
            "display_name": student_label,
            "client_tier": payload.client_type or "MEMBER",
            "host_phone": None,
            "is_first_visit": c_info["is_first_visit"],
            "onboarding_status": c_info["onboarding_status"],
            "customer_id": c_info["customer_id"],
        }]
    elif stype == "MEMBER":
        # Socio / Membresía (Exento de pasarela / Hold $0)
        slot.mode = SlotMode.FULL_COURT
        slot.status = SlotStatus.FULLY_BOOKED
        slot.booked_spots = slot.capacity
        if payload.custom_price is None:
            slot.total_price = Decimal("0.00")
        client_name = payload.client_name or "Socio VIP"
        slot.players_names = [{
            "spot_index": 1,
            "phone": payload.client_phone or "+57-SOCIO",
            "display_name": f"💎 {client_name}",
            "client_tier": "VIP_PAY_ON_SITE",
            "host_phone": None,
            "is_first_visit": c_info["is_first_visit"],
            "onboarding_status": c_info["onboarding_status"],
            "customer_id": c_info["customer_id"],
        }]
    elif stype == "PAY_AT_VENUE":
        # Pago en Sede (Pay-at-venue / Datáfono)
        slot.mode = SlotMode.FULL_COURT
        slot.status = SlotStatus.FULLY_BOOKED
        slot.booked_spots = slot.capacity
        client_name = payload.client_name or "Pago en Sede"
        slot.players_names = [{
            "spot_index": 1,
            "phone": payload.client_phone or "+57-SEDE",
            "display_name": f"💳 {client_name}",
            "client_tier": "VIP_PAY_ON_SITE",
            "host_phone": None,
            "is_first_visit": c_info["is_first_visit"],
            "onboarding_status": c_info["onboarding_status"],
            "customer_id": c_info["customer_id"],
        }]
    elif stype == "SPLIT_MATCH":
        # Partido Abierto (Split 1/4 - Cuota por jugador)
        slot.mode = SlotMode.SPLIT_MATCH
        if payload.client_category:
            slot.category = payload.client_category
        if payload.client_name:
            slot.status = SlotStatus.PARTIALLY_BOOKED
            slot.booked_spots = 1
            slot.players_names = [{
                "spot_index": 1,
                "phone": payload.client_phone or "+57-RECEPCION",
                "display_name": payload.client_name,
                "client_tier": payload.client_type or "STANDARD",
                "host_phone": None,
                "is_first_visit": c_info["is_first_visit"],
                "onboarding_status": c_info["onboarding_status"],
                "customer_id": c_info["customer_id"],
            }]
        else:
            slot.status = SlotStatus.AVAILABLE
            slot.booked_spots = 0
            slot.players_names = []
    elif stype in ("FULL_COURT", "MATCH"):
        # Partido Completo (Reserva 100% - Cancha completa)
        slot.mode = SlotMode.FULL_COURT
        slot.status = SlotStatus.FULLY_BOOKED
        slot.booked_spots = slot.capacity
        slot.players_names = [{
            "spot_index": 1,
            "phone": payload.client_phone or "+57-RECEPCION",
            "display_name": payload.client_name or "Reserva Completa",
            "client_tier": payload.client_type or "STANDARD",
            "host_phone": None,
            "is_first_visit": c_info["is_first_visit"],
            "onboarding_status": c_info["onboarding_status"],
            "customer_id": c_info["customer_id"],
        }]
    elif payload.client_name:
        slot.status = SlotStatus.FULLY_BOOKED
        slot.booked_spots = slot.capacity
        slot.players_names = [{
            "spot_index": 1,
            "phone": payload.client_phone or "+57-RECEPCION",
            "display_name": payload.client_name,
            "client_tier": payload.client_type or "VIP_PAY_ON_SITE",
            "host_phone": None,
            "is_first_visit": c_info["is_first_visit"],
            "onboarding_status": c_info["onboarding_status"],
            "customer_id": c_info["customer_id"],
        }]
    else:
        # Revertir a disponible si se pasa AVAILABLE o vacío
        slot.status = SlotStatus.AVAILABLE
        slot.booked_spots = 0
        slot.players_names = []
        slot.slot_type = "MATCH"

    await db.commit()
    await db.refresh(slot)

    # Operational Audit Trail
    try:
        if slot.status == SlotStatus.MAINTENANCE:
            audit_action = "BLOCK_SLOT"
        elif slot.status in (SlotStatus.FULLY_BOOKED, SlotStatus.PARTIALLY_BOOKED):
            audit_action = "RESERVA_CREADA"
        else:
            audit_action = "RESERVA_MODIFICADA"
        court_name = slot.court.name if slot.court else f"Cancha #{slot.court_id}"
        details_msg = f"Asignación {assignment_type} en {court_name} ({slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')})"
        if payload.client_name:
            details_msg += f" | Cliente: {payload.client_name}"
        if payload.notes:
            details_msg += f" | Nota: {payload.notes}"
        await log_activity(
            db=db,
            action=audit_action,
            entity_name="SLOT",
            entity_id=str(slot.id),
            details=details_msg,
            username_snapshot="Camilo Real (Recepción)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error in reserve_or_block_slot: {e}")

    now_utc = datetime.now(timezone.utc)
    return compute_slot_response(slot, now_utc)


@router.post("/create-americano", response_model=List[TimeSlotResponse])
@router.post("/tournaments/americano", response_model=List[TimeSlotResponse])
async def create_americano(
    payload: CreateAmericanoRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Crea un evento Torneo Americano bloqueando simultáneamente de 2 a 5 canchas
    durante 2h, 2.5h o 3h continuas, con bolsa de premios y modalidad PAREJA_FIJA o INDIVIDUAL.
    Soporta rutas POST /api/v1/slots/create-americano y POST /api/v1/slots/tournaments/americano.
    """
    if len(payload.court_ids) < 2:
        raise HTTPException(status_code=400, detail="Un torneo americano requiere seleccionar al menos 2 canchas.")
    if len(payload.court_ids) > 5:
        raise HTTPException(status_code=400, detail="No se pueden seleccionar más de 5 canchas para un americano.")

    t_name = payload.get_name() if hasattr(payload, "get_name") else (payload.tournament_name or getattr(payload, "name", "Torneo Americano") or "Torneo Americano")
    t_type = getattr(payload, "modality", None) or payload.tournament_type or "PAREJA_FIJA"
    duration_mins = payload.get_duration_minutes() if hasattr(payload, "get_duration_minutes") else (
        int(payload.duration_hours * 60) if getattr(payload, "duration_hours", None) else (payload.duration_minutes or 120)
    )

    start_dt = datetime.combine(payload.date, payload.start_time)
    end_dt = start_dt + timedelta(minutes=duration_mins)
    end_time_val = time(23, 59) if (end_dt.time() == time(0, 0) or end_dt.date() > payload.date) else end_dt.time()

    # 1. Validación Estricta Anti-Choques en todas las canchas seleccionadas
    import uuid
    for court_id_str in payload.court_ids:
        c_uuid = None
        try:
            c_uuid = uuid.UUID(court_id_str)
        except Exception:
            court_res = await db.execute(select(Court).where(Court.name.ilike(f"%{court_id_str}%")))
            c_obj = court_res.scalars().first()
            if c_obj:
                c_uuid = c_obj.id

        if not c_uuid:
            continue

        chk_stmt = (
            select(TimeSlot)
            .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
            .where(
                TimeSlot.court_id == c_uuid,
                TimeSlot.date == payload.date,
                TimeSlot.start_time < end_time_val,
                TimeSlot.end_time > payload.start_time,
            )
        )
        chk_res = await db.execute(chk_stmt)
        for s in chk_res.scalars().all():
            has_active_holds = any(h.status == HoldStatus.ACTIVE for h in s.holds)
            is_booked = s.status in [SlotStatus.FULLY_BOOKED, SlotStatus.PARTIALLY_BOOKED]
            is_class = s.slot_type in ["CLASS", "ACADEMY"]
            has_players = s.booked_spots > 0 or len(s.players_names or []) > 0
            if is_booked or has_active_holds or is_class or has_players:
                c_name = s.court.name if s.court else f"Pista {court_id_str}"
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Colisión detectada: La {c_name} ya tiene una reserva activa en el horario "
                        f"{s.start_time.strftime('%H:%M')}-{s.end_time.strftime('%H:%M')} "
                        f"(Estado: {s.slot_type}/{s.status.value}). Libera el turno antes de crear el torneo."
                    ),
                )

    created_slots = []
    now_utc = datetime.now(timezone.utc)

    for court_id_str in payload.court_ids:
        try:
            c_uuid = uuid.UUID(court_id_str)
        except Exception:
            court_res = await db.execute(select(Court).where(Court.name.like(f"%{court_id_str}%")))
            c_obj = court_res.scalars().first()
            if not c_obj:
                continue
            c_uuid = c_obj.id

        # Buscar slots de esta cancha que se solapen con el horario del torneo
        overlap_stmt = (
            select(TimeSlot)
            .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
            .where(
                TimeSlot.court_id == c_uuid,
                TimeSlot.date == payload.date,
                TimeSlot.start_time < end_time_val,
                TimeSlot.end_time > payload.start_time,
            )
        )
        res_overlap = await db.execute(overlap_stmt)
        overlap_slots = list(res_overlap.scalars().all())

        prize_val = payload.prize_pool or Decimal("300000.00")
        prize_str = f"${int(prize_val):,} COP"
        label_t = "Pareja Fija" if t_type == "PAREJA_FIJA" else "Individual"
        cat_label = f"Americano ({label_t})"

        player_entry = [{
            "spot_index": 1,
            "phone": "+57-AMERICANO",
            "display_name": f"🏆 {t_name} ({prize_str})",
            "client_tier": "VIP_PAY_ON_SITE",
            "host_phone": None,
        }]

        if overlap_slots:
            main_slot = overlap_slots[0]
            main_slot.start_time = payload.start_time
            main_slot.end_time = end_time_val
            main_slot.slot_type = "AMERICANO"
            main_slot.tournament_type = t_type
            main_slot.tournament_name = t_name
            main_slot.prize_pool = prize_val
            main_slot.category = cat_label
            main_slot.status = SlotStatus.FULLY_BOOKED
            main_slot.booked_spots = 4
            main_slot.total_price = prize_val
            main_slot.players_names = player_entry

            for extra in overlap_slots[1:]:
                await db.delete(extra)

            created_slots.append(main_slot)
        else:
            new_slot = TimeSlot(
                court_id=c_uuid,
                date=payload.date,
                start_time=payload.start_time,
                end_time=end_time_val,
                total_price=prize_val,
                mode=SlotMode.FULL_COURT,
                capacity=4,
                booked_spots=4,
                category=cat_label,
                status=SlotStatus.FULLY_BOOKED,
                slot_type="AMERICANO",
                tournament_type=t_type,
                tournament_name=t_name,
                prize_pool=prize_val,
                players_names=player_entry,
                is_promo=False,
            )
            db.add(new_slot)
            created_slots.append(new_slot)

    await db.commit()
    created_ids = [s.id for s in created_slots]
    res_loaded = await db.execute(
        select(TimeSlot)
        .options(selectinload(TimeSlot.holds), selectinload(TimeSlot.court))
        .where(TimeSlot.id.in_(created_ids))
    )
    loaded_slots = res_loaded.scalars().all()

    # Operational Audit Trail
    try:
        court_names = [s.court.name for s in loaded_slots if s.court]
        await log_activity(
            db=db,
            action="CREATE_AMERICANO",
            entity_name="TOURNAMENT",
            entity_id=str(loaded_slots[0].id) if loaded_slots else None,
            details=f"Torneo Americano '{t_name}' ({t_type}) creado para {payload.date} ({payload.start_time}). Canchas: {court_names or payload.court_ids}. Valor: ${price_val:,.0f} COP",
            username_snapshot="Camilo Real (Director Deportivo)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error in create_americano: {e}")

    return [compute_slot_response(s, now_utc) for s in loaded_slots]


@router.get("/club-config")
@router.get("/admin/club-settings")
async def get_club_configuration(db: AsyncSession = Depends(get_db)):
    """Retorna la configuración operativa del club y las canchas por deporte."""
    config = get_club_config()
    courts = await ensure_five_courts(db)
    return {
        **config,
        "config": config,
        "courts": [
            {
                "id": str(c.id),
                "court_number": getattr(c, "court_number", idx + 1),
                "name": c.name,
                "is_active": c.is_active,
                "sport_type": getattr(c, "sport_type", "PADEL") or "PADEL",
                "max_capacity": getattr(c, "max_capacity", 4) or 4,
            }
            for idx, c in enumerate(courts)
        ]
    }


@router.post("/club-config")
@router.post("/admin/club-settings")
async def update_club_configuration(
    payload: ClubConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza en caliente la configuración de tarifas y canchas del club."""
    updated = update_club_config(payload.model_dump(exclude_unset=True, exclude={"courts"}))
    if payload.courts:
        courts = await ensure_five_courts(db)
        court_map = {str(c.id): c for c in courts}
        for c_data in payload.courts:
            cid = str(c_data.get("id"))
            if cid in court_map:
                if "name" in c_data and c_data["name"]:
                    court_map[cid].name = c_data["name"]
                if "is_active" in c_data:
                    court_map[cid].is_active = bool(c_data["is_active"])
                if "sport_type" in c_data and c_data["sport_type"]:
                    court_map[cid].sport_type = str(c_data["sport_type"]).upper()
                if "max_capacity" in c_data and c_data["max_capacity"] is not None:
                    court_map[cid].max_capacity = int(c_data["max_capacity"])
        await db.commit()

    # Operational Audit Trail
    try:
        await log_activity(
            db=db,
            action="UPDATE_CONFIG",
            entity_name="CONFIG",
            entity_id="CLUB_SETTINGS",
            details="Actualización de tarifas y configuración del club",
            username_snapshot="Camilo Real (Director Deportivo)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error in update_club_config: {e}")

    courts = await ensure_five_courts(db)
    return {
        "message": "Configuración del club actualizada exitosamente",
        "config": updated,
        "courts": [
            {
                "id": str(c.id),
                "court_number": getattr(c, "court_number", idx + 1),
                "name": c.name,
                "is_active": c.is_active,
                "sport_type": getattr(c, "sport_type", "PADEL") or "PADEL",
                "max_capacity": getattr(c, "max_capacity", 4) or 4,
            }
            for idx, c in enumerate(courts)
        ]
    }


def parse_time_token(t_str: str) -> time:
    clean = t_str.strip().lower()
    is_pm = "pm" in clean
    is_am = "am" in clean
    num_part = re.sub(r"[^\d:]", "", clean)
    parts = num_part.split(":")
    hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    if is_pm and hours < 12:
        hours += 12
    elif is_am and hours == 12:
        hours = 0
    return time(hours, minutes)


DISCARD_PLAYER_PATTERNS = [
    "CUPO DISPONIBLE",
    "CUPO LIBRE",
    "DISPONIBLE",
    "LIBRE",
    "PARTIDO CERRADO",
    "PARTIDO ABIERTO",
    "CERRADO",
    "ABIERTO",
    "CUPOS LIMITADOS",
    "INSCRÍBETE",
    "INSCRIBETE",
    "POR CONFIRMAR",
    "LISTA DE ESPERA",
    "ESPERA",
    "CANCELADO",
    "VACANTE",
    "PENDIENTE",
]


def clean_and_validate_player_name(raw_name: str) -> Optional[str]:
    """
    Limpia números, viñetas, guiones, emojis y valida
    estrictamente que el nombre de jugador sea válido y no una cabecera, fecha, horario o cupo libre.
    """
    from app.services.whatsapp import clean_player_name
    return clean_player_name(raw_name)


@router.post("/parse-open-match", response_model=WhatsAppConvocatoriaResponse, status_code=status.HTTP_200_OK)
async def parse_open_match(
    payload: WhatsAppConvocatoriaRequest,
    db: AsyncSession = Depends(get_db),
):
    """Parsea una convocatoria multideporte de WhatsApp, sincroniza el TimeSlot y devuelve el mensaje de confirmación."""
    raw = payload.raw_text

    # 1. Detectar Deporte
    detected_sport = detect_sport_from_text(raw)
    sport_emoji = get_sport_emoji(detected_sport)
    sport_cap = get_sport_default_capacity(detected_sport)

    # 2. Parsear fecha
    target_date = get_bogota_today()
    months = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }
    date_match = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-záéíóú]+)", raw, re.IGNORECASE)
    if date_match and date_match.group(2).lower() in months:
        day = int(date_match.group(1))
        month = months[date_match.group(2).lower()]
        target_date = date(target_date.year, month, day)

    # 3. Parsear horario
    time_match = re.search(
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        raw,
        re.IGNORECASE,
    )
    if time_match:
        start_t = parse_time_token(time_match.group(1))
        end_t = parse_time_token(time_match.group(2))
    else:
        start_t = time(14, 0)
        end_t = time(15, 30)

    # 4. Parsear categoría
    cat_match = re.search(r"(?:Categor[íi]a|Cat\.?):\s*([^\n\r]+)", raw, re.IGNORECASE)
    category = cat_match.group(1).strip() if cat_match else ("Vóley Playa" if detected_sport == "VOLLEYBALL" else ("Pilates Reformer" if detected_sport == "PILATES" else "4ta"))

    # 5. Parsear precio sugerido en texto
    price_match = re.search(
        r"(?:💰|\$|COP|valor|precio)\s*:?\s*(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+)",
        raw,
        re.IGNORECASE,
    )
    if price_match:
        price_clean = price_match.group(1).replace(".", "").replace(",", ".")
        price_per_spot = Decimal(price_clean)
    else:
        price_per_spot = Decimal("20000.00") if detected_sport == "VOLLEYBALL" else Decimal("15000.00")

    # 6. Parsear jugadores con filtrado estricto multideporte y capacidad dinámica
    from app.services.whatsapp import parse_flexible_player_list
    raw_players = parse_flexible_player_list(raw, max_capacity=sport_cap)
    spots_count = len(raw_players)

    # 7. Buscar turnos existentes para esta fecha y franja horaria
    slot_stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
        .where(
            TimeSlot.date == target_date,
            TimeSlot.start_time == start_t,
        )
    )
    existing_slots_res = await db.execute(slot_stmt)
    matching_slots = existing_slots_res.scalars().all()

    # Priorizar coincidencia exacta de deporte si hay múltiples pistas en el mismo horario
    if matching_slots:
        sport_matched = [
            s for s in matching_slots
            if (getattr(s, "sport_type", None) or (s.court.sport_type if s.court else "PADEL")) == detected_sport
        ]
        if sport_matched:
            matching_slots = sport_matched

    start_str = start_t.strftime("%I:%M%p").lower()
    end_str = end_t.strftime("%I:%M%p").lower()
    date_formatted = target_date.strftime("%d/%m/%Y")

    if not matching_slots:
        warning_reply = (
            f"⚠️ *TURNO NO ENCONTRADO EN SISTEMA* ⚠️\n"
            f"📍 Capital Sports Club\n"
            f"📅 {date_formatted} | ⌚ {start_str} - {end_str}\n\n"
            f"No existe un turno habilitado en la programación para este horario ({detected_sport}).\n"
            f"Por favor consulta en recepción o en el Dashboard los turnos oficiales antes de convocar."
        )
        return WhatsAppConvocatoriaResponse(
            date=str(target_date),
            start_time=str(start_t),
            end_time=str(end_t),
            category=category,
            price_per_spot=price_per_spot,
            players=raw_players,
            participants=[],
            spots_count=spots_count,
            free_spots=max(0, sport_cap - spots_count),
            is_closed=False,
            slot_id=None,
            whatsapp_reply=warning_reply,
        )

    # Filtrar slots elegibles
    eligible_slots = [
        s for s in matching_slots
        if s.status != SlotStatus.BLOCKED and (s.mode == SlotMode.SPLIT_MATCH or s.status == SlotStatus.AVAILABLE)
    ]

    if not eligible_slots:
        warning_reply = (
            f"⚠️ *TURNO NO DISPONIBLE PARA CONVOCATORIA* ⚠️\n"
            f"📍 Capital Sports Club\n"
            f"📅 {date_formatted} | ⌚ {start_str} - {end_str}\n\n"
            f"Este horario no admite convocatoria abierta (cancha completa ya reservada o turno bloqueado).\n"
            f"Por favor consulta otros turnos disponibles en recepción."
        )
        return WhatsAppConvocatoriaResponse(
            date=str(target_date),
            start_time=str(start_t),
            end_time=str(end_t),
            category=category,
            price_per_spot=price_per_spot,
            players=raw_players,
            participants=[],
            spots_count=spots_count,
            free_spots=max(0, sport_cap - spots_count),
            is_closed=False,
            slot_id=None,
            whatsapp_reply=warning_reply,
        )

    slot = next((s for s in eligible_slots if s.mode == SlotMode.SPLIT_MATCH), eligible_slots[0])
    effective_cap = slot.capacity or sport_cap
    free_spots = max(0, effective_cap - spots_count)
    is_closed = (spots_count >= effective_cap)

    prev_participants = to_participants_list(slot.players_names) if slot else []
    prev_by_name = {p["display_name"].strip().lower(): p for p in prev_participants}
    prev_names_set = set(prev_by_name.keys())
    incoming_names_set = set(p.strip().lower() for p in raw_players)

    # Inmutabilidad: Precio y Cuota dinámica prorrateada para Vóley
    if detected_sport == "VOLLEYBALL":
        total_court_price = slot.total_price if slot.total_price > 0 else Decimal("120000.00")
        if spots_count > 0:
            official_price_per_spot = (total_court_price / Decimal(spots_count)).quantize(Decimal("0.01"))
        else:
            official_price_per_spot = (total_court_price / Decimal(effective_cap)).quantize(Decimal("0.01"))
    else:
        official_price_per_spot = (slot.total_price / Decimal(effective_cap)).quantize(Decimal("0.01"))

    court_name = slot.court.name if slot.court else "Capital Sports Club"

    # Anti-overbooking
    if slot.booked_spots >= effective_cap and slot.status == SlotStatus.FULLY_BOOKED:
        if spots_count >= effective_cap and incoming_names_set != prev_names_set:
            warning_reply = (
                f"⚠️ *TURNO COMPLETO SIN CUPOS DISPONIBLES* ⚠️\n"
                f"📍 {court_name}\n"
                f"📅 {date_formatted} | ⌚ {start_str} - {end_str}\n\n"
                f"Este turno ya completó sus {effective_cap} cupos y se encuentra cerrado.\n"
                f"No hay cupos disponibles para esta franja horaria."
            )
            return WhatsAppConvocatoriaResponse(
                date=str(slot.date),
                start_time=str(slot.start_time),
                end_time=str(slot.end_time),
                category=category,
                price_per_spot=official_price_per_spot,
                players=raw_players,
                participants=[SlotParticipant(**p) for p in prev_participants],
                spots_count=effective_cap,
                free_spots=0,
                is_closed=True,
                slot_id=slot.id,
                whatsapp_reply=warning_reply,
            )

    norm_sender = normalize_phone(payload.sender_phone) if payload.sender_phone else None
    assigned_sender = False

    participants = []
    for i, p_name in enumerate(raw_players, start=1):
        existing = prev_by_name.get(p_name.lower())
        if existing and existing.get("phone") and not str(existing["phone"]).startswith("+57-WA-"):
            phone = existing["phone"]
            tier = existing.get("client_tier", "STANDARD")
            h_phone = existing.get("host_phone")
        elif norm_sender and not assigned_sender and (i == len(raw_players) or len(raw_players) > len(prev_participants)):
            phone = norm_sender
            tier = "STANDARD"
            h_phone = None
            assigned_sender = True
        elif norm_sender and len(raw_players) == 1 and not assigned_sender:
            phone = norm_sender
            tier = "STANDARD"
            h_phone = None
            assigned_sender = True
        else:
            phone = f"+57-WA-{p_name.lower().replace(' ', '')}"
            tier = "STANDARD"
            h_phone = None

        # Detección de Cliente y Primera Visita por teléfono o nombre
        cust_info = await get_or_create_booking_customer(
            db=db,
            name=p_name,
            phone=phone if not str(phone).startswith("+57-WA-") else None,
            category=category,
            client_type=tier,
        )

        participants.append({
            "spot_index": i,
            "phone": phone,
            "display_name": p_name,
            "client_tier": tier,
            "host_phone": h_phone,
            "is_first_visit": cust_info["is_first_visit"],
            "onboarding_status": cust_info["onboarding_status"],
            "customer_id": cust_info["customer_id"],
        })

    slot_status = SlotStatus.FULLY_BOOKED if is_closed else (
        SlotStatus.PARTIALLY_BOOKED if spots_count > 0 else SlotStatus.AVAILABLE
    )

    slot.mode = SlotMode.SPLIT_MATCH
    slot.players_names = participants
    slot.booked_spots = spots_count
    slot.capacity = effective_cap
    slot.category = category
    slot.status = slot_status
    slot.sport_type = detected_sport

    if is_closed:
        if not slot.closed_at:
            slot.closed_at = datetime.now(timezone.utc)
    else:
        slot.closed_at = None

    await db.commit()
    await db.refresh(slot)

    # Formatear respuesta WhatsApp oficial multideporte
    from app.services.whatsapp import format_whatsapp_reply
    reply = format_whatsapp_reply(slot)

    return WhatsAppConvocatoriaResponse(
        date=str(slot.date),
        start_time=str(slot.start_time),
        end_time=str(slot.end_time),
        category=category,
        price_per_spot=official_price_per_spot,
        players=raw_players,
        participants=[SlotParticipant(**p) for p in participants],
        spots_count=spots_count,
        free_spots=free_spots,
        is_closed=is_closed,
        slot_id=slot.id,
        whatsapp_reply=reply,
    )
@router.post("/drop-player", response_model=DropPlayerResponse, status_code=status.HTTP_200_OK)
async def drop_player(
    payload: DropPlayerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Seguridad en Bajas: Permite a un jugador o su titular cancelar su cupo en un turno.
    Verifica que sender_phone coincida con phone o host_phone del cupo. Si no coincide, retorna 403 Forbidden.
    """
    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.holds), selectinload(TimeSlot.court))
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

    norm_sender = normalize_phone(payload.sender_phone)
    if not norm_sender:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar un número de teléfono válido para validar la baja",
        )

    participants = to_participants_list(slot.players_names)

    # Buscar participante por phone o host_phone
    matched_idx = -1
    matched_player = None
    for idx, p in enumerate(participants):
        p_phone = normalize_phone(p.get("phone"))
        h_phone = normalize_phone(p.get("host_phone"))
        if p_phone == norm_sender or h_phone == norm_sender:
            matched_idx = idx
            matched_player = p
            break

    if matched_idx == -1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El número no es titular del cupo que intenta cancelar",
        )

    # 1. Remover al participante autenticado
    removed_p = participants.pop(matched_idx)

    # 2. Re-indexar los cupos restantes (1..N)
    for i, p in enumerate(participants, start=1):
        p["spot_index"] = i

    slot.players_names = participants
    slot.booked_spots = max(0, slot.booked_spots - 1)

    # 3. Restaurar estado del turno
    if slot.booked_spots == 0:
        slot.status = SlotStatus.AVAILABLE
    else:
        slot.status = SlotStatus.PARTIALLY_BOOKED

    # 4. Cancelar holds activos de este teléfono en el slot si existen
    for hold in slot.holds:
        if hold.status == HoldStatus.ACTIVE and normalize_phone(hold.customer_phone) == norm_sender:
            hold.status = HoldStatus.CANCELLED

    await db.commit()
    await db.refresh(slot)

    # Operational Audit Trail
    try:
        await log_activity(
            db=db,
            action="CANCEL_SLOT_PLAYER",
            entity_name="SLOT",
            entity_id=str(payload.slot_id),
            details=f"Baja de jugador '{payload.player_name}' en slot #{payload.slot_id}",
            username_snapshot="Camilo Real (Recepción)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error in drop_player: {e}")

    now_utc = datetime.now(timezone.utc)
    slot_resp = compute_slot_response(slot, now_utc)

    return DropPlayerResponse(
        message=f"Cupo {removed_p['spot_index']} ({removed_p['display_name']}) liberado con éxito. Turno actualizado a PARTIDO ABIERTO.",
        slot_id=slot.id,
        freed_spot=removed_p["spot_index"],
        freed_player_name=removed_p["display_name"],
        freed_phone=removed_p["phone"],
        available_spots=slot_resp.available_spots,
        status=slot_resp.status,
    )


class AssignSpotRequest(BaseModel):
    slot_id: int
    customer_name: Optional[str] = None
    client_name: Optional[str] = None
    customer_phone: Optional[str] = None
    client_phone: Optional[str] = None
    spots_count: int = Field(default=1, ge=1, le=4)
    method: str = "COUNTER"  # "COUNTER", "MEMBERSHIP", "DIRECT"
    client_tier: Optional[str] = None


@router.post("/assign-spot", status_code=status.HTTP_200_OK)
async def assign_spot(
    payload: AssignSpotRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Asignación directa e inmediata de cupo(s) desde recepción:
    - Método 'COUNTER' (Efectivo/Datáfono en counter): Confirma de una vez sin hold temporal.
    - Método 'MEMBERSHIP': Descuenta beneficio de membresía sin pasarela de pago.
    """
    name = (payload.customer_name or payload.client_name or "").strip()
    phone = (payload.customer_phone or payload.client_phone or "").strip()
    if not name or not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nombre y teléfono del jugador son requeridos.",
        )

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
            detail="El slot especificado no existe.",
        )

    validate_slot_not_past(slot)

    if slot.status == SlotStatus.BLOCKED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El slot se encuentra bloqueado para reservas.",
        )

    now_utc = datetime.now(timezone.utc)

    # Calcular cupos disponibles reales
    active_holds_spots = sum(
        hold.spots_held
        for hold in slot.holds
        if hold.status == HoldStatus.ACTIVE and ensure_utc(hold.expires_at) > now_utc
    )
    available_spots = slot.capacity - slot.booked_spots - active_holds_spots

    if payload.spots_count > available_spots:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No hay suficientes cupos disponibles. Cupos disponibles: {available_spots}.",
        )

    method_upper = payload.method.upper()
    is_membership = method_upper == "MEMBERSHIP" or (payload.client_tier and payload.client_tier.upper() in [
        "MEMBER", "TAPIA", "COELLO", "GALAN", "CHINGOTTO", "LEBRON"
    ])

    if is_membership:
        tier_str = payload.client_tier.upper() if payload.client_tier else "MEMBER"
        pay_status = PaymentStatus.MEMBER_EXEMPT
        amount = Decimal("0.00")
        ref_prefix = "MEM"
    else:
        tier_str = payload.client_tier.upper() if payload.client_tier else "VIP_PAY_ON_SITE"
        pay_status = PaymentStatus.PAID if method_upper == "COUNTER" else PaymentStatus.PENDING_ON_SITE
        price_per_spot = slot.total_price / Decimal(slot.capacity)
        amount = (price_per_spot * Decimal(payload.spots_count)).quantize(Decimal("0.01"))
        ref_prefix = "POS" if method_upper == "COUNTER" else "VIP"

    # Actualizar participantes del slot
    slot.booked_spots += payload.spots_count
    current_participants = to_participants_list(slot.players_names)
    current_participants.append({
        "spot_index": len(current_participants) + 1,
        "phone": phone,
        "display_name": name,
        "client_tier": tier_str,
        "host_phone": None,
    })
    for g in range(2, payload.spots_count + 1):
        current_participants.append({
            "spot_index": len(current_participants) + 1,
            "phone": f"{phone}#GUEST{g}",
            "display_name": f"{name} (Invitado {g})",
            "client_tier": tier_str,
            "host_phone": phone,
        })
    slot.players_names = current_participants

    if slot.booked_spots >= slot.capacity:
        slot.status = SlotStatus.FULLY_BOOKED
    else:
        slot.status = SlotStatus.PARTIALLY_BOOKED

    # Crear Booking confirmado
    booking_ref = f"{ref_prefix}-{uuid.uuid4().hex[:8].upper()}"
    new_booking = Booking(
        slot_id=slot.id,
        customer_phone=phone,
        customer_name=name,
        spots_booked=payload.spots_count,
        amount_paid=amount,
        payment_reference=booking_ref,
        transaction_id=f"{ref_prefix}-TX-{uuid.uuid4().hex[:8].upper()}",
        created_at=now_utc,
        client_tier=ClientTier.MEMBER if is_membership else ClientTier.VIP_PAY_ON_SITE,
        payment_status=pay_status,
    )
    db.add(new_booking)

    # Crear Hold representativo en estado CONFIRMED
    new_hold = SlotHold(
        slot_id=slot.id,
        customer_phone=phone,
        customer_name=name,
        spots_held=payload.spots_count,
        amount_to_pay=amount,
        expires_at=now_utc + timedelta(hours=24),
        status=HoldStatus.CONFIRMED,
        payment_reference=booking_ref,
        client_tier=ClientTier.MEMBER if is_membership else ClientTier.VIP_PAY_ON_SITE,
        payment_status=pay_status,
    )
    db.add(new_hold)

    # Actualizar o registrar historial del cliente en CRM
    cust_stmt = select(Customer).where(Customer.phone == phone)
    cust_res = await db.execute(cust_stmt)
    cust = cust_res.scalar_one_or_none()
    if cust:
        cust.total_bookings_completed += payload.spots_count
        cust.is_first_visit = False
        if cust.onboarding_status == "PENDING":
            cust.onboarding_status = "WELCOMED"
    else:
        new_cust = Customer(
            name=name,
            phone=phone,
            category="4ta",
            client_type="Socio VIP" if is_membership else "Estándar",
            membership_tier=tier_str if tier_str in ["TAPIA", "COELLO", "GALAN", "CHINGOTTO", "LEBRON"] else "ESTANDAR",
            total_bookings_completed=payload.spots_count,
            is_first_visit=False,
            onboarding_status="WELCOMED",
        )
        db.add(new_cust)

    await db.commit()
    await db.refresh(slot)

    # Registro de auditoría
    try:
        await log_activity(
            db=db,
            action="ASSIGN_SPOT",
            entity_name="SLOT",
            entity_id=str(slot.id),
            details=f"Asignación confirmada de {payload.spots_count} cupo(s) a '{name}' ({phone}) vía {payload.method}. Ref: {booking_ref}",
            username_snapshot="Camilo Real (Recepción)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error in assign_spot: {e}")

    return {
        "status": "success",
        "message": f"Cupo(s) asignados y confirmados con éxito para {name} ({payload.method}).",
        "slot_id": slot.id,
        "booked_spots": slot.booked_spots,
        "available_spots": max(0, slot.capacity - slot.booked_spots),
        "slot_status": slot.status.value if hasattr(slot.status, "value") else str(slot.status),
        "booking_reference": booking_ref,
    }


class MatchResultRequest(BaseModel):
    slot_id: Optional[int] = None
    winner_team: Optional[str] = None
    winner_names: Optional[List[str]] = None
    winner_phones: Optional[List[str]] = None
    points: int = 25


@router.post("/match-result", status_code=status.HTTP_200_OK)
@router.post("/{slot_id}/match-result", status_code=status.HTTP_200_OK)
async def record_slot_match_result(
    payload: MatchResultRequest,
    slot_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Registra el resultado de un partido y otorga +25 puntos de ranking a los ganadores.
    """
    from app.services.ranking_engine import award_match_points

    target_slot_id = slot_id or payload.slot_id
    slot = None
    if target_slot_id:
        stmt = select(TimeSlot).options(selectinload(TimeSlot.court)).where(TimeSlot.id == target_slot_id)
        res = await db.execute(stmt)
        slot = res.scalars().first()

    names = list(payload.winner_names or [])
    phones = list(payload.winner_phones or [])

    if not names and slot and slot.players_names:
        plist = to_participants_list(slot.players_names)
        w_team = (payload.winner_team or "pair1").lower()
        if "2" in w_team:
            team_players = plist[2:4] if len(plist) >= 4 else plist[1:]
        else:
            team_players = plist[:2]

        for p in team_players:
            p_name = p.get("display_name") or p.get("name")
            p_phone = p.get("phone")
            if p_name:
                names.append(p_name)
                if p_phone:
                    phones.append(p_phone)

    if not names:
        names = ["Pareja Ganadora"]

    winners = await award_match_points(
        db=db,
        winner_names=names,
        winner_phones=phones if phones else None,
        points=payload.points or 25,
    )

    if slot:
        slot.is_finished = True
        slot.winners_names = ", ".join(names)
        await db.commit()

    try:
        court_desc = slot.court.name if slot and slot.court else (f"Slot #{target_slot_id}" if target_slot_id else "Slot")
        await log_activity(
            db=db,
            action="MATCH_RESULT",
            entity_name="SLOT",
            entity_id=str(target_slot_id or 0),
            details=f"Victoria registrada en {court_desc}. Ganadores: {', '.join(names)} (+{payload.points or 25} Pts).",
            username_snapshot="Camilo Real (Recepción)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error in record_slot_match_result: {e}")

    return {
        "status": "success",
        "message": f"Victoria registrada exitosamente (+{payload.points or 25} Pts): {', '.join(names)}.",
        "winners": [
            {
                "id": w.id,
                "name": w.name,
                "phone": w.phone,
                "category": w.category,
                "ranking_points": w.ranking_points,
            }
            for w in winners
        ],
        "slot_id": target_slot_id,
    }


@router.post("/hold", response_model=SlotHoldResponse, status_code=status.HTTP_201_CREATED)
@router.post("/{slot_id}/hold", response_model=SlotHoldResponse, status_code=status.HTTP_201_CREATED)
async def create_slot_hold_alias(
    payload: SlotHoldCreate,
    slot_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Crea un hold temporal para un slot verificando estrictamente que no sea del pasado.
    """
    target_id = slot_id or payload.slot_id
    payload.slot_id = target_id

    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.holds))
        .where(TimeSlot.id == target_id)
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

    from app.api.v1.endpoints.holds import create_hold
    return await create_hold(payload=payload, db=db)


@router.post("/book", status_code=status.HTTP_200_OK)
@router.post("/{slot_id}/book", status_code=status.HTTP_200_OK)
async def book_slot_alias(
    payload: AssignSpotRequest,
    slot_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Reserva un slot verificando estrictamente que no sea del pasado.
    """
    target_id = slot_id or payload.slot_id
    payload.slot_id = target_id

    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.holds))
        .where(TimeSlot.id == target_id)
        .with_for_update()
    )
    result = await db.execute(stmt)
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El slot especificado no existe.",
        )
    validate_slot_not_past(slot)

    return await assign_spot(payload=payload, db=db)

