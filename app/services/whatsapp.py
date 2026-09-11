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
from sqlalchemy import cast, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.timezone import BOGOTA_TZ, get_bogota_now, get_bogota_today
from app.models.court import Court
from app.models.slot import ClientTier, SlotMode, SlotStatus, TimeSlot
from app.models.incident import PlayerIncident

logger = logging.getLogger("yieldpadel.whatsapp")

try:
    import google.generativeai as genai
except ImportError:
    genai = None

# -----------------------------------------------------------------------------
# IA Concierge (Gemini) - Conocimiento del club y tono humano
# -----------------------------------------------------------------------------

CONCIERGE_SYSTEM_INSTRUCTION = """Eres el asistente concierge oficial de Capital Pádel Club (sede Maloka, Bogotá).
Tu tono es cálido, servicial, deportivo y formal-cercano (español de Colombia con trato respetuoso).

INFORMACIÓN INSTITUCIONAL DEL CLUB:
- Ubicación: Complejo Maloka, Bogotá D.C.
- Horario: Lunes a Domingo de 06:00 a 24:00 (último turno inicia 22:00/22:30).
- Instalaciones: 5 canchas de pádel (Canchas 1 a 4 azules, Cancha 5 negra), 2 pistas de pickleball, 1 cancha de arena para vóley y sala de consolas.
- Servicios: Tienda/POS (venta y alquiler de palas, bolas), Bar/Cafetería, vestieres, parqueadero cubierto.
- Actividades: Torneos Americanos entre semana y fines de semana, Academia formativa y partidos abiertos comunitarios.

REGLAS DE INTERACCIÓN:
- Si el usuario saluda por primera vez o dice 'hola', responde con el saludo cálido y humano presentándote como el equipo de Capital Pádel Club y ofreciendo ayuda en reservas, torneos o servicios.
- Si pregunta qué es el club, horarios, servicios o precios generales, responde de forma clara y directa usando emojis deportivos sobrios (🎾, 📍, ⌚, 🏆).
- Si pregunta por disponibilidad específica de canchas para hoy o mañana, invoca la consulta a la base de datos de time_slots y presenta las opciones disponibles con su precio en pesos colombianos.
- Si el mensaje corresponde a una lista de partido con raquetas (🎾) o comandos 'voy'/'me bajo', deriva al flujo transaccional existente sin alterarlo."""


def is_transactional_message(text: str) -> bool:
    """True si el mensaje trae raquetas (🎾) o comandos rígidos 'voy'/'me bajo' que deben ir al flujo transaccional existente."""
    if not text:
        return False
    return bool("🎾" in text or JOIN_REGEX.search(text) or DROP_REGEX.search(text))


# Saludos cortos y estrictos: solo estos disparan el mensaje institucional fijo de bienvenida
GREETING_ONLY_PATTERNS = [
    r"^hola+$",
    r"^ho+la+$",
    r"^buenas?$",
    r"^buen[oa]s?\s+d[ií]as?$",
    r"^buenas?\s+tardes?$",
    r"^buenas?\s+noches?$",
    r"^inicio$",
    r"^start$",
    r"^hey$",
    r"^hi$",
    r"^saludos$",
]
GREETING_ONLY_REGEX = re.compile("|".join(GREETING_ONLY_PATTERNS), re.IGNORECASE)

QUICK_AVAILABILITY_KEYWORDS = [
    r"\breservas?\b",
    r"\bdisponibilidad\b",
    r"\bturnos?\b",
    r"\bcanchas?\s+libres?\b",
    r"\bhorarios?\b",
]
QUICK_AVAILABILITY_REGEX = re.compile("|".join(QUICK_AVAILABILITY_KEYWORDS), re.IGNORECASE)

WELCOME_MESSAGE = (
    "🎾 *¡Hola! Bienvenido a Capital Pádel Club* 🎾\n\n"
    "Somos el equipo de Capital Pádel Club, sede Complejo Maloka en Bogotá. "
    "Con gusto te ayudamos con reservas, torneos o servicios del club.\n\n"
    "¿En qué te podemos colaborar hoy?"
)


