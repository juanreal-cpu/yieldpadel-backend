"""
YieldPadel - Servicio de WhatsApp
Maneja dinámicas de grupo, reconocimiento de comandos por intención ('voy', 'me bajo'),
control estricto de mutabilidad de atributos del inventario (fecha, horarios, precio y cancha)
y detección flexible de jugadores en listas.
"""

import logging
import os
import re
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.court import Court
from app.models.slot import ClientTier, SlotMode, SlotStatus, TimeSlot

logger = logging.getLogger("yieldpadel.whatsapp")

# -----------------------------------------------------------------------------
# Expresiones regulares para reconocimiento de intenciones
# -----------------------------------------------------------------------------

# Intención de entrada (Join)
JOIN_KEYWORDS = [
    r"\b(?:yo\s+)?voy\b",
    r"\b(?:yo\s+)?entro\b",
    r"\b(?:yo\s+)?juego\b",
    r"\bme\s+anoto\b",
    r"\ban[oó]tenme\b",
    r"\ban[oó]tame\b",
    r"\bme\s+apunto\b",
    r"\bap[uú]ntame\b",
    r"\bcuenten\s+conmigo\b",
    r"\bme\s+sumo\b",
]
JOIN_REGEX = re.compile("|".join(JOIN_KEYWORDS), re.IGNORECASE)

# Intención de salida (Drop)
DROP_KEYWORDS = [
    r"\bme\s+bajo\b",
    r"\bno\s+voy\b",
    r"\bme\s+salgo\b",
    r"\bcancelo\b",
    r"\bcancelar\b",
    r"\bno\s+juego\b",
    r"\bno\s+puedo(?:\s+ir)?\b",
    r"\bb[aá]jenme\b",
    r"\bbajenme\b",
    r"\bme\s+desanoto\b",
    r"\bme\s+quito\b",
    r"\bno\s+alcanzo\b",
]
DROP_REGEX = re.compile("|".join(DROP_KEYWORDS), re.IGNORECASE)

# Patrones descartables para nombres de jugadores (textos del sistema)
DISCARD_PATTERNS = [
    "CUPO DISPONIBLE",
    "CUPO LIBRE",
    "DISPONIBLE",
    "LIBRE",
    "VACANTE",
    "POR DEFINIR",
    "CANCELADO",
    "BAJA",
    "RESERVADO",
    "INSCRIBETE",
    "INSCRÍBETE",
    "PARTIDO CERRADO",
    "PARTIDO ABIERTO",
    "CAPITAL PADEL",
    "CAPITAL PÁDEL",
    "BOGOTA PADEL",
    "BOGOTÁ PÁDEL",
    "CATEGORIA",
    "CATEGORÍA",
    "CUOTA",
    "PRECIO",
    "VALOR",
]

# Líneas de metadatos del club a ignorar al parsear listas
METADATA_LINE_PATTERNS = [
    r"^(?:hoy|mañana|ayer|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\b",
    r"\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
    r"^\s*(?:categor[íi]a|cat\.?)\s*:",
    r"^\s*⌚",
    r"^\s*(?:horario|hora)\s*:",
    r"^\s*📍",
    r"^\s*(?:sede|cancha|club|lugar)\s*:",
    r"^\s*💰",
    r"^\s*(?:precio|cuota|valor|costo)\s*:",
    r"^\s*👥\s*\*?(?:inscritos|jugadores|confirmados)",
    r"^\s*(?:inscritos|jugadores|confirmados)\s*:",
    r"^\s*⚡\s*\*?¡?quedan\b",
    r"^\s*🔒\s*\*?cancha asegurada\b",
    r"^\s*✅\s*\*?¡?partido cerrado\b",
    r"^\s*🎾\s*\*?partido abierto\b",
    r"^\s*[\-\=\*\_]{3,}\s*$",
]
METADATA_REGEX = re.compile("|".join(METADATA_LINE_PATTERNS), re.IGNORECASE)


