from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.timezone import get_bogota_now, get_bogota_today
from app.models.court import Court
from app.models.slot import HoldStatus, SlotMode, SlotStatus, TimeSlot, SlotHold
from app.schemas.slot import (
    CourtResponse,
    DropPlayerRequest,
    DropPlayerResponse,
    SlotParticipant,
    TimeSlotResponse,
    WhatsAppConvocatoriaRequest,
    WhatsAppConvocatoriaResponse,
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
            }
        else:
            name = str(item).strip()
            p = {
                "spot_index": i,
                "phone": f"+57-WA-{name.lower().replace(' ', '')}",
                "display_name": name,
                "client_tier": "STANDARD",
                "host_phone": None,
            }
        result.append(p)
    return result


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

    price_per_spot = (slot.total_price / Decimal(slot.capacity)).quantize(Decimal("0.01"))

    participants_raw = to_participants_list(slot.players_names)
    participants_objs = [SlotParticipant(**p) for p in participants_raw]
    display_names = [p.display_name for p in participants_objs]

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
    )


@router.get("/", response_model=List[TimeSlotResponse])
async def list_slots(
    slot_date: Optional[date] = Query(None, alias="date", description="Filtrar por fecha"),
    mode: Optional[SlotMode] = Query(None, description="Filtrar por modo FULL_COURT o SPLIT_MATCH"),
    only_available: bool = Query(True, description="Mostrar únicamente slots con cupos disponibles"),
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
    """Garantiza la existencia y numeración de las 5 canchas estándar del club."""
    import uuid
    res = await db.execute(select(Court).where(Court.is_active == True))
    courts = list(res.scalars().all())

    court_map = {c.name: c for c in courts}
    num_map = {c.court_number: c for c in courts if getattr(c, "court_number", None) is not None}

    sample_club_id = None
    for c in courts:
        if getattr(c, "club_id", None):
            sample_club_id = c.club_id
            break
    if not sample_club_id:
        sample_club_id = uuid.uuid4()

    court_definitions = [
        (1, "Cancha Central 1"),
        (2, "Cancha 2"),
        (3, "Cancha 3"),
        (4, "Cancha 4"),
        (5, "Cancha 5"),
    ]

    changed = False
    for num, name in court_definitions:
        existing = num_map.get(num) or court_map.get(name)
        if existing:
            if existing.name != name:
                existing.name = name
                changed = True
            if getattr(existing, "court_number", None) != num:
                existing.court_number = num
                changed = True
        else:
            new_court = Court(
                id=uuid.uuid4(),
                club_id=sample_club_id,
                court_number=num,
                name=name,
                is_active=True,
            )
            db.add(new_court)
            changed = True

    if changed:
        await db.commit()
        res = await db.execute(select(Court).where(Court.is_active == True))
        courts = list(res.scalars().all())

    courts.sort(key=lambda c: (getattr(c, "court_number", None) or 99, c.name))
    return courts


@router.get("/courts", response_model=List[CourtResponse])
async def get_courts(db: AsyncSession = Depends(get_db)):
    """Obtiene el listado ordenado de las 5 canchas activas del club."""
    courts = await ensure_five_courts(db)
    return courts


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_demo_data(
    target_date: Optional[date] = Query(None, alias="date", description="Fecha específica para sembrar turnos demo"),
    db: AsyncSession = Depends(get_db),
):
    """
    Siembra turnos de demostración para las 5 canchas con duraciones de 1h, 1.5h y 2h,
    cubriendo franjas de 06:00 a 23:00 con estados variados:
    - Azul / Esmeralda: Pagado / Cerrado (4/4)
    - Amarillo / Ámbar: Partido Abierto (1/4 a 3/4)
    - Morado: Americano / Torneo
    - Gris suave: Disponible / Libre
    """
    courts = await ensure_five_courts(db)
    today = get_bogota_today()
    dates_to_seed = [target_date] if target_date else [today - timedelta(days=1), today, today + timedelta(days=1)]

    # Plantillas de turnos por número de cancha con duraciones de 1h, 1.5h y 2h
    court_templates = {
        1: [  # Cancha Central 1
            {"start": time(6, 0), "end": time(7, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("80000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(7, 0), "end": time(8, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("120000.00"), "booked": 4, "cat": "3ra", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(8, 30), "end": time(10, 0), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("100000.00"), "booked": 3, "cat": "4ta", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573001112233", "display_name": "Juan Perez", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573002223344", "display_name": "Carlos Gomez", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 3, "phone": "+573003334455", "display_name": "Mateo Silva", "client_tier": "VIP_PAY_ON_SITE", "host_phone": None},
            ]},
            {"start": time(10, 0), "end": time(12, 0), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("160000.00"), "booked": 4, "cat": "Americano", "status": SlotStatus.FULLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573101111111", "display_name": "Felipe R", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573102222222", "display_name": "David M", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 3, "phone": "+573103333333", "display_name": "Santiago T", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 4, "phone": "+573104444444", "display_name": "Lucas B", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(12, 0), "end": time(13, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("70000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(14, 0), "end": time(15, 30), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("112000.00"), "booked": 2, "cat": "3ra", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573151112233", "display_name": "Andres B", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573152223344", "display_name": "Diego V", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(16, 0), "end": time(18, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("160000.00"), "booked": 4, "cat": "Open", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(18, 0), "end": time(19, 30), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("140000.00"), "booked": 4, "cat": "2da", "status": SlotStatus.FULLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573161111111", "display_name": "Camila S", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573162222222", "display_name": "Paula G", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 3, "phone": "+573163333333", "display_name": "Mariana O", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 4, "phone": "+573164444444", "display_name": "Valentina C", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(20, 0), "end": time(22, 0), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("180000.00"), "booked": 4, "cat": "Torneo Nocturno", "status": SlotStatus.FULLY_BOOKED, "players": []},
        ],
        2: [  # Cancha 2
            {"start": time(6, 30), "end": time(8, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("90000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(8, 0), "end": time(9, 0), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("80000.00"), "booked": 1, "cat": "5ta", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573181112233", "display_name": "Esteban R", "client_tier": "STANDARD", "host_phone": None}
            ]},
            {"start": time(9, 30), "end": time(11, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("150000.00"), "booked": 4, "cat": "3ra", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(11, 30), "end": time(12, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("70000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(14, 0), "end": time(16, 0), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("140000.00"), "booked": 3, "cat": "Americano Express", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573171112233", "display_name": "Pablo M", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573172223344", "display_name": "Tomas K", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 3, "phone": "+573173334455", "display_name": "Nicolas D", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(16, 30), "end": time(18, 0), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("110000.00"), "booked": 2, "cat": "4ta", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573121112233", "display_name": "German L", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573122223344", "display_name": "Oscar P", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(18, 30), "end": time(20, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("140000.00"), "booked": 4, "cat": "3ra", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(20, 0), "end": time(21, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("100000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
        ],
        3: [  # Cancha 3
            {"start": time(7, 0), "end": time(8, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("75000.00"), "booked": 0, "cat": "5ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(8, 0), "end": time(10, 0), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("150000.00"), "booked": 4, "cat": "Americano Femenino", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(10, 30), "end": time(12, 0), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("112000.00"), "booked": 3, "cat": "3ra", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573111112233", "display_name": "Alvaro H", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573112223344", "display_name": "Jorge E", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 3, "phone": "+573113334455", "display_name": "Mauricio C", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(13, 0), "end": time(14, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("60000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(14, 30), "end": time(16, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("120000.00"), "booked": 4, "cat": "4ta", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(16, 30), "end": time(18, 30), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("130000.00"), "booked": 2, "cat": "4ta", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573191112233", "display_name": "Cristian V", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573192223344", "display_name": "Hernan T", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(19, 0), "end": time(20, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("140000.00"), "booked": 4, "cat": "3ra", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(21, 0), "end": time(22, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("80000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
        ],
        4: [  # Cancha 4
            {"start": time(6, 0), "end": time(7, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("80000.00"), "booked": 0, "cat": "5ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(8, 0), "end": time(9, 30), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("100000.00"), "booked": 2, "cat": "4ta", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573211112233", "display_name": "Sergio N", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573212223344", "display_name": "Daniel J", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(10, 0), "end": time(11, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("70000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(11, 30), "end": time(13, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("150000.00"), "booked": 4, "cat": "3ra", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(14, 0), "end": time(15, 30), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("112000.00"), "booked": 1, "cat": "3ra", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573221112233", "display_name": "Jaime B", "client_tier": "STANDARD", "host_phone": None}
            ]},
            {"start": time(16, 0), "end": time(17, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("80000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(17, 30), "end": time(19, 30), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("160000.00"), "booked": 4, "cat": "Torneo Mixto", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(20, 0), "end": time(21, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("130000.00"), "booked": 4, "cat": "2da", "status": SlotStatus.FULLY_BOOKED, "players": []},
        ],
        5: [  # Cancha 5
            {"start": time(7, 0), "end": time(8, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("110000.00"), "booked": 4, "cat": "4ta", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(9, 0), "end": time(10, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("70000.00"), "booked": 0, "cat": "5ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(10, 30), "end": time(12, 30), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("130000.00"), "booked": 3, "cat": "Americano Iniciación", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573231112233", "display_name": "Luis F", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573232223344", "display_name": "Mario Z", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 3, "phone": "+573233334455", "display_name": "Guillermo R", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(13, 0), "end": time(14, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("60000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
            {"start": time(14, 30), "end": time(16, 0), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("110000.00"), "booked": 2, "cat": "4ta", "status": SlotStatus.PARTIALLY_BOOKED, "players": [
                {"spot_index": 1, "phone": "+573241112233", "display_name": "Rodrigo A", "client_tier": "STANDARD", "host_phone": None},
                {"spot_index": 2, "phone": "+573242223344", "display_name": "Samuel Q", "client_tier": "STANDARD", "host_phone": None},
            ]},
            {"start": time(16, 30), "end": time(18, 0), "mode": SlotMode.FULL_COURT, "price": Decimal("120000.00"), "booked": 4, "cat": "3ra", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(18, 30), "end": time(20, 30), "mode": SlotMode.SPLIT_MATCH, "price": Decimal("150000.00"), "booked": 4, "cat": "3ra", "status": SlotStatus.FULLY_BOOKED, "players": []},
            {"start": time(21, 0), "end": time(22, 30), "mode": SlotMode.FULL_COURT, "price": Decimal("90000.00"), "booked": 0, "cat": "4ta", "status": SlotStatus.AVAILABLE, "players": []},
        ],
    }

    total_created = 0
    for d in dates_to_seed:
        is_past = d < today
        for idx, court in enumerate(courts, start=1):
            court_num = getattr(court, "court_number", None) or idx
            templates = court_templates.get(court_num, court_templates[1])

            existing_res = await db.execute(
                select(TimeSlot.start_time).where(TimeSlot.court_id == court.id, TimeSlot.date == d)
            )
            existing_times = set(existing_res.scalars().all())

            to_add = []
            for tpl in templates:
                if tpl["start"] in existing_times:
                    continue
                slot_booked = 4 if is_past else tpl["booked"]
                slot_status = SlotStatus.FULLY_BOOKED if (is_past or slot_booked >= 4) else (
                    SlotStatus.PARTIALLY_BOOKED if slot_booked > 0 else SlotStatus.AVAILABLE
                )
                players = [] if is_past else tpl["players"]

                to_add.append(
                    TimeSlot(
                        court_id=court.id,
                        date=d,
                        start_time=tpl["start"],
                        end_time=tpl["end"],
                        total_price=tpl["price"],
                        mode=tpl["mode"],
                        capacity=4,
                        booked_spots=slot_booked,
                        category=tpl["cat"],
                        players_names=players,
                        status=slot_status,
                    )
                )

            if to_add:
                db.add_all(to_add)
                total_created += len(to_add)

    if total_created > 0:
        await db.commit()
        return {
            "message": f"Se sembraron {total_created} turnos demo exitosamente en las 5 canchas",
            "courts_count": len(courts),
            "slots_created": total_created,
        }

    return {"message": "Los datos de demostración ya se encontraban presentes para todas las canchas", "courts_count": len(courts), "slots_created": 0}


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
    """Parsea una convocatoria de WhatsApp, sincroniza el TimeSlot y devuelve el mensaje de confirmación."""
    raw = payload.raw_text

    # 1. Parsear fecha
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

    # 2. Parsear horario
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

    # 3. Parsear categoría
    cat_match = re.search(r"(?:Categor[íi]a|Cat\.?):\s*([^\n\r]+)", raw, re.IGNORECASE)
    category = cat_match.group(1).strip() if cat_match else "4ta"

    # 4. Parsear precio (buscar indicador de dinero 💰, $, COP, precio o valor)
    price_match = re.search(
        r"(?:💰|\$|COP|valor|precio)\s*:?\s*(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+)",
        raw,
        re.IGNORECASE,
    )
    if price_match:
        price_clean = price_match.group(1).replace(".", "").replace(",", ".")
        price_per_spot = Decimal(price_clean)
    else:
        price_per_spot = Decimal("15000.00")

    # 5. Parsear jugadores (flexible: 🎾, otros emojis, números, guiones o texto)
    from app.services.whatsapp import parse_flexible_player_list
    raw_players = parse_flexible_player_list(raw)
    spots_count = len(raw_players)
    free_spots = max(0, 4 - spots_count)
    is_closed = (spots_count == 4)

    # 6. Validación estricta de inventario en WhatsApp (Anti-overbooking)
    start_str = start_t.strftime("%I:%M%p").lower()
    end_str = end_t.strftime("%I:%M%p").lower()
    date_formatted = target_date.strftime("%d/%m/%Y")
    price_formatted = f"{int(price_per_spot):,}".replace(",", ".")

    # Buscar slots existentes para esta fecha y franja horaria
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

    # a) Si no existe ningún turno programado para la fecha y hora:
    if not matching_slots:
        warning_reply = (
            f"⚠️ *TURNO NO ENCONTRADO EN SISTEMA* ⚠️\n"
            f"📍 Capital Pádel Club\n"
            f"📅 {date_formatted} | ⌚ {start_str} - {end_str}\n\n"
            f"No existe un turno habilitado en la programación del club para este horario.\n"
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
            free_spots=free_spots,
            is_closed=False,
            slot_id=None,
            whatsapp_reply=warning_reply,
        )

    # b) Filtrar slots que admitan convocatoria (no bloqueados y en modo SPLIT_MATCH o status AVAILABLE)
    eligible_slots = [
        s for s in matching_slots
        if s.status != SlotStatus.BLOCKED and (s.mode == SlotMode.SPLIT_MATCH or s.status == SlotStatus.AVAILABLE)
    ]

    if not eligible_slots:
        warning_reply = (
            f"⚠️ *TURNO NO DISPONIBLE PARA CONVOCATORIA* ⚠️\n"
            f"📍 Capital Pádel Club\n"
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
            free_spots=free_spots,
            is_closed=False,
            slot_id=None,
            whatsapp_reply=warning_reply,
        )

    # Seleccionar el slot preferente (el que ya es SPLIT_MATCH o el primero AVAILABLE)
    slot = next((s for s in eligible_slots if s.mode == SlotMode.SPLIT_MATCH), eligible_slots[0])

    prev_participants = to_participants_list(slot.players_names) if slot else []
    prev_by_name = {p["display_name"].strip().lower(): p for p in prev_participants}
    prev_names_set = set(prev_by_name.keys())
    incoming_names_set = set(p.strip().lower() for p in raw_players)

    # Inmutabilidad: Precio oficial por cupo y sede extraídos directamente del inventario en BD
    official_price_per_spot = (slot.total_price / Decimal(slot.capacity)).quantize(Decimal("0.01"))
    court_name = slot.court.name if slot.court else "Capital Pádel Club"

    # c) Anti-overbooking: si el slot ya está lleno (4/4) y la convocatoria entrante intenta sobrecupar o registrar otro grupo
    if slot.booked_spots >= 4 and slot.status == SlotStatus.FULLY_BOOKED:
        if spots_count >= 4 and incoming_names_set != prev_names_set:
            warning_reply = (
                f"⚠️ *TURNO COMPLETO SIN CUPOS DISPONIBLES* ⚠️\n"
                f"📍 {court_name}\n"
                f"📅 {date_formatted} | ⌚ {start_str} - {end_str}\n\n"
                f"Este turno ya completó sus 4 cupos y se encuentra cerrado.\n"
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
                spots_count=4,
                free_spots=0,
                is_closed=True,
                slot_id=slot.id,
                whatsapp_reply=warning_reply,
            )

    # Estructurar participantes canónicos
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

        participants.append({
            "spot_index": i,
            "phone": phone,
            "display_name": p_name,
            "client_tier": tier,
            "host_phone": h_phone,
        })

    slot_status = SlotStatus.FULLY_BOOKED if is_closed else (
        SlotStatus.PARTIALLY_BOOKED if spots_count > 0 else SlotStatus.AVAILABLE
    )

    slot.mode = SlotMode.SPLIT_MATCH
    slot.players_names = participants
    slot.booked_spots = spots_count
    slot.category = category
    # Inmutabilidad: slot.total_price NO se sobreescribe con datos del usuario
    slot.status = slot_status

    if is_closed:
        if not slot.closed_at:
            slot.closed_at = datetime.now(timezone.utc)
    else:
        slot.closed_at = None

    await db.commit()
    await db.refresh(slot)

    # 7. Generar mensaje de respuesta para el grupo de WhatsApp con atributos inmutables
    start_str = slot.start_time.strftime("%I:%M%p").lower()
    end_str = slot.end_time.strftime("%I:%M%p").lower()
    date_formatted = slot.date.strftime("%d/%m/%Y")
    price_formatted = f"{int(official_price_per_spot):,}".replace(",", ".")

    if is_closed:
        players_list = "\n".join([f"{i+1}. 🎾 {p}" for i, p in enumerate(raw_players)])
        reply = (
            f"✅ ¡PARTIDO CERRADO Y CONFIRMADO! (4/4) 🎾\n"
            f"📍 {court_name}\n"
            f"📅 {date_formatted} | ⌚ {start_str} - {end_str}\n"
            f"🏆 Categoría: {category}\n"
            f"💰 Cuota: ${price_formatted} COP / jugador\n\n"
            f"👥 *Jugadores Confirmados (4/4):*\n{players_list}\n\n"
            f"🔒 *Cancha asegurada en sistema. ¡Nos vemos en la pista!*"
        )
    else:
        slot_lines = []
        for i in range(1, 5):
            if i <= spots_count:
                slot_lines.append(f"{i}. 🎾 {raw_players[i - 1]}")
            else:
                slot_lines.append(f"{i}. ⚡ [CUPO DISPONIBLE]")
        players_list = "\n".join(slot_lines)

        reply = (
            f"🎾 PARTIDO ABIERTO ({spots_count}/4)\n"
            f"📍 {court_name}\n"
            f"📅 {date_formatted} | ⌚ {start_str} - {end_str}\n"
            f"🏆 Categoría: {category}\n"
            f"💰 Cuota: ${price_formatted} COP / jugador\n\n"
            f"👥 *Inscritos ({spots_count}/4):*\n{players_list}\n\n"
            f"⚡ *¡Quedan {free_spots} cupo(s) disponible(s)! Aparta tu cupo directamente respondiendo a esta lista.*"
        )

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