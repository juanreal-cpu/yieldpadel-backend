"""
YieldPadel - Servicio de WhatsApp
Maneja dinámicas de grupo, reconocimiento de comandos por intención ('voy', 'me bajo'),
extracción precisa del turno en mensajes citados (context / reply),
control estricto de mutabilidad de atributos del inventario (fecha, horarios, precio y cancha),
detección flexible de jugadores con filtrado riguroso de cabeceras,
fallback inteligente de nombres (WhatsApp profile -> historial BD -> teléfono enmascarado),
y sistema de validaciones temporales y alertas de cancelación tardía con registro de incidencias.
"""

import logging
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.timezone import BOGOTA_TZ, get_bogota_now, get_bogota_today
from app.models.court import Court
from app.models.slot import ClientTier, SlotMode, SlotStatus, TimeSlot
from app.models.incident import PlayerIncident

logger = logging.getLogger("yieldpadel.whatsapp")

# Cache en memoria de mensajes enviados y recibidos por ID (wamid) para resolver citas
MESSAGES_CACHE: Dict[str, str] = {}

# Parámetros del sistema de cancelación
CANCELLATION_GRACE_MINUTES = getattr(settings, "CANCELLATION_GRACE_MINUTES", 30)
CONFIRMATION_GRACE_MINUTES = 10

# -----------------------------------------------------------------------------
# Expresiones regulares para reconocimiento de intenciones
# -----------------------------------------------------------------------------

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

# Emojis de cabeceras que invalidan inmediatamente una línea de jugador
HEADER_EMOJIS = ["📅", "🗓️", "📆", "⌚", "🕒", "⏰", "📍", "🏆", "💰", "💲", "💵"]

# Palabras prohibidas en nombres de jugador (fechas, meses, sedes, estados)
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
    "CANCHA",
    "SEDE",
    "PISTA",
    "HORARIO",
    "FECHA",
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
    "LUNES",
    "MARTES",
    "MIERCOLES",
    "MIÉRCOLES",
    "JUEVES",
    "VIERNES",
    "SABADO",
    "SÁBADO",
    "DOMINGO",
    "HOY",
    "MAÑANA",
    "AYER",
    "INSCRITOS",
    "JUGADORES",
    "CONFIRMADOS",
    "CANCHA ASEGURADA",
]

MONTHS_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}


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


def mask_phone(phone: Optional[str]) -> str:
    """
    Enmascara un número telefónico para visualización pública:
    Ejemplo: '+573134567547' -> '+57 313 ***547'
             '3134567547'   -> '+57 313 ***547'
    """
    if not phone:
        return "+57 *** ***000"

    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("57") and len(digits) == 12:
        area = digits[2:5]
        last3 = digits[-3:]
        return f"+57 {area} ***{last3}"
    elif len(digits) == 10 and digits.startswith("3"):
        area = digits[:3]
        last3 = digits[-3:]
        return f"+57 {area} ***{last3}"
    elif len(digits) >= 7:
        prefix = f"+{digits[:2]}" if digits.startswith("57") else (f"+{digits[0]}" if str(phone).startswith("+") else "")
        remaining = digits[2:] if digits.startswith("57") else digits
        first3 = remaining[:3]
        last3 = remaining[-3:]
        return f"{prefix} {first3} ***{last3}".strip()
    return f"+57 *** ***{digits[-3:] if len(digits) >= 3 else '000'}"


def is_masked_phone(val: str) -> bool:
    """Detecta si una cadena representa un teléfono enmascarado (ej: '+57 313 ***547')."""
    if not val:
        return False
    clean = val.strip()
    return bool(re.match(r"^\+?\d{1,3}\s*\d{2,4}\s*\*{2,4}\s*\d{2,4}$", clean))


def parse_time_token(token: str) -> time:
    """Parsea tokens como '2:00pm', '14:00', '3pm', '9:30am'."""
    clean = token.strip().lower()
    is_pm = "pm" in clean
    is_am = "am" in clean
    clean = clean.replace("pm", "").replace("am", "").strip()

    if ":" in clean:
        parts = clean.split(":")
        h, m = int(parts[0]), int(parts[1])
    else:
        h, m = int(clean), 0

    if is_pm and h < 12:
        h += 12
    elif is_am and h == 12:
        h = 0

    return time(h, m)


def detect_intent(text: str) -> str:
    """Clasifica el mensaje en 'DROP', 'JOIN', 'LIST' o 'UNKNOWN'."""
    clean = text.strip()
    if DROP_REGEX.search(clean):
        return "DROP"
    if JOIN_REGEX.search(clean):
        return "JOIN"
    if "🎾" in clean or ("1." in clean and "2." in clean) or ("cancha" in clean.lower() and "4ta" in clean.lower()):
        return "LIST"
    return "UNKNOWN"


