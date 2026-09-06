from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
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


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_demo_data(
    target_date: Optional[date] = Query(None, alias="date", description="Fecha específica para sembrar turnos demo"),
    db: AsyncSession = Depends(get_db),
):
    """Crea una cancha demo y turnos de prueba (ayer, hoy, mañana o fecha especificada) si no existen."""
    court_stmt = select(Court).where(Court.is_active == True)
    court_res = await db.execute(court_stmt)
    court = court_res.scalars().first()

    if not court:
        court = Court(name="Cancha Central 1", is_active=True)
        db.add(court)
        await db.flush()

    today = date.today()
    dates_to_seed = [target_date] if target_date else [today - timedelta(days=1), today, today + timedelta(days=1)]

    total_created = 0
    for d in dates_to_seed:
        existing_res = await db.execute(
            select(TimeSlot.start_time).where(TimeSlot.court_id == court.id, TimeSlot.date == d)
        )
        existing_times = set(existing_res.scalars().all())
        is_past = d < today
        day_slots = [
            TimeSlot(
                court_id=court.id,
                date=d,
                start_time=time(8, 0),
                end_time=time(9, 30),
                total_price=Decimal("120000.00"),
                mode=SlotMode.FULL_COURT,
                capacity=4,
                booked_spots=4 if is_past else 0,
                status=SlotStatus.FULLY_BOOKED if is_past else SlotStatus.AVAILABLE,
            ),
            TimeSlot(
                court_id=court.id,
                date=d,
                start_time=time(10, 0),
                end_time=time(11, 30),
                total_price=Decimal("60000.00"),
                mode=SlotMode.SPLIT_MATCH,
                capacity=4,
                booked_spots=4 if is_past else 0,
                category="4ta",
                status=SlotStatus.FULLY_BOOKED if is_past else SlotStatus.AVAILABLE,
            ),
            TimeSlot(
                court_id=court.id,
                date=d,
                start_time=time(14, 0),
                end_time=time(15, 30),
                total_price=Decimal("60000.00"),
                mode=SlotMode.SPLIT_MATCH,
                capacity=4,
                booked_spots=4 if is_past else 0,
                category="4ta",
                status=SlotStatus.FULLY_BOOKED if is_past else SlotStatus.AVAILABLE,
            ),
            TimeSlot(
                court_id=court.id,
                date=d,
                start_time=time(16, 0),
                end_time=time(17, 30),
                total_price=Decimal("72000.00"),
                mode=SlotMode.SPLIT_MATCH,
                capacity=4,
                booked_spots=4 if is_past else 1,
                category="4ta",
                players_names=[{"spot_index": 1, "phone": "+573001234567", "display_name": "Andres B", "client_tier": "STANDARD", "host_phone": None}] if not is_past else [],
                status=SlotStatus.FULLY_BOOKED if is_past else SlotStatus.PARTIALLY_BOOKED,
            ),
            TimeSlot(
                court_id=court.id,
                date=d,
                start_time=time(18, 0),
                end_time=time(19, 30),
                total_price=Decimal("140000.00"),
                mode=SlotMode.FULL_COURT,
                capacity=4,
                booked_spots=0,
                status=SlotStatus.AVAILABLE,
            ),
            TimeSlot(
                court_id=court.id,
                date=d,
                start_time=time(20, 0),
                end_time=time(21, 30),
                total_price=Decimal("80000.00"),
                mode=SlotMode.SPLIT_MATCH,
                capacity=4,
                booked_spots=0,
                category="3ra",
                status=SlotStatus.AVAILABLE,
            ),
        ]
        to_add = [s for s in day_slots if s.start_time not in existing_times]
        if to_add:
            db.add_all(to_add)
            total_created += len(to_add)

    if total_created > 0:
        await db.commit()
        return {
            "message": f"Se sembraron {total_created} turnos demo correctamente",
            "court_id": str(court.id),
            "slots_created": total_created,
        }

    return {"message": "Los datos de demostración ya se encontraban presentes", "court_id": str(court.id)}


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
    Limpia números, viñetas, guiones, emojis de cupos o corchetes y valida
    estrictamente que el nombre de jugador sea válido y no un texto del sistema o cupo libre.
    """
    if not raw_name:
        return None
    # Eliminar índices numéricos iniciales, viñetas, guiones, emojis como ⚡ y corchetes
    cleaned = re.sub(r"^[\d\.\-\)\:\s\[\]⚡\*\#\+]+", "", raw_name).strip()
    cleaned = re.sub(r"[\[\]\*\#]+$", "", cleaned).strip()

    if len(cleaned) < 2:
        return None

    cleaned_upper = cleaned.upper()
    for pattern in DISCARD_PLAYER_PATTERNS:
        if pattern in cleaned_upper:
            return None

    if not any(c.isalnum() for c in cleaned):
        return None

    return cleaned


@router.post("/parse-open-match", response_model=WhatsAppConvocatoriaResponse, status_code=status.HTTP_200_OK)
async def parse_open_match(
    payload: WhatsAppConvocatoriaRequest,
    db: AsyncSession = Depends(get_db),
):
    """Parsea una convocatoria de WhatsApp, sincroniza el TimeSlot y devuelve el mensaje de confirmación."""
    raw = payload.raw_text

    # 1. Parsear fecha
    target_date = date.today()
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

    # 5. Parsear jugadores (líneas con 🎾)
    raw_players = []
    for line in raw.splitlines():
        if "🎾" in line:
            candidate = line.split("🎾", 1)[1].strip()
            valid_name = clean_and_validate_player_name(candidate)
            if valid_name:
                raw_players.append(valid_name)

    # Limitar a la capacidad estándar de pádel (4 jugadores)
    raw_players = raw_players[:4]
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

    # c) Anti-overbooking: si el slot ya está lleno (4/4) y la convocatoria entrante intenta sobrecupar o registrar otro grupo
    if slot.booked_spots >= 4 and slot.status == SlotStatus.FULLY_BOOKED:
        if spots_count >= 4 and incoming_names_set != prev_names_set:
            warning_reply = (
                f"⚠️ *TURNO COMPLETO SIN CUPOS DISPONIBLES* ⚠️\n"
                f"📍 Capital Pádel Club\n"
                f"📅 {date_formatted} | ⌚ {start_str} - {end_str}\n\n"
                f"Este turno ya completó sus 4 cupos y se encuentra cerrado.\n"
                f"No hay cupos disponibles para esta franja horaria."
            )
            return WhatsAppConvocatoriaResponse(
                date=str(target_date),
                start_time=str(start_t),
                end_time=str(end_t),
                category=category,
                price_per_spot=price_per_spot,
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
    slot.total_price = price_per_spot * Decimal(4)
    slot.status = slot_status

    await db.commit()
    await db.refresh(slot)

    # 7. Generar mensaje de respuesta para el grupo de WhatsApp
    start_str = start_t.strftime("%I:%M%p").lower()
    end_str = end_t.strftime("%I:%M%p").lower()
    date_formatted = target_date.strftime("%d/%m/%Y")
    price_formatted = f"{int(price_per_spot):,}".replace(",", ".")

    if is_closed:
        players_list = "\n".join([f"{i+1}. 🎾 {p}" for i, p in enumerate(raw_players)])
        reply = (
            f"✅ ¡PARTIDO CERRADO Y CONFIRMADO! (4/4) 🎾\n"
            f"📍 Capital Pádel Club\n"
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
            f"📍 Capital Pádel Club\n"
            f"📅 {date_formatted} | ⌚ {start_str} - {end_str}\n"
            f"🏆 Categoría: {category}\n"
            f"💰 Cuota: ${price_formatted} COP / jugador\n\n"
            f"👥 *Inscritos ({spots_count}/4):*\n{players_list}\n\n"
            f"⚡ *¡Quedan {free_spots} cupo(s) disponible(s)! Aparta tu cupo directamente respondiendo a esta lista.*"
        )

    return WhatsAppConvocatoriaResponse(
        date=str(target_date),
        start_time=str(start_t),
        end_time=str(end_t),
        category=category,
        price_per_spot=price_per_spot,
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