def is_simple_greeting(text: str) -> bool:
    """True solo si el mensaje ES, en su totalidad, un saludo corto ('hola', 'buenas', 'buenos días', 'inicio', 'start', etc.)."""
    if not text:
        return False
    clean = text.strip().lower()
    clean = re.sub(r"[^\w\sáéíóúñ]", "", clean, flags=re.UNICODE).strip()
    if not clean or len(clean.split()) > 3:
        return False
    return bool(GREETING_ONLY_REGEX.match(clean))


def _local_concierge_fallback(clean_text: str) -> str:
    """Respuestas de conocimiento del club sin depender de Gemini (usadas si la IA no está configurada o falla)."""
    t = clean_text.lower()
    if re.search(r"\bcu[aá]nt[ao]s?\b.*\bcanchas?\b|\bcanchas?\b.*\btienen\b", t):
        return (
            "🎾 *Nuestras instalaciones en Capital Pádel Club:*\n\n"
            "• 5 canchas de pádel (4 azules + 1 negra)\n"
            "• 2 pistas de pickleball 🏓\n"
            "• 1 cancha de arena para vóley 🏐\n"
            "• Sala de consolas 🎮\n\n"
            "¿Quieres que te muestre la disponibilidad de hoy?"
        )
    if re.search(r"\bservicios?\b|\bqu[eé]\s+hay\b|\bofrecen\b", t):
        return (
            "🏆 *Servicios de Capital Pádel Club:*\n\n"
            "• Tienda/POS: venta y alquiler de palas y bolas 🎾\n"
            "• Bar / Cafetería\n"
            "• Vestieres\n"
            "• Parqueadero cubierto 🚗\n"
            "• Torneos Americanos, Academia y partidos abiertos comunitarios\n\n"
            "¿Te gustaría conocer horarios o disponibilidad?"
        )
    if re.search(r"\bprecios?\b|\bvalor(es)?\b|\bcu[aá]nto\s+cuesta\b|\btarifas?\b", t):
        return (
            "💰 *Tarifas en Capital Pádel Club:*\n\n"
            "Nuestras tarifas varían según la franja horaria (valle/pico) y la cancha. "
            "Escribe *'disponibilidad'* o *'turnos hoy'* y te muestro los horarios con su precio exacto en COP. 🎾"
        )
    if re.search(r"\bd[oó]nde\b|\bubicad[oa]s?\b|\bdirecci[oó]n\b|\bqueda[n]?\b", t):
        return (
            "📍 *Ubicación de Capital Pádel Club:*\n\n"
            "Estamos en el Complejo Maloka, Bogotá D.C. ¡Te esperamos! 🎾"
        )
    if re.search(r"\bhorarios?\b|\ba\s+qu[eé]\s+hora\b|\babren\b|\bcierran\b", t):
        return (
            "⌚ *Horario de Capital Pádel Club:*\n\n"
            "Todos los días de 06:00 a.m. a 12:00 a.m. (medianoche). "
            "El último turno inicia a las 22:00/22:30. 🎾"
        )
    return (
        "🎾 *Capital Pádel Club* 🎾\n\n"
        "Puedo ayudarte con reservas, torneos o servicios del club. Por ejemplo, pregúntame:\n"
        "• *'cuántas canchas tienen'*\n"
        "• *'qué servicios hay'*\n"
        "• *'disponibilidad de hoy'*\n\n"
        "¡Cuéntame en qué te ayudo! 🏆"
    )

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

AVAILABILITY_KEYWORDS = [
    r"\bqu[eé]\s+horas?\s+hay\b",
    r"\bcanchas?\s+libres?\b",
    r"\bpistas?\s+libres?\b",
    r"\bhay\s+turno\b",
    r"\bhay\s+turnos\b",
    r"\bhay\s+cancha\b",
    r"\bhay\s+pista\b",
    r"\bdisponibilidad\b",
    r"\bqu[eé]\s+turnos?\s+tienen\b",
    r"\bhorarios?\s+disponibles?\b",
    r"\bqu[eé]\s+hay\s+hoy\b",
    r"\bqu[eé]\s+hay\s+disponible\b",
]
AVAILABILITY_REGEX = re.compile("|".join(AVAILABILITY_KEYWORDS), re.IGNORECASE)