def clean_player_name(raw_name: str) -> Optional[str]:
    """
    Limpieza estricta de nombres de jugador:
    - Preserva teléfonos con máscara (+57 313 ***547).
    - Filtra y descarta si contiene emojis de calendario, reloj, sede, dinero o trofeo.
    - Filtra y descarta si contiene dígitos o fechas (ej: '24', '15000', '2:00pm').
    - Un jugador solo es válido si es una cadena de texto alfabética limpia o un teléfono enmascarado.
    """
    if not raw_name:
        return None

    # Si contiene algún emoji de cabecera, descartar inmediatamente
    for em in HEADER_EMOJIS:
        if em in raw_name:
            return None

    # Remover viñetas, números de lista iniciales (ej: '1.', '2)', '3 -'), emojis y corchetes
    cleaned = re.sub(r"^[0-9\.\-\)\:\s\[\]\(\)\⚡\*\#\+🎾🏓🏸👤🔥✅]+", "", raw_name).strip()
    cleaned = re.sub(r"[0-9\.\-\)\:\s\[\]\(\)\⚡\*\#\+🎾🏓🏸👤🔥✅]+$", "", cleaned).strip()

    # Si el valor es un teléfono enmascarado, aceptarlo directamente
    if is_masked_phone(cleaned):
        return cleaned
    raw_cleaned = re.sub(r"^[0-9\.\-\)\:\s\[\]\(\)\⚡\#🎾🏓🏸👤🔥✅]+", "", raw_name).strip()
    if is_masked_phone(raw_cleaned):
        return raw_cleaned
    if is_masked_phone(raw_name):
        return raw_name.strip()

    if len(cleaned) < 2:
        return None

    # Si contiene CUALQUIER dígito dentro del nombre (ej: '24 de Septiembre', '2:00pm', '15000'), es inválido
    if re.search(r"\d", cleaned):
        return None

    cleaned_upper = cleaned.upper()
    for pat in DISCARD_PATTERNS:
        if pat in cleaned_upper:
            return None

    # Validar que esté compuesto exclusivamente por letras (con acentos y ñ), espacios, puntos o guiones
    if not re.match(r"^[a-záéíóúñüA-ZÁÉÍÓÚÑÜ\s\.\'\-]+$", cleaned):
        return None

    # Debe contener al menos 2 letras
    letters = re.findall(r"[a-záéíóúñüA-ZÁÉÍÓÚÑÜ]", cleaned)
    if len(letters) < 2:
        return None

    return cleaned


def parse_flexible_player_list(raw_text: str) -> List[str]:
    """
    Detección flexible de nombres en listas:
    Reconoce jugadores con 🎾 o cualquier viñeta, descartando exhaustivamente
    líneas de fechas (📅, 24 de Septiembre), relojes (⌚, 2:00pm), sedes (📍),
    categorías (🏆) o cuotas (💰).
    """
    players: List[str] = []
    lines = raw_text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 1. Descartar si contiene emojis de cabecera
        if any(em in stripped for em in HEADER_EMOJIS):
            continue

        # 2. Descartar si contiene palabras de fecha o meses
        stripped_lower = stripped.lower()
        if any(m in stripped_lower for m in MONTHS_MAP):
            continue
        if any(d in stripped_lower for d in ["lunes", "martes", "miercoles", "miércoles", "jueves", "viernes", "sabado", "sábado", "domingo", "hoy", "mañana", "ayer"]):
            continue

        # 3. Descartar si contiene horarios o precios
        if re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", stripped_lower):
            continue
        if re.search(r"\b\d{1,2}:\d{2}\b", stripped_lower):
            continue
        if any(w in stripped_lower for w in ["cuota", "precio", "valor", "costo", "cop", "$", "cancha", "sede", "club", "categoria", "categoría"]):
            continue

        # 4. Descartar indicadores de estado o vacíos
        if any(w in stripped_lower for w in ["cupo", "disponible", "libre", "inscritos", "confirmados", "partido abierto", "partido cerrado", "cancha asegurada"]):
            continue

        # Extraer texto de jugador tras emoji representativo si existe
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