def normalize_phone(phone: Optional[str]) -> str:
    """Estandariza números de teléfono al formato canónico +57..."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) == 10 and digits.startswith("3"):
        return "+57" + digits
    elif len(digits) == 12 and digits.startswith("573"):
        return "+" + digits
    elif str(phone).startswith("+"):
        return "+" + digits
    return digits


def detect_intent(text: str) -> str:
    """
    Clasifica el mensaje entrante en una de las intenciones soportadas:
    - 'DROP': Intención de salida ('me bajo', 'no voy', 'cancelo')
    - 'JOIN': Intención de entrada ('voy', 'entro', 'juego', 'me anoto')
    - 'LIST': Lista de convocatoria (múltiples jugadores o formato completo)
    - 'UNKNOWN': Otro texto
    """
    clean = text.strip()
    # 1. Comprobar salida (DROP) primero para evitar falsos positivos con 'no voy'
    if DROP_REGEX.search(clean):
        return "DROP"

    # 2. Comprobar entrada (JOIN)
    if JOIN_REGEX.search(clean):
        return "JOIN"

    # 3. Comprobar si parece una lista o convocatoria
    if "🎾" in clean or ("1." in clean and "2." in clean) or ("cancha" in clean.lower() and "4ta" in clean.lower()):
        return "LIST"

    return "UNKNOWN"


def clean_player_name(raw_name: str) -> Optional[str]:
    """
    Limpia y valida un nombre de jugador.
    Remueve emojis, viñetas, índices numéricos y valida que no sea un texto de sistema.
    """
    if not raw_name:
        return None

    # Remover viñetas, números iniciales (ej: 1., 2), 3 -), emojis y corchetes
    cleaned = re.sub(r"^[\d\.\-\)\:\s\[\]⚡\*\#\+🎾🏓🏸👤🔥✅]+", "", raw_name).strip()
    cleaned = re.sub(r"[\[\]\*\#\s🎾🏓🏸👤🔥⚡]+$", "", cleaned).strip()

    if len(cleaned) < 2:
        return None

    cleaned_upper = cleaned.upper()
    for pat in DISCARD_PATTERNS:
        if pat in cleaned_upper:
            return None

    if not any(c.isalnum() for c in cleaned):
        return None

    return cleaned


def parse_flexible_player_list(raw_text: str) -> List[str]:
    """
    Detección flexible de nombres en listas:
    Reconoce jugadores tanto si usan 🎾 como cualquier otro emoji, número, guión o texto,
    siempre y cuando sea un nombre real distinto a '[CUPO DISPONIBLE]' o líneas de metadatos.
    """
    players: List[str] = []
    lines = raw_text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Descartar líneas que coincidan con metadatos del club
        if METADATA_REGEX.search(stripped):
            continue

        # Candidato: extraer jugador tras 🎾 si existe, o evaluar la línea completa
        if "🎾" in stripped:
            candidate = stripped.split("🎾", 1)[1].strip()
        elif "🏓" in stripped:
            candidate = stripped.split("🏓", 1)[1].strip()
        elif "👤" in stripped:
            candidate = stripped.split("👤", 1)[1].strip()
        else:
            candidate = stripped

        valid_name = clean_player_name(candidate)
        if valid_name and valid_name not in players:
            players.append(valid_name)
            if len(players) == 4:
                break

    return players


def extract_player_name_from_join(text: str, default_name: Optional[str] = None) -> str:
    """
    Extrae un apodo o nombre explícito proporcionado en el mensaje de entrada.
    Ejemplos:
    - 'voy - Carlos' -> 'Carlos'
    - 'entro (Pipe)' -> 'Pipe'
    - 'me anoto: Mateo Gomez' -> 'Mateo Gomez'
    - 'anotenme a Pedro' -> 'Pedro'
    - 'voy' -> default_name o 'Jugador'
    """
    # Buscar patrones con paréntesis: entro (Pipe)
    paren_match = re.search(r"\(([^)]+)\)", text)
    if paren_match:
        cand = clean_player_name(paren_match.group(1))
        if cand:
            return cand

    # Buscar patrones con guion o dos puntos: voy - Carlos, me anoto: Carlos
    sep_match = re.search(r"(?:voy|entro|juego|me\s+anoto|an[oó]tenme|me\s+apunto)\s*[:\-]\s*([a-záéíóúñ\s]+)", text, re.IGNORECASE)
    if sep_match:
        cand = clean_player_name(sep_match.group(1))
        if cand:
            return cand

    # Buscar 'anotenme a Nombre' / 'anota a Nombre'
    to_match = re.search(r"an[oó]t(?:enme|ame|ar)?\s+a\s+([a-záéíóúñ\s]+)", text, re.IGNORECASE)
    if to_match:
        cand = clean_player_name(to_match.group(1))
        if cand:
            return cand

    # Si hay un nombre por defecto (ej. nombre de perfil de WhatsApp)
    if default_name and clean_player_name(default_name):
        return clean_player_name(default_name)

    return "Jugador"


def to_participants_list(raw_players: any) -> List[dict]:
    """Normaliza la lista JSON de participantes a una lista canónica de diccionarios."""
    if not raw_players:
        return []
    result = []
    for i, item in enumerate(raw_players, start=1):
        if isinstance(item, dict):
            result.append({
                "spot_index": item.get("spot_index", i),
                "phone": item.get("phone", f"+57-unknown-{i}"),
                "display_name": item.get("display_name", f"Jugador {i}"),
                "client_tier": item.get("client_tier", "STANDARD"),
                "host_phone": item.get("host_phone"),
            })
        else:
            name = str(item).strip()
            result.append({
                "spot_index": i,
                "phone": f"+57-WA-{name.lower().replace(' ', '')}",
                "display_name": name,
                "client_tier": "STANDARD",
                "host_phone": None,
            })
    return result


async def find_target_slot(
    db: AsyncSession,
    raw_text: str,
    sender_phone: Optional[str] = None,
    must_be_registered: bool = False,
) -> Optional[TimeSlot]:
    """
    Localiza el TimeSlot objetivo:
    1. Por ID explícito (#12, slot 12, turno 12).
    2. Si must_be_registered=True (para 'me bajo'), busca turnos futuros donde el remitente esté anotado.
    3. Por fecha y hora si se citan en el mensaje.
    4. El turno abierto más próximo (fecha >= hoy, SPLIT_MATCH, con cupos libres).
    """
    today = date.today()

    # 1. Por ID explícito
    id_match = re.search(r"(?:slot|turno|cancha|id)?\s*#?\s*(\d+)", raw_text, re.IGNORECASE)
    if id_match:
        slot_id = int(id_match.group(1))
        stmt = (
            select(TimeSlot)
            .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
            .where(TimeSlot.id == slot_id)
        )
        res = await db.execute(stmt)
        slot = res.scalars().first()
        if slot:
            return slot

    # 2. Si es para baja ('me bajo'), localizar turno donde sender_phone esté registrado
    norm_sender = normalize_phone(sender_phone) if sender_phone else None
    if must_be_registered and norm_sender:
        stmt = (
            select(TimeSlot)
            .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
            .where(TimeSlot.date >= today)
            .order_by(TimeSlot.date.asc(), TimeSlot.start_time.asc())
        )
        res = await db.execute(stmt)
        active_slots = res.scalars().all()
        for s in active_slots:
            participants = to_participants_list(s.players_names)
            for p in participants:
                if normalize_phone(p.get("phone")) == norm_sender or normalize_phone(p.get("host_phone")) == norm_sender:
                    return s

    # 3. Por fecha y hora si están en el texto
    months = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }
    date_match = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-záéíóú]+)", raw_text, re.IGNORECASE)
    time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", raw_text, re.IGNORECASE)

    if date_match and time_match:
        day = int(date_match.group(1))
        m_name = date_match.group(2).lower()
        if m_name in months:
            target_d = date(today.year, months[m_name], day)
            from app.api.v1.endpoints.slots import parse_time_token
            start_t = parse_time_token(time_match.group(1))
            stmt = (
                select(TimeSlot)
                .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
                .where(TimeSlot.date == target_d, TimeSlot.start_time == start_t)
            )
            res = await db.execute(stmt)
            slot = res.scalars().first()
            if slot:
                return slot

    # 4. Turno abierto más próximo
    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
        .where(TimeSlot.date >= today)
        .order_by(TimeSlot.date.asc(), TimeSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    all_slots = res.scalars().all()
    for s in all_slots:
        mode_val = s.mode.value if hasattr(s.mode, "value") else str(s.mode)
        status_val = s.status.value if hasattr(s.status, "value") else str(s.status)
        if mode_val == "SPLIT_MATCH" and status_val in ("AVAILABLE", "PARTIALLY_BOOKED"):
            if s.booked_spots < s.capacity:
                return s

    return None


def format_whatsapp_reply(slot: TimeSlot) -> str:
    """
    Genera el mensaje de WhatsApp garantizando la inmutabilidad de los atributos del slot:
    - Fecha, hora de inicio y fin, precio y club son estrictamente los de la base de datos.
    - Muestra estado (PARTIDO ABIERTO / CERRADO), cupos restantes y jugadores canónicos.
    """
    date_str = slot.date.strftime("%d/%m/%Y")
    start_str = slot.start_time.strftime("%I:%M%p").lower()
    end_str = slot.end_time.strftime("%I:%M%p").lower()
    court_name = slot.court.name if slot.court else "Capital Pádel Club"
    category = slot.category or "4ta"

    # Inmutabilidad: Precio oficial por cupo extraído directamente del inventario
    price_per_spot = (slot.total_price / Decimal(slot.capacity)).quantize(Decimal("0.01"))
    price_formatted = f"{int(price_per_spot):,}".replace(",", ".")

    participants = to_participants_list(slot.players_names)
    spots_count = len(participants)
    free_spots = max(0, slot.capacity - spots_count)
    is_closed = (spots_count >= slot.capacity)

    if is_closed:
        players_lines = "\n".join([f"{i}. 🎾 {p['display_name']}" for i, p in enumerate(participants, start=1)])
        return (
            f"✅ ¡PARTIDO CERRADO Y CONFIRMADO! ({slot.capacity}/{slot.capacity}) 🎾\n"
            f"📍 {court_name}\n"
            f"📅 {date_str} | ⌚ {start_str} - {end_str}\n"
            f"🏆 Categoría: {category}\n"
            f"💰 Cuota: ${price_formatted} COP / jugador\n\n"
            f"👥 *Jugadores Confirmados ({slot.capacity}/{slot.capacity}):*\n"
            f"{players_lines}\n\n"
            f"🔒 *Cancha asegurada en sistema. ¡Nos vemos en la pista!*"
        )
    else:
        player_entries = []
        for i, p in enumerate(participants, start=1):
            player_entries.append(f"{i}. 🎾 {p['display_name']}")
        for i in range(spots_count + 1, slot.capacity + 1):
            player_entries.append(f"{i}. ⚡ [CUPO DISPONIBLE]")

        players_lines = "\n".join(player_entries)
        return (
            f"🎾 PARTIDO ABIERTO ({spots_count}/{slot.capacity})\n"
            f"📍 {court_name}\n"
            f"📅 {date_str} | ⌚ {start_str} - {end_str}\n"
            f"🏆 Categoría: {category}\n"
            f"💰 Cuota: ${price_formatted} COP / jugador\n\n"
            f"👥 *Inscritos ({spots_count}/{slot.capacity}):*\n"
            f"{players_lines}\n\n"
            f"⚡ *¡Quedan {free_spots} cupo(s) disponible(s)! Aparta tu cupo directamente respondiendo a esta lista.*"
        )


async def process_join_intent(
    db: AsyncSession,
    sender_phone: str,
    sender_name: Optional[str],
    raw_text: str,
) -> str:
    """
    Procesa la intención de entrada ('voy', 'entro', 'juego', 'me anoto'):
    1. Localiza el turno abierto.
    2. Valida que haya cupo y que el remitente no esté previamente inscrito.
    3. Registra al jugador respetando estrictamente los datos inmutables del inventario.
    4. Devuelve el mensaje formateado de confirmación.
    """
    norm_sender = normalize_phone(sender_phone)
    slot = await find_target_slot(db, raw_text, sender_phone=sender_phone, must_be_registered=False)

    if not slot:
        return (
            "⚠️ *NO HAY TURNOS ABIERTOS DISPONIBLES* ⚠️\n"
            "En este momento no se encontró una convocatoria abierta para sumarte.\n"
            "Por favor consulta en recepción o en el Dashboard los turnos oficiales disponibles."
        )

    participants = to_participants_list(slot.players_names)
    existing_phones = {normalize_phone(p.get("phone")) for p in participants if p.get("phone")}

    # Verificar si ya está inscrito
    if norm_sender in existing_phones:
        player_obj = next((p for p in participants if normalize_phone(p.get("phone")) == norm_sender), None)
        p_name = player_obj.get("display_name") if player_obj else "Jugador"
        date_str = slot.date.strftime("%d/%m/%Y")
        start_str = slot.start_time.strftime("%I:%M%p").lower()
        return (
            f"ℹ️ *YA ESTÁS INSCRITO* ℹ️\n"
            f"Tu número ya se encuentra registrado como *{p_name}* en el turno de las {start_str} ({date_str}).\n"
            f"¡Te esperamos en la pista!"
        )

    # Verificar si el turno está lleno
    if len(participants) >= slot.capacity:
        return (
            f"⚠️ *TURNO COMPLETO ({slot.capacity}/{slot.capacity})* ⚠️\n"
            f"El turno para el {slot.date.strftime('%d/%m/%Y')} a las {slot.start_time.strftime('%I:%M%p').lower()} "
            f"ya tiene todos sus cupos ocupados.\n"
            f"Por favor consulta otros turnos abiertos en recepción."
        )

    # Inscribir jugador en el primer cupo libre
    display_name = extract_player_name_from_join(raw_text, default_name=sender_name)
    new_spot_index = len(participants) + 1

    participants.append({
        "spot_index": new_spot_index,
        "phone": norm_sender,
        "display_name": display_name,
        "client_tier": "STANDARD",
        "host_phone": None,
    })

    slot.mode = SlotMode.SPLIT_MATCH
    slot.players_names = participants
    slot.booked_spots = len(participants)
    slot.status = SlotStatus.FULLY_BOOKED if slot.booked_spots >= slot.capacity else SlotStatus.PARTIALLY_BOOKED

    # Inmutabilidad: Preservar intactos slot.date, slot.start_time, slot.end_time, slot.court_id y slot.total_price
    await db.commit()
    await db.refresh(slot)

    logger.info(f"Player {norm_sender} ({display_name}) joined slot {slot.id} ({slot.booked_spots}/{slot.capacity})")
    return format_whatsapp_reply(slot)


async def process_drop_intent(
    db: AsyncSession,
    sender_phone: str,
    raw_text: str,
) -> str:
    """
    Procesa la intención de salida ('me bajo', 'no voy', 'cancelo'):
    1. Localiza el turno donde sender_phone esté registrado.
    2. Valida estrictamente que sender_phone corresponda a un cupo ocupado.
    3. Libera la posición, reabre el turno a PARTIDO ABIERTO y re-indexa.
    4. Devuelve la confirmación de baja y el nuevo estado del turno.
    """
    norm_sender = normalize_phone(sender_phone)
    if not norm_sender:
        return "⚠️ No se pudo verificar tu número telefónico para procesar la baja."

    slot = await find_target_slot(db, raw_text, sender_phone=sender_phone, must_be_registered=True)

    if not slot:
        return (
            "⚠️ *NO SE ENCONTRÓ NINGUNA RESERVA ACTIVA* ⚠️\n"
            f"El número {norm_sender} no figura como participante registrado en ningún turno próximo."
        )

    participants = to_participants_list(slot.players_names)
    matched_idx = -1
    matched_player = None

    for idx, p in enumerate(participants):
        p_phone = normalize_phone(p.get("phone"))
        h_phone = normalize_phone(p.get("host_phone"))
        if p_phone == norm_sender or h_phone == norm_sender:
            matched_idx = idx
            matched_player = p
            break

    if matched_idx == -1 or not matched_player:
        return (
            f"⚠️ *NO SE PUDO PROCESAR LA BAJA* ⚠️\n"
            f"El número {norm_sender} no tiene asignado un cupo en el turno #{slot.id}."
        )

    # Remover al participante y re-indexar los restantes
    participants.pop(matched_idx)
    for i, p in enumerate(participants, start=1):
        p["spot_index"] = i

    slot.players_names = participants
    slot.booked_spots = len(participants)
    slot.status = SlotStatus.AVAILABLE if slot.booked_spots == 0 else SlotStatus.PARTIALLY_BOOKED

    # Inmutabilidad: Preservar intactos slot.date, slot.start_time, slot.end_time, slot.court_id y slot.total_price
    await db.commit()
    await db.refresh(slot)

    logger.info(f"Player {norm_sender} ({matched_player['display_name']}) dropped from slot {slot.id}")

    date_str = slot.date.strftime("%d/%m/%Y")
    start_str = slot.start_time.strftime("%I:%M%p").lower()
    end_str = slot.end_time.strftime("%I:%M%p").lower()

    reopened_reply = format_whatsapp_reply(slot)
    return (
        f"✅ *BAJA CONFIRMADA EN YIELDPADEL*\n"
        f"Tu cupo en el turno de las {start_str} - {end_str} ({date_str}) ha sido liberado exitosamente.\n\n"
        f"{reopened_reply}"
    )


async def process_list_intent(
    db: AsyncSession,
    sender_phone: str,
    sender_name: Optional[str],
    raw_text: str,
) -> str:
    """
    Procesa el reenvío o pegado de una lista de convocatoria completa.
    Utiliza parse_flexible_player_list para aceptar cualquier emoji o numeración,
    protege la inmutabilidad de fecha/hora/precio en BD y actualiza el turno.
    """
    from app.schemas.slot import WhatsAppConvocatoriaRequest
    from app.api.v1.endpoints.slots import parse_open_match

    conv_res = await parse_open_match(
        payload=WhatsAppConvocatoriaRequest(
            raw_text=raw_text,
            sender_phone=sender_phone,
        ),
        db=db,
    )
    return conv_res.whatsapp_reply


async def process_incoming_whatsapp_message(
    db: AsyncSession,
    sender_phone: str,
    sender_name: Optional[str],
    raw_text: str,
) -> str:
    """
    Orquestador principal para mensajes entrantes de WhatsApp:
    Clasifica la intención y despacha a la rutina correspondiente.
    """
    intent = detect_intent(raw_text)
    logger.info(f"WhatsApp message intent '{intent}' from {sender_phone} ({sender_name})")

    if intent == "DROP":
        return await process_drop_intent(db, sender_phone, raw_text)
    elif intent == "JOIN":
        return await process_join_intent(db, sender_phone, sender_name, raw_text)
    elif intent == "LIST":
        return await process_list_intent(db, sender_phone, sender_name, raw_text)
    else:
        # Texto no reconocido como comando de pádel
        return (
            "🎾 *Asistente de Capital Pádel Club* 🎾\n\n"
            "Puedes responder a las convocatorias de pádel con los siguientes comandos:\n"
            "• *'voy'*, *'entro'* o *'me anoto'* para apartar un cupo en el turno abierto.\n"
            "• *'me bajo'* o *'cancelo'* para liberar tu cupo previamente reservado.\n"
            "• O pega la lista actualizada de jugadores para sincronizar el partido.\n\n"
            "¡Nos vemos en la pista! 🏆"
        )


async def send_whatsapp_message(to_phone: str, message_body: str) -> bool:
    """
    Despacha un mensaje de texto saliente a la Graph API de Meta (WhatsApp Cloud API v20.0).
    Lee WHATSAPP_PHONE_NUMBER_ID y WHATSAPP_ACCESS_TOKEN de variables de entorno o settings.
    """
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN") or getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)

    clean_to = to_phone.lstrip("+").strip()

    if not phone_number_id or not access_token:
        logger.warning(
            "WHATSAPP_PHONE_NUMBER_ID o WHATSAPP_ACCESS_TOKEN no están configurados. "
            "No se puede despachar la respuesta a Meta Graph API."
        )
        print(f"[WHATSAPP OUTGOING] AVISO: Faltan credenciales en entorno (WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_ACCESS_TOKEN). No se envió a {clean_to}.")
        print(f"[WHATSAPP OUTGOING PREVIEW a {clean_to}]:\n{message_body}\n")
        return False

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_body,
        },
    }

    print(f"[WHATSAPP OUTGOING] Despachando mensaje a {clean_to} vía Meta Graph API v20.0...")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.is_success:
                resp_json = resp.json()
                logger.info(f"WhatsApp outgoing message sent successfully to {clean_to}: {resp_json}")
                print(f"[WHATSAPP OUTGOING] ÉXITO enviando a {clean_to} (HTTP {resp.status_code}): {resp_json}")
                return True
            else:
                logger.error(
                    f"WhatsApp outgoing message error from Meta Graph API for {clean_to} (HTTP {resp.status_code}): {resp.text}"
                )
                print(f"[WHATSAPP OUTGOING] ERROR de Meta Graph API al enviar a {clean_to} (HTTP {resp.status_code}): {resp.text}")
                return False
    except Exception as exc:
        logger.error(f"Excepción al despachar mensaje WhatsApp a {clean_to}: {exc}", exc_info=True)
        print(f"[WHATSAPP OUTGOING] EXCEPCIÓN al despachar a {clean_to}: {exc}")
        return False