import importlib
yield_mod = importlib.import_module("app.services.yield")
calculate_recommended_price = yield_mod.calculate_recommended_price

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


def detect_sport_from_text(text: str) -> str:
    """
    Detecta el deporte a partir del texto:
    - CONSOLE: si contiene 🎮 o 'consola'/'videojuegos'/'gaming'/'fifa'/'esports'.
    - VOLLEYBALL: si contiene 🏐 o 'volleyball'/'voley'/'voleibol'.
    - PICKLEBALL: si contiene 🏓 o 'pickleball'.
    - PILATES: si contiene 🧘 o 'pilates'.
    - PADEL: si contiene 🎾 o 'padel'/'pádel' o por defecto.
    """
    if not text:
        return "PADEL"
    clean = text.lower()
    if "🎮" in text or re.search(r"\b(?:consola|videojuego[s]?|gaming|esports?|fifa)\b", clean):
        return "CONSOLE"
    if "🏐" in text or re.search(r"\b(?:volleyball|v[oó]ley|voleibol)\b", clean):
        return "VOLLEYBALL"
    if "🏓" in text or re.search(r"\bpickleball\b", clean):
        return "PICKLEBALL"
    if "🧘" in text or re.search(r"\bpilates\b", clean):
        return "PILATES"
    if "🎾" in text or re.search(r"\b(?:p[aá]del|padel)\b", clean):
        return "PADEL"
    return "PADEL"


def get_sport_emoji(sport_type: Optional[str]) -> str:
    """Retorna el emoji correspondiente al deporte."""
    s = (sport_type or "PADEL").upper()
    if s == "VOLLEYBALL":
        return "🏐"
    elif s == "PICKLEBALL":
        return "🏓"
    elif s == "PILATES":
        return "🧘"
    elif s in ("CONSOLE", "GAMING"):
        return "🎮"
    return "🎾"


def get_sport_default_capacity(sport_type: Optional[str]) -> int:
    """Retorna la capacidad estándar por deporte: Pádel/Pickleball/Consola=4, Vóley/Pilates=12."""
    s = (sport_type or "PADEL").upper()
    if s in ("VOLLEYBALL", "PILATES"):
        return 12
    return 4



def detect_intent(text: str) -> str:
    """Clasifica el mensaje en 'DROP', 'JOIN', 'AVAILABILITY', 'LIST' o 'UNKNOWN'."""
    clean = text.strip()
    if DROP_REGEX.search(clean):
        return "DROP"
    if JOIN_REGEX.search(clean):
        return "JOIN"
    if AVAILABILITY_REGEX.search(clean) or any(w in clean.lower() for w in ["que horas hay", "qué horas hay", "canchas libres", "cancha libre", "pistas libres", "hay turno", "disponibilidad"]):
        return "AVAILABILITY"
    if any(em in clean for em in ["🎾", "🏐", "🏓", "🧘"]) or ("1." in clean and "2." in clean) or ("cancha" in clean.lower() and any(k in clean.lower() for k in ["4ta", "voley", "vóley", "pilates", "pickleball"])):
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