def extract_explicit_nickname(text: str) -> Optional[str]:
    """Extrae apodo explícito en mensajes de entrada ('voy (Pipe)', 'entro - Carlos', 'anótenme a Juan')."""
    paren_match = re.search(r"\(([^)]+)\)", text)
    if paren_match:
        cand = clean_player_name(paren_match.group(1))
        if cand:
            return cand

    sep_match = re.search(r"(?:voy|entro|juego|me\s+anoto|an[oó]tenme|me\s+apunto)\s*[:\-]\s*([a-záéíóúñ\s]+)", text, re.IGNORECASE)
    if sep_match:
        cand = clean_player_name(sep_match.group(1))
        if cand:
            return cand

    to_match = re.search(r"an[oó]t(?:enme|ame|ar)?\s+a\s+([a-záéíóúñ\s]+)", text, re.IGNORECASE)
    if to_match:
        cand = clean_player_name(to_match.group(1))
        if cand:
            return cand

    return None


def extract_player_name_from_join(text: str, default_name: Optional[str] = None) -> str:
    """Extrae apodo explícito en mensajes de entrada ('voy (Pipe)', 'entro - Carlos')."""
    nick = extract_explicit_nickname(text)
    if nick:
        return nick
    if default_name and clean_player_name(default_name):
        return clean_player_name(default_name)
    return "Jugador"


async def find_prior_player_name(db: AsyncSession, sender_phone: str) -> Optional[str]:
    """
    Busca si sender_phone ya tiene un display_name registrado en la base de datos:
    1. Participantes previos de TimeSlot (JSON players_names)
    2. Booking (yield_bookings)
    3. SlotHold (slot_holds)
    Descarta 'Jugador' o teléfonos enmascarados.
    """
    norm_phone = normalize_phone(sender_phone)
    if not norm_phone:
        return None

    digits = re.sub(r"\D", "", norm_phone)
    last_7 = digits[-7:] if len(digits) >= 7 else digits

    # 1. Buscar en TimeSlot.players_names recientes
    try:
        stmt = select(TimeSlot).order_by(TimeSlot.id.desc()).limit(100)
        res = await db.execute(stmt)
        slots = res.scalars().all()
        for s in slots:
            participants = to_participants_list(s.players_names)
            for p in participants:
                p_phone = normalize_phone(p.get("phone"))
                h_phone = normalize_phone(p.get("host_phone"))
                if p_phone == norm_phone or h_phone == norm_phone or (last_7 and (last_7 in p_phone or last_7 in h_phone)):
                    cand = p.get("display_name")
                    if cand and cand != "Jugador" and not is_masked_phone(cand):
                        cleaned = clean_player_name(cand)
                        if cleaned:
                            return cleaned
    except Exception as e:
        logger.warning(f"Error checking prior player names in TimeSlot: {e}")

    # 2. Buscar en Booking
    try:
        from app.models.booking import Booking
        stmt_b = select(Booking.customer_name).where(Booking.customer_phone.like(f"%{last_7}%")).order_by(Booking.id.desc()).limit(10)
        res_b = await db.execute(stmt_b)
        names_b = res_b.scalars().all()
        for cand in names_b:
            if cand and cand != "Jugador" and not is_masked_phone(cand):
                cleaned = clean_player_name(cand)
                if cleaned:
                    return cleaned
    except Exception as e:
        logger.warning(f"Error checking prior player names in Booking: {e}")

    # 3. Buscar en SlotHold
    try:
        from app.models.slot import SlotHold
        stmt_h = select(SlotHold.customer_name).where(SlotHold.customer_phone.like(f"%{last_7}%")).order_by(SlotHold.id.desc()).limit(10)
        res_h = await db.execute(stmt_h)
        names_h = res_h.scalars().all()
        for cand in names_h:
            if cand and cand != "Jugador" and not is_masked_phone(cand):
                cleaned = clean_player_name(cand)
                if cleaned:
                    return cleaned
    except Exception as e:
        logger.warning(f"Error checking prior player names in SlotHold: {e}")

    return None


async def resolve_join_player_name(
    db: AsyncSession,
    raw_text: str,
    sender_name: Optional[str],
    sender_phone: str,
) -> str:
    """
    Jerarquía estricta de nombres para 'voy':
    1. Apodo explícito en el texto ('voy (Pipe)', 'entro - Carlos').
    2. Nombre del perfil de WhatsApp (sender_name).
    3. Historial en BD de sender_phone (TimeSlot, Booking, SlotHold).
    4. Teléfono enmascarado (ej. '+57 313 ***547') en lugar de la palabra 'Jugador'.
    """
    # 1. Apodo explícito
    nickname = extract_explicit_nickname(raw_text)
    if nickname:
        return nickname

    # 2. Nombre del perfil de WhatsApp
    if sender_name and str(sender_name).strip():
        cleaned_sender = clean_player_name(str(sender_name).strip())
        if cleaned_sender:
            return cleaned_sender

    # 3. Buscar display_name previo en la base de datos
    prior_name = await find_prior_player_name(db, sender_phone)
    if prior_name:
        return prior_name

    # 4. Fallback a teléfono con máscara
    return mask_phone(sender_phone)


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


