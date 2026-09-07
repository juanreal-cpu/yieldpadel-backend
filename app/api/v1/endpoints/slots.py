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
from app.services import calculate_recommended_price
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
    ReserveOrBlockRequest,
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

            existing_res = await db.execute(
                select(TimeSlot.start_time).where(TimeSlot.court_id == court.id, TimeSlot.date == d)
            )
            existing_times = set(existing_res.scalars().all())

            to_add = []
            for b_idx, (start_t, end_t) in enumerate(BLOCKS_90_MIN):
                if start_t in existing_times:
                    continue

                # Precio base dinámico según Yield Management
                is_pico = is_weekend or (start_t.hour >= 18)
                base_price = Decimal("120000.00") if is_pico else Decimal("80000.00")

                slot_mode = SlotMode.SPLIT_MATCH if (start_t.hour in (18, 19, 20) and court_num <= 3) else SlotMode.FULL_COURT
                slot_type = "MATCH"
                instructor_name = None
                category = "4ta"
                booked_spots = 0
                status_val = SlotStatus.AVAILABLE
                players = []

                # Muestras operativas para verificar academia y clases
                if court_num == 3 and start_t == time(16, 30) and day_idx in (0, 2, 4):
                    slot_type = "CLASS"
                    instructor_name = "Prof. Marcos Rivas"
                    category = "Academia Avanzada"
                    status_val = SlotStatus.FULLY_BOOKED
                    booked_spots = 4
                    players = [{
                        "spot_index": 1,
                        "phone": "+57-ACADEMY",
                        "display_name": "Clase con Marcos Rivas",
                        "client_tier": "MEMBER",
                        "host_phone": None
                    }]
                elif court_num == 5 and start_t == time(9, 0) and day_idx in (0, 1, 3):
                    slot_type = "ACADEMY"
                    instructor_name = "Prof. Valentina Gómez"
                    category = "Clase Infantil"
                    status_val = SlotStatus.FULLY_BOOKED
                    booked_spots = 4
                    players = [{
                        "spot_index": 1,
                        "phone": "+57-ACADEMY",
                        "display_name": "Academia Infantil",
                        "client_tier": "MEMBER",
                        "host_phone": None
                    }]
                elif court_num == 1 and start_t == time(18, 0) and day_idx == 0:
                    # Partido abierto en curso para pruebas de hoy
                    slot_mode = SlotMode.SPLIT_MATCH
                    status_val = SlotStatus.PARTIALLY_BOOKED
                    booked_spots = 3
                    players = [
                        {"spot_index": 1, "phone": "+573001112233", "display_name": "Juan Perez", "client_tier": "STANDARD", "host_phone": None},
                        {"spot_index": 2, "phone": "+573002223344", "display_name": "Carlos Gomez", "client_tier": "STANDARD", "host_phone": None},
                        {"spot_index": 3, "phone": "+573003334455", "display_name": "Mateo Silva", "client_tier": "VIP_PAY_ON_SITE", "host_phone": None},
                    ]

                to_add.append(
                    TimeSlot(
                        court_id=court.id,
                        date=d,
                        start_time=start_t,
                        end_time=end_t,
                        total_price=base_price,
                        mode=slot_mode,
                        capacity=4,
                        booked_spots=booked_spots,
                        category=category,
                        players_names=players,
                        status=status_val,
                        slot_type=slot_type,
                        instructor_name=instructor_name,
                        is_promo=False,
                    )
                )

            if to_add:
                db.add_all(to_add)
                total_created += len(to_add)

    if total_created > 0:
        await db.commit()
        return {
            "message": f"Se sembraron {total_created} turnos de 90 min exitosamente para los próximos 7 días en las 5 canchas",
            "courts_count": len(courts),
            "days_count": len(dates_to_seed),
            "slots_created": total_created,
        }

    return {
        "message": "Los 7 días de turnos de 90 minutos ya se encontraban presentes para todas las canchas",
        "courts_count": len(courts),
        "days_count": len(dates_to_seed),
        "slots_created": 0,
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

    stype = (payload.slot_type or "MATCH").upper()
    slot.slot_type = stype

    if payload.instructor_name:
        slot.instructor_name = payload.instructor_name

    if payload.mode:
        slot.mode = payload.mode

    # Asignar precio personalizado o recomendado por Yield
    if payload.custom_price is not None and payload.custom_price > 0:
        slot.total_price = payload.custom_price
    else:
        yield_data = calculate_recommended_price(slot)
        slot.total_price = yield_data["recommended_price"]

    # Procesar según tipo de turno
    if stype == "MAINTENANCE":
        slot.status = SlotStatus.BLOCKED
        slot.booked_spots = slot.capacity
        slot.players_names = [{"spot_index": 1, "phone": "+57-MANT", "display_name": "Mantenimiento", "client_tier": "VIP_PAY_ON_SITE", "host_phone": None}]
    elif stype in ("CLASS", "ACADEMY"):
        slot.status = SlotStatus.FULLY_BOOKED
        slot.booked_spots = slot.capacity
        prof_title = payload.instructor_name or "Profesor Asignado"
        student_label = payload.client_name or f"Clase con {prof_title}"
        slot.players_names = [{
            "spot_index": 1,
            "phone": payload.client_phone or "+57-ACADEMY",
            "display_name": student_label,
            "client_tier": "MEMBER",
            "host_phone": None
        }]
    elif payload.client_name:
        slot.status = SlotStatus.FULLY_BOOKED
        slot.booked_spots = slot.capacity
        slot.players_names = [{
            "spot_index": 1,
            "phone": payload.client_phone or "+57-RECEPCION",
            "display_name": payload.client_name,
            "client_tier": "VIP_PAY_ON_SITE",
            "host_phone": None
        }]
    else:
        # Solo actualización de tarifa recomendada
        slot.status = SlotStatus.AVAILABLE
        slot.booked_spots = 0
        slot.players_names = []

    await db.commit()
    await db.refresh(slot)

    now_utc = datetime.now(timezone.utc)
    return compute_slot_response(slot, now_utc)


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