def parse_flexible_player_list(raw_text: str, max_capacity: int = 12) -> List[str]:
    """
    Detección flexible de nombres en listas multideporte:
    Reconoce jugadores con 🎾, 🏐, 🏓, 🧘 o cualquier viñeta, descartando exhaustivamente
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
        elif "🏐" in stripped:
            candidate = stripped.split("🏐", 1)[1].strip()
        elif "🏓" in stripped:
            candidate = stripped.split("🏓", 1)[1].strip()
        elif "🧘" in stripped:
            candidate = stripped.split("🧘", 1)[1].strip()
        elif "👤" in stripped:
            candidate = stripped.split("👤", 1)[1].strip()
        else:
            candidate = stripped

        valid_name = clean_player_name(candidate)
        if valid_name and valid_name not in players:
            players.append(valid_name)
            if len(players) >= max_capacity:
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
    detected_sport = detect_sport_from_text(quoted_text or raw_text)

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
            matching_slots = res.scalars().all()
            if matching_slots:
                if len(matching_slots) > 1:
                    clean_quoted = quoted_text.lower()
                    # Priorizar coincidencia exacta de deporte
                    for s in matching_slots:
                        s_sport = getattr(s, "sport_type", None) or (s.court.sport_type if s.court else "PADEL")
                        if s_sport == detected_sport:
                            return s
                    for s in matching_slots:
                        c_name = (s.court.name.lower() if s.court else "")
                        c_num = str(getattr(s.court, "court_number", "")) if s.court else ""
                        if c_name and c_name in clean_quoted:
                            return s
                        if c_num and (f"cancha {c_num}" in clean_quoted or f"pista {c_num}" in clean_quoted):
                            return s
                return matching_slots[0]

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
        matching_slots = res.scalars().all()
        if matching_slots:
            for s in matching_slots:
                s_sport = getattr(s, "sport_type", None) or (s.court.sport_type if s.court else "PADEL")
                if s_sport == detected_sport:
                    return s
            return matching_slots[0]

    # d) Turno abierto más próximo (priorizando deporte detectado)
    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
        .where(TimeSlot.date >= today)
        .order_by(TimeSlot.date.asc(), TimeSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    all_slots = res.scalars().all()
    sport_candidate = None
    fallback_candidate = None
    for s in all_slots:
        if getattr(s, "slot_type", "MATCH") in ("CLASS", "ACADEMY", "MAINTENANCE"):
            continue
        mode_val = s.mode.value if hasattr(s.mode, "value") else str(s.mode)
        status_val = s.status.value if hasattr(s.status, "value") else str(s.status)
        if mode_val == "SPLIT_MATCH" and status_val in ("AVAILABLE", "PARTIALLY_BOOKED"):
            if s.booked_spots < s.capacity:
                s_sport = getattr(s, "sport_type", None) or (s.court.sport_type if s.court else "PADEL")
                if s_sport == detected_sport and sport_candidate is None:
                    sport_candidate = s
                elif fallback_candidate is None:
                    fallback_candidate = s

    return sport_candidate or fallback_candidate


def format_whatsapp_reply(slot: TimeSlot) -> str:
    """
    Genera el mensaje oficial de WhatsApp garantizando la inmutabilidad de tarifa y sede,
    con soporte multideporte (Pádel 🎾, Pickleball 🏓, Vóley 🏐 y Pilates 🧘) y tarifa
    prorrateada dinámica para Vóley ($120.000 COP / count(jugadores_inscritos)).
    """
    date_str = slot.date.strftime("%d/%m/%Y")
    start_str = slot.start_time.strftime("%I:%M%p").lower()
    end_str = slot.end_time.strftime("%I:%M%p").lower()

    try:
        court_name = slot.court.name if (hasattr(slot, "court") and slot.court) else "Capital Pádel Club"
    except Exception:
        court_name = "Capital Pádel Club"
    category = slot.category or "4ta"

    sport = getattr(slot, "sport_type", None) or (slot.court.sport_type if getattr(slot, "court", None) and getattr(slot.court, "sport_type", None) else "PADEL")
    sport_emoji = get_sport_emoji(sport)

    participants = to_participants_list(slot.players_names)
    spots_count = len(participants)
    free_spots = max(0, slot.capacity - spots_count)
    is_closed = (spots_count >= slot.capacity)

    # Tarifa y cuota
    if sport == "VOLLEYBALL":
        total_court_price = slot.total_price if slot.total_price > 0 else Decimal("120000.00")
        if spots_count > 0:
            price_per_spot = (total_court_price / Decimal(spots_count)).quantize(Decimal("0.01"))
        else:
            price_per_spot = (total_court_price / Decimal(slot.capacity)).quantize(Decimal("0.01"))
        price_formatted = f"{int(price_per_spot):,}".replace(",", ".")
        total_formatted = f"{int(total_court_price):,}".replace(",", ".")
        price_line = f"💰 Cuota Prorrateada: ${price_formatted} COP / jugador ({spots_count} inscritos pagan ${total_formatted} COP total)"
    else:
        price_per_spot = (slot.total_price / Decimal(slot.capacity)).quantize(Decimal("0.01"))
        price_formatted = f"{int(price_per_spot):,}".replace(",", ".")
        price_line = f"💰 Cuota: ${price_formatted} COP / jugador"

    if is_closed:
        players_lines = "\n".join([f"{i}. {sport_emoji} {p['display_name']}" for i, p in enumerate(participants, start=1)])
        header_title = f"✅ ¡PARTIDO CERRADO Y CONFIRMADO! ({slot.capacity}/{slot.capacity}) {sport_emoji}"
        if sport == "PILATES":
            header_title = f"✅ ¡CLASE DE PILATES COMPLETA! ({slot.capacity}/{slot.capacity}) 🧘"
        return (
            f"{header_title}\n"
            f"📍 {court_name}\n"
            f"📅 {date_str} | ⌚ {start_str} - {end_str}\n"
            f"🏆 Categoría: {category}\n"
            f"{price_line}\n\n"
            f"👥 *Jugadores Confirmados ({slot.capacity}/{slot.capacity}):*\n"
            f"{players_lines}\n\n"
            f"🔒 *Espacio asegurado en sistema. ¡Nos vemos en la pista!*"
        )
    else:
        player_entries = []
        for i, p in enumerate(participants, start=1):
            player_entries.append(f"{i}. {sport_emoji} {p['display_name']}")
        for i in range(spots_count + 1, slot.capacity + 1):
            player_entries.append(f"{i}. ⚡ [CUPO DISPONIBLE]")

        players_lines = "\n".join(player_entries)
        header_title = f"{sport_emoji} PARTIDO ABIERTO ({spots_count}/{slot.capacity})"
        if sport == "PILATES":
            header_title = f"🧘 CLASE DE PILATES ABIERTA ({spots_count}/{slot.capacity})"
        return (
            f"{header_title}\n"
            f"📍 {court_name}\n"
            f"📅 {date_str} | ⌚ {start_str} - {end_str}\n"
            f"🏆 Categoría: {category}\n"
            f"{price_line}\n\n"
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

    if getattr(slot, "slot_type", "MATCH") in ("CLASS", "ACADEMY"):
        date_str = slot.date.strftime("%d/%m/%Y")
        start_str = slot.start_time.strftime("%I:%M%p").lower()
        end_str = slot.end_time.strftime("%I:%M%p").lower()
        prof_txt = f" con el profesor {slot.instructor_name}" if slot.instructor_name else ""
        return (
            "⚠️ *TURNO RESERVADO PARA CLASE / ACADEMIA* ⚠️\n"
            f"El bloque de las {start_str} - {end_str} ({date_str}){prof_txt} corresponde a una sesión de entrenamiento.\n"
            "Las inscripciones abiertas por WhatsApp están deshabilitadas para este horario. Comunícate directamente con recepción."
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
    elif intent == "AVAILABILITY":
        return await process_availability_query(db, target_date=None, query_text=raw_text)
    elif intent == "LIST":
        return await process_list_intent(db, sender_phone, sender_name, raw_text)
    else:
        return await generate_concierge_reply(message_text=raw_text, sender_phone=sender_phone, db=db)


async def process_availability_query(
    db: AsyncSession,
    target_date: Optional[date] = None,
    query_text: Optional[str] = None,
) -> str:
    """
    Responde a consultas de disponibilidad ('qué horas hay', 'canchas libres', 'hay turno'):
    Pide la franja de interés y lista las pistas disponibles del día con tarifas recomendadas de Yield.
    """
    today = get_bogota_today()
    now_bogota = get_bogota_now()
    d = target_date or today
    date_str = d.strftime("%d/%m/%Y")
    label_day = "Hoy" if d == today else d.strftime("%A").capitalize()

    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court))
        .where(
            TimeSlot.date == d,
            cast(TimeSlot.status, String) == "AVAILABLE",
            TimeSlot.slot_type == "MATCH",
        )
        .order_by(TimeSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    slots = list(res.scalars().all())

    if d == today:
        current_time = now_bogota.time()
        slots = [s for s in slots if s.start_time > current_time]

    if not slots:
        return (
            f"🎾 *DISPONIBILIDAD - CAPITAL PÁDEL CLUB* 🎾\n\n"
            f"📅 Fecha: *{label_day} ({date_str})*\n"
            f"En este momento todas nuestras pistas se encuentran reservadas para esta jornada.\n\n"
            f"💡 ¿Deseas consultar la disponibilidad de *Mañana* o anotarte en lista de espera? Comunícate con recepción."
        )

    # Agrupar por franja horaria
    morning_slots = [s for s in slots if s.start_time < time(12, 0)]
    afternoon_slots = [s for s in slots if time(12, 0) <= s.start_time < time(18, 0)]
    night_slots = [s for s in slots if s.start_time >= time(18, 0)]

    sections = []

    def format_slot_line(s: TimeSlot) -> str:
        c_name = s.court.name if s.court else "Cancha"
        st = s.start_time.strftime("%I:%M%p").lower()
        et = s.end_time.strftime("%I:%M%p").lower()
        yd = calculate_recommended_price(s)
        p_cop = f"${int(yd['recommended_price']):,}".replace(",", ".")
        tier_tag = "🔥 Pico" if yd["is_pico"] else "🌿 Valle"
        if yd["is_promo"]:
            tier_tag = "⚡ PROMO FLASH (-25%)"
        return f"• *{st} - {et}* | {c_name} ➔ *{p_cop} COP* ({tier_tag})"

    if morning_slots:
        m_lines = "\n".join([format_slot_line(s) for s in morning_slots[:4]])
        sections.append(f"☀️ *Mañana (< 12:00m):*\n{m_lines}")

    if afternoon_slots:
        a_lines = "\n".join([format_slot_line(s) for s in afternoon_slots[:4]])
        sections.append(f"🌤️ *Tarde (12:00m - 06:00pm):*\n{a_lines}")

    if night_slots:
        n_lines = "\n".join([format_slot_line(s) for s in night_slots[:4]])
        sections.append(f"🌙 *Noche / Prime (> 06:00pm):*\n{n_lines}")

    body_sections = "\n\n".join(sections)
    return (
        f"🎾 *DISPONIBILIDAD DE PISTAS - CAPITAL PÁDEL CLUB* 🎾\n"
        f"📅 Fecha: *{label_day} ({date_str})*\n\n"
        f"¿En qué franja te gustaría jugar? Puedes reservar respondiendo a este mensaje:\n\n"
        f"{body_sections}\n\n"
        f"💬 *¿Cómo reservar?* Responde citando el turno o escribe *'VOY [Hora] [Cancha]'* para apartar de inmediato."
    )


async def generate_quick_availability_reply(
    db: AsyncSession,
    target_date: Optional[date] = None,
) -> str:
    """
    Respuesta compacta (3-4 turnos) para preguntas rápidas de disponibilidad
    ('reservas', 'disponibilidad', 'turnos', 'canchas libres', 'horarios').
    """
    today = get_bogota_today()
    now_bogota = get_bogota_now()
    d = target_date or today
    day_label = "hoy" if d == today else "mañana"

    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court))
        .where(
            TimeSlot.date == d,
            cast(TimeSlot.status, String) == "AVAILABLE",
            TimeSlot.slot_type == "MATCH",
        )
        .order_by(TimeSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    slots = list(res.scalars().all())

    if d == today:
        current_time = now_bogota.time()
        slots = [s for s in slots if s.start_time > current_time]

    if not slots:
        if d == today:
            return "Por el momento todas las canchas están reservadas para hoy. ¿Te gustaría consultar para mañana?"
        return "Por el momento todas las canchas están reservadas para mañana. ¿Deseas consultar otra fecha?"

    lines = []
    for s in slots[:4]:
        c_name = s.court.name if s.court else "Cancha"
        st = s.start_time.strftime("%I:%M %p").lstrip("0")
        et = s.end_time.strftime("%I:%M %p").lstrip("0")
        price = f"${int(s.total_price or 0):,}".replace(",", ".")
        lines.append(f"• {st} - {et} ({c_name} - {price} COP)")

    lines_str = "\n".join(lines)
    return (
        f"🎾 *Turnos libres para {day_label} en Capital Pádel Club:*\n"
        f"{lines_str}\n\n"
        f"Escribe la hora que prefieres para apartarla de inmediato."
    )


async def generate_concierge_reply(
    message_text: str,
    sender_phone: str,
    db: Optional[AsyncSession] = None,
) -> str:
    """
    Concierge conversacional (Gemini) con conocimiento institucional del club.
    - Saludo corto y estricto ('hola', 'buenas', 'inicio', 'start'...) -> mensaje de bienvenida fijo.
    - Pregunta de disponibilidad/reservas -> consulta real a time_slots (formato compacto).
    - Resto de preguntas en lenguaje natural -> Gemini (o base de conocimiento local si Gemini no está disponible).
    """
    clean = (message_text or "").strip()

    if is_simple_greeting(clean):
        return WELCOME_MESSAGE

    if db is not None and (detect_intent(clean) == "AVAILABILITY" or QUICK_AVAILABILITY_REGEX.search(clean)):
        target_date = get_bogota_today()
        if re.search(r"\bma[ñn]ana\b", clean, re.IGNORECASE):
            target_date = target_date + timedelta(days=1)
        return await generate_quick_availability_reply(db, target_date=target_date)

    api_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not genai or not api_key:
        logger.warning("Gemini no configurado (falta google-generativeai o GEMINI_API_KEY); usando base de conocimiento local.")
        return _local_concierge_fallback(clean)

    try:
        model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=CONCIERGE_SYSTEM_INSTRUCTION,
        )
        response = await model.generate_content_async(clean or "hola")
        ai_text = (getattr(response, "text", None) or "").strip()
        if not ai_text:
            raise ValueError("Respuesta vacía de Gemini")
        return ai_text
    except Exception as exc:
        logger.error(f"Error generando respuesta de concierge IA para {sender_phone}: {exc}", exc_info=True)
        return _local_concierge_fallback(clean)


async def generate_availability_broadcast(
    db: AsyncSession,
    target_date: Optional[date] = None,
) -> Tuple[str, int]:
    """
    Genera el resumen de turnos clave libres del día para despacho masivo al grupo de WhatsApp.
    """
    today = get_bogota_today()
    d = target_date or today
    date_str = d.strftime("%d/%m/%Y")
    now_bogota = get_bogota_now()

    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court))
        .where(
            TimeSlot.date == d,
            cast(TimeSlot.status, String) == "AVAILABLE",
            TimeSlot.slot_type == "MATCH",
        )
        .order_by(TimeSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    slots = list(res.scalars().all())

    if d == today:
        current_time = now_bogota.time()
        slots = [s for s in slots if s.start_time > current_time]

    total_free = len(slots)
    if total_free == 0:
        msg = (
            f"🎾 *ESTADO DE PISTAS - CAPITAL PÁDEL CLUB* 🎾\n\n"
            f"📅 Hoy {date_str}: ¡Canchas al 100% de ocupación!\n"
            f"Agradecemos a toda la comunidad. Consulta los turnos abiertos de mañana en recepción."
        )
        return msg, 0

    featured = slots[:6]
    lines = []
    for s in featured:
        c_name = s.court.name if s.court else "Cancha"
        st = s.start_time.strftime("%I:%M%p").lower()
        et = s.end_time.strftime("%I:%M%p").lower()
        yd = calculate_recommended_price(s)
        p_cop = f"${int(yd['recommended_price']):,}".replace(",", ".")
        tier_str = "🔥 Pico" if yd["is_pico"] else "🌿 Valle"
        if yd["is_promo"]:
            tier_str = "⚡ PROMO FLASH (-25%)"
        lines.append(f"📍 {c_name} | ⌚ *{st} - {et}* ➔ *{p_cop} COP* ({tier_str})")

    slots_text = "\n".join(lines)
    msg = (
        f"📢 *TURNOS DISPONIBLES DE PÁDEL HOY ({date_str})* 🎾\n"
        f"¡Asegura tu cancha o partido abierto antes de que se agoten!\n\n"
        f"{slots_text}\n\n"
        f"⚡ *Quedan {total_free} bloques disponibles en el club.*\n"
        f"💬 Responde directamente a este mensaje con *'VOY [Hora]'* para apartar tu cupo."
    )
    return msg, total_free


async def generate_promo_urgent_broadcast(
    db: AsyncSession,
    target_date: Optional[date] = None,
) -> Tuple[str, int]:
    """
    Filtra los slots vacíos más críticos (< 3 horas para el inicio) y genera
    una alerta con precio de descuento '⚡ PROMO FLASH YIELD (-25%)'.
    """
    today = get_bogota_today()
    now_bogota = get_bogota_now()
    d = target_date or today
    date_str = d.strftime("%d/%m/%Y")

    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court))
        .where(
            TimeSlot.date == d,
            cast(TimeSlot.status, String) == "AVAILABLE",
            TimeSlot.slot_type == "MATCH",
        )
        .order_by(TimeSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    slots = list(res.scalars().all())

    urgent_slots = []
    for s in slots:
        slot_dt = datetime.combine(s.date, s.start_time).replace(tzinfo=BOGOTA_TZ)
        mins = (slot_dt - now_bogota).total_seconds() / 60
        if 0 < mins <= 180:
            urgent_slots.append(s)

    if not urgent_slots:
        # Fallback a próximos turnos libres del día
        future_slots = [s for s in slots if datetime.combine(s.date, s.start_time).replace(tzinfo=BOGOTA_TZ) > now_bogota][:2]
        if not future_slots:
            future_slots = slots[:2]
        if not future_slots:
            msg = (
                f"⚡ *REMATE DE CANCHAS - YIELDPADEL* ⚡\n\n"
                f"📅 {date_str}: No hay turnos críticos libres en este momento. ¡Todas las pistas próximas están confirmadas!"
            )
            return msg, 0
        urgent_slots = future_slots

    lines = []
    for s in urgent_slots:
        c_name = s.court.name if s.court else "Cancha"
        st = s.start_time.strftime("%I:%M%p").lower()
        et = s.end_time.strftime("%I:%M%p").lower()
        yd = calculate_recommended_price(s)
        base_p = f"${int(yd['base_price']):,}".replace(",", ".")
        promo_p = f"${int(yd['recommended_price']):,}".replace(",", ".")
        lines.append(
            f"🔥 *{c_name}* | ⌚ *{st} - {et}*\n"
            f"   💰 Tarifa Regular: ~{base_p}~ ➔ *PROMO FLASH: {promo_p} COP* (⚡ -{yd['discount_percent']}%)"
        )

    slots_text = "\n\n".join(lines)
    msg = (
        f"⚡ *¡REMATE FLASH YIELD - ÚLTIMA HORA!* ⚡\n"
        f"🚨 *Turnos con descuento especial para jugar hoy* en Capital Pádel Club:\n\n"
        f"{slots_text}\n\n"
        f"🏃‍♂️ *¡Aprovecha antes de que se ocupen!* Responde inmediatamente *'VOY [Hora]'* para bloquear tu pista al instante."
    )
    return msg, len(urgent_slots)


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