def parse_slot_info_from_text(text: str) -> Tuple[Optional[int], Optional[date], Optional[time], Optional[time]]:
    """
    Extrae la fecha, horario (start_time, end_time) y/o ID de slot de un texto o mensaje citado.
    """
    if not text:
        return None, None, None, None

    today = get_bogota_today()
    slot_id = None
    target_date = None
    start_t = None
    end_t = None

    # 1. Buscar ID explícito (#12, slot 12, turno #12)
    id_match = re.search(r"\b(?:slot|turno|id)\s*#?\s*(\d+)\b|#\s*(\d+)\b", text, re.IGNORECASE)
    if id_match:
        cand_id = int(id_match.group(1) or id_match.group(2))
        if cand_id < 1000 and not (cand_id >= 2024 and cand_id <= 2030):
            slot_id = cand_id

    # 2. Buscar fecha
    # a) Fecha con indicador de calendario (ej: 📅 24/09/2026 o 📅 24/09)
    cal_date_match = re.search(r"(?:📅|🗓️|📆|fecha:?)\s*(\d{1,2})[\/\-\.](\d{1,2})(?:[\/\-\.](\d{2,4}))?", text, re.IGNORECASE)
    if cal_date_match:
        day = int(cal_date_match.group(1))
        month = int(cal_date_match.group(2))
        year = int(cal_date_match.group(3)) if cal_date_match.group(3) else today.year
        if len(str(year)) == 2:
            year += 2000
        try:
            target_date = date(year, month, day)
        except ValueError:
            pass

    # b) Formato completo de 3 partes DD/MM/YYYY o DD-MM-YYYY (evita (2/4))
    if not target_date:
        full_date_match = re.search(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b", text)
        if full_date_match:
            day = int(full_date_match.group(1))
            month = int(full_date_match.group(2))
            year = int(full_date_match.group(3))
            if len(str(year)) == 2:
                year += 2000
            try:
                target_date = date(year, month, day)
            except ValueError:
                pass

    # c) Formato "24 de Septiembre" o "HOY 6 SEPTIEMBRE"
    if not target_date:
        name_date_match = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-záéíóú]+)", text, re.IGNORECASE)
        if name_date_match and name_date_match.group(2).lower() in MONTHS_MAP:
            day = int(name_date_match.group(1))
            month = MONTHS_MAP[name_date_match.group(2).lower()]
            target_date = date(today.year, month, day)

    if not target_date:
        if re.search(r"\bhoy\b", text, re.IGNORECASE):
            target_date = today
        elif re.search(r"\bmañana\b|\bmanana\b", text, re.IGNORECASE):
            target_date = today + timedelta(days=1)

    # 3. Buscar franja horaria (start_time - end_time)
    time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text, re.IGNORECASE)
    if time_match:
        start_t = parse_time_token(time_match.group(1))
        end_t = parse_time_token(time_match.group(2))
    else:
        single_time_match = re.search(r"\b(?:a\s+las|alas)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", text, re.IGNORECASE)
        if single_time_match:
            start_t = parse_time_token(single_time_match.group(1))

    return slot_id, target_date, start_t, end_t


async def find_target_slot(
    db: AsyncSession,
    raw_text: str,
    quoted_text: Optional[str] = None,
    sender_phone: Optional[str] = None,
    must_be_registered: bool = False,
) -> Optional[TimeSlot]:
    """
    Localización precisa del turno:
    1. Si hay mensaje citado (quoted_text): extrae obligatoriamente la fecha y horario DEL TEXTO CITADO.
       Busca estrictamente el slot que coincida con el horario del mensaje citado y NO busca otro slot.
    2. Si no hay mensaje citado:
       - Si se menciona un slot ID explícito o fecha/hora en raw_text, lo busca.
       - Si must_be_registered=True (baja), busca el turno donde el usuario esté inscrito (futuro o pasado reciente).
       - Si es entrada ('voy'), busca el turno abierto más próximo.
    """
    today = get_bogota_today()

    # -------------------------------------------------------------------------
    # CASO 1: Extracción precisa desde MENSAJE CITADO
    # -------------------------------------------------------------------------
    if quoted_text:
        q_slot_id, q_date, q_start, q_end = parse_slot_info_from_text(quoted_text)
        logger.info(f"Parsed quoted context -> slot_id={q_slot_id}, date={q_date}, start={q_start}, end={q_end}")

        if q_slot_id:
            stmt = select(TimeSlot).options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds)).where(TimeSlot.id == q_slot_id)
            res = await db.execute(stmt)
            slot = res.scalars().first()
            if slot:
                return slot

        target_d = q_date or today
        if q_start:
            stmt = (
                select(TimeSlot)
                .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
                .where(TimeSlot.date == target_d, TimeSlot.start_time == q_start)
            )
            res = await db.execute(stmt)
            slot = res.scalars().first()
            if slot:
                return slot

        logger.warning(f"Quoted context provided but no matching slot found in DB: date={target_d}, start={q_start}")
        return None

    # -------------------------------------------------------------------------
    # CASO 2: Sin mensaje citado (búsqueda directa)
    # -------------------------------------------------------------------------
    # a) ID explícito en el texto
    id_match = re.search(r"\b(?:slot|turno|id)\s*#?\s*(\d+)\b|#\s*(\d+)\b", raw_text, re.IGNORECASE)
    if id_match:
        cand_id = int(id_match.group(1) or id_match.group(2))
        if cand_id < 1000 and not (cand_id >= 2024 and cand_id <= 2030):
            stmt = select(TimeSlot).options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds)).where(TimeSlot.id == cand_id)
            res = await db.execute(stmt)
            slot = res.scalars().first()
            if slot:
                return slot

    # b) Si es baja ('me bajo'), localizar turno donde el usuario esté inscrito
    norm_sender = normalize_phone(sender_phone) if sender_phone else None
    if must_be_registered and norm_sender:
        # Primero turnos de hoy en adelante
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

        # Buscar en turnos recientes pasados para poder rechazar adecuadamente con aviso de concluido
        stmt_past = (
            select(TimeSlot)
            .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
            .where(TimeSlot.date >= today - timedelta(days=3))
            .order_by(TimeSlot.date.desc(), TimeSlot.start_time.desc())
        )
        res_past = await db.execute(stmt_past)
        past_slots = res_past.scalars().all()
        for s in past_slots:
            participants = to_participants_list(s.players_names)
            for p in participants:
                if normalize_phone(p.get("phone")) == norm_sender or normalize_phone(p.get("host_phone")) == norm_sender:
                    return s

    # c) Horario citado en raw_text
    _, raw_date, raw_start, _ = parse_slot_info_from_text(raw_text)
    if raw_start:
        target_d = raw_date or today
        stmt = (
            select(TimeSlot)
            .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
            .where(TimeSlot.date == target_d, TimeSlot.start_time == raw_start)
        )
        res = await db.execute(stmt)
        slot = res.scalars().first()
        if slot:
            return slot

    # d) Turno abierto más próximo
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
    Genera el mensaje oficial de WhatsApp garantizando la inmutabilidad 100% de tarifa y sede:
    - La cuota y el nombre de la cancha provienen exclusivamente del objeto slot en BD.
    - Prohíbe cualquier sobreescritura externa de precios.
    """
    date_str = slot.date.strftime("%d/%m/%Y")
    start_str = slot.start_time.strftime("%I:%M%p").lower()
    end_str = slot.end_time.strftime("%I:%M%p").lower()

    try:
        court_name = slot.court.name if (hasattr(slot, "court") and slot.court) else "Capital Pádel Club"
    except Exception:
        court_name = "Capital Pádel Club"
    category = slot.category or "4ta"
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


async def record_player_incident(
    db: AsyncSession,
    player_phone: str,
    player_name: str,
    slot_id: int,
    incident_type: str = "late_cancellation",
    description: str = "Baja tardía con menos de 30 min de anticipación",
) -> PlayerIncident:
    """Registra una incidencia en el historial del jugador."""
    incident = PlayerIncident(
        player_phone=player_phone,
        player_name=player_name,
        slot_id=slot_id,
        incident_type=incident_type,
        description=description,
        created_at=datetime.now(timezone.utc),
    )
    db.add(incident)
    return incident


async def get_player_incidents(db: AsyncSession, phone: str) -> List[dict]:
    """Obtiene el historial de incidencias de un jugador."""
    norm_phone = normalize_phone(phone)
    digits = re.sub(r"\D", "", norm_phone)
    last_7 = digits[-7:] if len(digits) >= 7 else digits

    stmt = (
        select(PlayerIncident)
        .where(PlayerIncident.player_phone.like(f"%{last_7}%"))
        .order_by(PlayerIncident.created_at.desc())
    )
    res = await db.execute(stmt)
    records = res.scalars().all()
    return [
        {
            "id": r.id,
            "player_phone": r.player_phone,
            "player_name": r.player_name,
            "slot_id": r.slot_id,
            "incident_type": r.incident_type,
            "description": r.description,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


async def process_join_intent(
    db: AsyncSession,
    sender_phone: str,
    sender_name: Optional[str],
    raw_text: str,
    quoted_text: Optional[str] = None,
) -> str:
    """
    Procesa intención de entrada ('voy', 'entro', 'juego', 'me anoto'):
    - Aplica jerarquía de nombres: apodo explícito -> perfil WhatsApp -> historial BD -> teléfono con máscara.
    - Localiza el slot citado o el turno abierto más próximo.
    - Si completa capacidad, marca slot.closed_at y confirma partido cerrado.
    """
    norm_sender = normalize_phone(sender_phone)
    slot = await find_target_slot(
        db=db,
        raw_text=raw_text,
        quoted_text=quoted_text,
        sender_phone=sender_phone,
        must_be_registered=False,
    )

    if not slot:
        if quoted_text:
            return (
                "⚠️ *TURNO CITADO NO ENCONTRADO O CERRADO* ⚠️\n"
                "El horario al que estás respondiendo no se encuentra disponible o no existe en el sistema.\n"
                "Por favor consulta en recepción o en el Dashboard los turnos oficiales disponibles."
            )
        return (
            "⚠️ *NO HAY TURNOS ABIERTOS DISPONIBLES* ⚠️\n"
            "En este momento no se encontró una convocatoria abierta para sumarte.\n"
            "Por favor consulta en recepción o en el Dashboard los turnos oficiales disponibles."
        )

    participants = to_participants_list(slot.players_names)
    existing_phones = {normalize_phone(p.get("phone")) for p in participants if p.get("phone")}

    # Validar no duplicidad
    if norm_sender in existing_phones:
        player_obj = next((p for p in participants if normalize_phone(p.get("phone")) == norm_sender), None)
        p_name = player_obj.get("display_name") if player_obj else mask_phone(norm_sender)
        date_str = slot.date.strftime("%d/%m/%Y")
        start_str = slot.start_time.strftime("%I:%M%p").lower()
        return (
            f"ℹ️ *YA ESTÁS INSCRITO* ℹ️\n"
            f"Tu número ya se encuentra registrado como *{p_name}* en el turno de las {start_str} ({date_str}).\n"
            f"¡Te esperamos en la pista!"
        )

    # Validar capacidad
    if len(participants) >= slot.capacity:
        return (
            f"⚠️ *TURNO COMPLETO ({slot.capacity}/{slot.capacity})* ⚠️\n"
            f"El turno para el {slot.date.strftime('%d/%m/%Y')} a las {slot.start_time.strftime('%I:%M%p').lower()} "
            f"ya tiene todos sus cupos ocupados.\n"
            f"Por favor consulta otros turnos abiertos en recepción."
        )

    # 1. Resolver display_name con fallback estricto:
    # Perfil WhatsApp -> Historial BD (TimeSlot, Booking, SlotHold) -> Teléfono con máscara (ej. '+57 313 ***547')
    display_name = await resolve_join_player_name(
        db=db,
        raw_text=raw_text,
        sender_name=sender_name,
        sender_phone=norm_sender,
    )

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

    if slot.booked_spots >= slot.capacity:
        slot.status = SlotStatus.FULLY_BOOKED
        if not slot.closed_at:
            slot.closed_at = datetime.now(timezone.utc)
    else:
        slot.status = SlotStatus.PARTIALLY_BOOKED

    # Inmutabilidad: Preservar total_price, court_id, date, start_time y end_time intactos
    await db.commit()
    await db.refresh(slot)

    logger.info(f"Player {norm_sender} ({display_name}) joined slot {slot.id} ({slot.booked_spots}/{slot.capacity})")
    return format_whatsapp_reply(slot)


async def process_drop_intent(
    db: AsyncSession,
    sender_phone: str,
    raw_text: str,
    quoted_text: Optional[str] = None,
) -> str:
    """
    Procesa intención de salida ('me bajo', 'no voy', 'cancelo'):
    - Valida que sender_phone corresponda a un cupo activo en un turno.
    - Rechaza la baja si el partido ya está en curso o en el pasado.
    - Si faltan menos de 30 minutos:
        * Si el turno se cerró hace menos de 10 min: baja sin penalidad (confirmación de última hora).
        * Si llevaba cerrado más tiempo:
            a) Registra incidencia 'late_cancellation' en historial del jugador.
            b) Envía advertencia al usuario.
            c) Emite alerta de urgencia al grupo: '🚨 ¡SE BUSCA 1 JUGADOR URGENTE!...'
    - Si faltan más de 30 minutos: baja normal y republica la lista con [CUPO DISPONIBLE].
    """
    norm_sender = normalize_phone(sender_phone)
    if not norm_sender:
        return "⚠️ No se pudo verificar tu número telefónico para procesar la baja."

    slot = await find_target_slot(
        db=db,
        raw_text=raw_text,
        quoted_text=quoted_text,
        sender_phone=sender_phone,
        must_be_registered=True,
    )

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

    date_str = slot.date.strftime("%d/%m/%Y")
    start_str = slot.start_time.strftime("%I:%M%p").lower()
    end_str = slot.end_time.strftime("%I:%M%p").lower()
    court_name = slot.court.name if slot.court else "Capital Pádel Club"

    # -------------------------------------------------------------------------
    # VALIDACIÓN TEMPORAL 1: Partido Pasado o en Curso (Zona Horaria Colombia)
    # -------------------------------------------------------------------------
    now_bogota = get_bogota_now()
    today = now_bogota.date()
    now_time = now_bogota.time()

    is_past_or_current = (slot.date < today) or (slot.date == today and slot.start_time <= now_time)
    if is_past_or_current:
        return (
            "⚠️ *PARTIDO EN CURSO O FINALIZADO* ⚠️\n"
            f"El turno de las {start_str} - {end_str} ({date_str}) ya está en juego o ha finalizado.\n"
            "No es posible procesar la baja de un partido en curso o pasado."
        )

    # -------------------------------------------------------------------------
    # VALIDACIÓN TEMPORAL 2: Ventana de 30 min y Cierre Reciente de 10 min
    # -------------------------------------------------------------------------
    slot_dt = datetime.combine(slot.date, slot.start_time).replace(tzinfo=BOGOTA_TZ)
    minutes_until_start = (slot_dt - now_bogota).total_seconds() / 60

    is_late = (minutes_until_start < CANCELLATION_GRACE_MINUTES)
    is_recent_close = False
    mins_since_close = None

    if is_late and slot.closed_at:
        now_utc = datetime.now(timezone.utc)
        if slot.closed_at.tzinfo is not None:
            mins_since_close = (now_utc - slot.closed_at).total_seconds() / 60
        else:
            mins_since_close = (now_utc - slot.closed_at.replace(tzinfo=timezone.utc)).total_seconds() / 60

        if 0 <= mins_since_close <= CONFIRMATION_GRACE_MINUTES:
            is_recent_close = True

    # Remover participante y re-indexar los restantes
    participants.pop(matched_idx)
    for i, p in enumerate(participants, start=1):
        p["spot_index"] = i

    slot.players_names = participants
    slot.booked_spots = len(participants)
    slot.status = SlotStatus.AVAILABLE if slot.booked_spots == 0 else SlotStatus.PARTIALLY_BOOKED
    slot.closed_at = None  # Al abrirse un cupo, deja de estar cerrado

    logger.info(f"Player {norm_sender} ({matched_player.get('display_name')}) dropped from slot {slot.id}")

    if is_late and not is_recent_close:
        # a) Registrar una incidencia de baja tardía (late_cancellation) en el historial del jugador
        await record_player_incident(
            db=db,
            player_phone=norm_sender,
            player_name=matched_player.get("display_name", mask_phone(norm_sender)),
            slot_id=slot.id,
            incident_type="late_cancellation",
            description=f"Baja tardía con {max(0, int(minutes_until_start))} min de anticipación en turno #{slot.id}",
        )
        await db.commit()
        await db.refresh(slot)

        # b) Advertencia al usuario
        warning_msg = "⚠️ Tu baja se procesó con menos de 30 min de anticipación. Queda asentada en tu historial de reservas."

        # c) Mensaje de alerta de urgencia al grupo
        urgency_alert = (
            "🚨 ¡SE BUSCA 1 JUGADOR URGENTE!\n"
            f"Turno: {start_str} - {end_str} | {court_name}\n"
            "Un cupo se acaba de liberar. Responde 'VOY' para entrar a la pista."
        )

        group_id = os.getenv("WHATSAPP_GROUP_ID") or getattr(settings, "WHATSAPP_GROUP_ID", None)
        if group_id:
            try:
                await send_whatsapp_message(to_phone=group_id, message_body=urgency_alert)
            except Exception as e:
                logger.error(f"Error despachando alerta de urgencia al grupo {group_id}: {e}")

        reopened_reply = format_whatsapp_reply(slot)
        return (
            f"✅ *BAJA PROCESADA CON ADVERTENCIA*\n"
            f"Tu cupo en el turno de las {start_str} - {end_str} ({date_str}) ha sido liberado.\n\n"
            f"{warning_msg}\n\n"
            f"{urgency_alert}\n\n"
            f"{reopened_reply}"
        )

    elif is_late and is_recent_close:
        # Cerró hace menos de 10 minutos: baja sin penalidad
        await db.commit()
        await db.refresh(slot)

        mins_label = int(mins_since_close) if mins_since_close is not None else 0
        reopened_reply = format_whatsapp_reply(slot)
        return (
            f"✅ *BAJA PROCESADA SIN PENALIDAD*\n"
            f"Entendemos que el partido se confirmó hace menos de 10 minutos ({mins_label} min). "
            f"Tu cupo en el turno de las {start_str} - {end_str} ({date_str}) ha sido liberado sin penalidad por confirmación de última hora.\n\n"
            f"{reopened_reply}"
        )

    else:
        # Faltan más de 30 minutos: baja normal
        await db.commit()
        await db.refresh(slot)

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
    """Procesa el reenvío de una lista de convocatoria completa."""
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
    quoted_text: Optional[str] = None,
    context: Optional[dict] = None,
) -> str:
    """
    Orquestador principal de mensajes entrantes.
    Resuelve el texto citado desde context si no viene explícito.
    """
    if not quoted_text and context:
        quoted_text = (
            context.get("quoted_message", {}).get("body")
            or context.get("quoted_message", {}).get("text", {}).get("body")
            or context.get("body")
            or context.get("text")
        )
        if not quoted_text and context.get("id"):
            quoted_text = MESSAGES_CACHE.get(context.get("id"))

    intent = detect_intent(raw_text)
    logger.info(f"WhatsApp message intent '{intent}' from {sender_phone} ({sender_name}), quoted_len={len(quoted_text) if quoted_text else 0}")

    if intent == "DROP":
        return await process_drop_intent(db, sender_phone, raw_text, quoted_text=quoted_text)
    elif intent == "JOIN":
        return await process_join_intent(db, sender_phone, sender_name, raw_text, quoted_text=quoted_text)
    elif intent == "LIST":
        return await process_list_intent(db, sender_phone, sender_name, raw_text)
    else:
        return (
            "🎾 *Asistente de Capital Pádel Club* 🎾\n\n"
            "Puedes responder a las convocatorias de pádel con los siguientes comandos:\n"
            "• *'voy'*, *'entro'* o *'me anoto'* (incluso citando la convocatoria) para apartar un cupo.\n"
            "• *'me bajo'* o *'cancelo'* para liberar tu cupo previamente reservado.\n"
            "• O pega la lista actualizada de jugadores para sincronizar el partido.\n\n"
            "¡Nos vemos en la pista! 🏆"
        )


async def send_whatsapp_message(to_phone: str, message_body: str) -> bool:
    """Despacha un mensaje de texto a Meta Graph API v20.0 y almacena en cache."""
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN") or getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)

    clean_to = to_phone.lstrip("+").strip()

    if not phone_number_id or not access_token:
        logger.warning("Faltan credenciales WHATSAPP_PHONE_NUMBER_ID o WHATSAPP_ACCESS_TOKEN.")
        print(f"[WHATSAPP OUTGOING] AVISO: Faltan credenciales en entorno. No se envió a {clean_to}.")
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

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.is_success:
                resp_json = resp.json()
                msg_id = resp_json.get("messages", [{}])[0].get("id")
                if msg_id:
                    MESSAGES_CACHE[msg_id] = message_body
                logger.info(f"WhatsApp outgoing sent to {clean_to}: {resp_json}")
                print(f"[WHATSAPP OUTGOING] ÉXITO enviando a {clean_to}: {resp_json}")
                return True
            else:
                logger.error(f"Error Meta Graph API ({resp.status_code}): {resp.text}")
                print(f"[WHATSAPP OUTGOING] ERROR Meta Graph API: {resp.text}")
                return False
    except Exception as exc:
        logger.error(f"Excepción despachando a {clean_to}: {exc}", exc_info=True)
        print(f"[WHATSAPP OUTGOING] EXCEPCIÓN: {exc}")
        return False
