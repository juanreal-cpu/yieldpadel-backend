"""
YieldPadel - Yield Management & Dynamic Pricing Engine
Calcula precios dinámicos según franja horaria (Valle vs Pico), fines de semana,
descuentos promocionales de última hora (Last-Minute Promo < 3h) y pisos de seguridad.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from app.core.timezone import BOGOTA_TZ, get_bogota_now

# Constantes de Precios Base y Promocionales
VALLE_BASE_PRICE = Decimal("80000.00")   # $80.000 COP / cancha ($20.000 / cupo)
PICO_BASE_PRICE = Decimal("120000.00")   # $120.000 COP / cancha ($30.000 / cupo)

VALLE_PROMO_PRICE = Decimal("60000.00")  # Descuento -25% Last-Minute ($15.000 / cupo)
PICO_PROMO_PRICE = Decimal("90000.00")   # Descuento -25% Last-Minute ($22.500 / cupo)

DEFAULT_MIN_SAFETY_PRICE = Decimal("60000.00")  # Piso mínimo de seguridad

# Estado de Configuración del Club en Caliente
CLUB_SETTINGS: Dict[str, Any] = {
    "valle_price": Decimal("80000.00"),
    "pico_price": Decimal("120000.00"),
    "min_safety_price": Decimal("60000.00"),
    "padel_valle": Decimal("80000.00"),
    "padel_pico": Decimal("120000.00"),
    "padel_floor": Decimal("60000.00"),
    "pickleball_valle": Decimal("50000.00"),
    "pickleball_pico": Decimal("80000.00"),
    "volleyball_individual": Decimal("15000.00"),
    "volleyball_base": Decimal("120000.00"),
    "pilates_per_mat": Decimal("35000.00"),
    "promo_discount_percent": 25,
    "cancellation_grace_minutes": 30,
    "confirmation_grace_minutes": 10,
    "whatsapp_group_id": "573132058547",
}


def get_club_config() -> Dict[str, Any]:
    """Retorna la configuración operativa actual del club."""
    valle = float(CLUB_SETTINGS["valle_price"])
    pico = float(CLUB_SETTINGS["pico_price"])
    floor = float(CLUB_SETTINGS["min_safety_price"])
    group = str(CLUB_SETTINGS["whatsapp_group_id"])
    return {
        "valle_price": valle,
        "base_valle": valle,
        "pico_price": pico,
        "base_pico": pico,
        "min_safety_price": floor,
        "safety_floor": floor,
        "padel_valle": float(CLUB_SETTINGS.get("padel_valle", 80000.0)),
        "padel_pico": float(CLUB_SETTINGS.get("padel_pico", 120000.0)),
        "padel_floor": float(CLUB_SETTINGS.get("padel_floor", 60000.0)),
        "pickleball_valle": float(CLUB_SETTINGS.get("pickleball_valle", 50000.0)),
        "pickleball_pico": float(CLUB_SETTINGS.get("pickleball_pico", 80000.0)),
        "volleyball_individual": float(CLUB_SETTINGS.get("volleyball_individual", 15000.0)),
        "volleyball_base": float(CLUB_SETTINGS.get("volleyball_base", 120000.0)),
        "pilates_per_mat": float(CLUB_SETTINGS.get("pilates_per_mat", 35000.0)),
        "promo_discount_percent": int(CLUB_SETTINGS["promo_discount_percent"]),
        "cancellation_grace_minutes": int(CLUB_SETTINGS["cancellation_grace_minutes"]),
        "confirmation_grace_minutes": int(CLUB_SETTINGS["confirmation_grace_minutes"]),
        "whatsapp_group_id": group,
        "broadcast_group_id": group,
    }


def update_club_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza en memoria la parametrización operativa del club."""
    # Map aliases
    if "base_valle" in updates and "valle_price" not in updates:
        updates["valle_price"] = updates["base_valle"]
    if "base_pico" in updates and "pico_price" not in updates:
        updates["pico_price"] = updates["base_pico"]
    if "safety_floor" in updates and "min_safety_price" not in updates:
        updates["min_safety_price"] = updates["safety_floor"]
    if "broadcast_group_id" in updates and "whatsapp_group_id" not in updates:
        updates["whatsapp_group_id"] = updates["broadcast_group_id"]
    if "padel_valle" in updates and "valle_price" not in updates:
        updates["valle_price"] = updates["padel_valle"]
    if "padel_pico" in updates and "pico_price" not in updates:
        updates["pico_price"] = updates["padel_pico"]
    if "padel_floor" in updates and "min_safety_price" not in updates:
        updates["min_safety_price"] = updates["padel_floor"]

    for k, v in updates.items():
        if v is not None and k in CLUB_SETTINGS:
            if "price" in k or "valle" in k or "pico" in k or "floor" in k or "base" in k or "mat" in k or "indiv" in k or "volleyball" in k:
                CLUB_SETTINGS[k] = Decimal(str(v))
            else:
                CLUB_SETTINGS[k] = v
    return get_club_config()


def is_pico_hour(target_date: date, start_time: time) -> bool:
    """
    Determina si una fecha y hora corresponden a Horario Pico:
    - Fines de semana (Sábado=5 y Domingo=6): Todo el día es Pico.
    - Lunes a Viernes (0 a 4): Pico si el inicio es a partir de las 18:00 (6:00pm).
    """
    # weekday: Monday is 0 and Sunday is 6
    if target_date.weekday() in (5, 6):
        return True
    return start_time.hour >= 18


def calculate_recommended_price(
    slot: Any,
    current_time: Optional[datetime] = None,
    min_safety_price: Optional[Decimal] = None,
    promo_discount_percent: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """
    Calcula el precio recomendado por el motor de Yield Management:
    1. Horario Valle (semana < 18:00): $80.000 COP / cancha ($20.000 COP / cupo).
    2. Horario Pico (semana >= 18:00 o fines de semana): $120.000 COP / cancha ($30.000 COP / cupo).
    3. Regla Last-Minute Promo:
       Si slot.status == 'AVAILABLE' (sin cupos tomados) y faltan menos de 3 horas
       para el inicio hoy en hora Bogotá, aplica descuento yield parametrizable (default -25%):
       - Valle: $60.000 COP / cancha ($15.000 COP / cupo).
       - Pico: $90.000 COP / cancha ($22.500 COP / cupo).
       y marca is_promo = True.
    4. Piso de Seguridad: Garantiza que ningún precio descienda del valor mínimo configurado.
    """
    now = current_time or get_bogota_now()
    today = now.date()

    # Extraer fecha, hora y estado del slot
    slot_date = getattr(slot, "date", today)
    start_t = getattr(slot, "start_time", time(18, 0))
    slot_status = getattr(slot, "status", "AVAILABLE")
    if hasattr(slot_status, "value"):
        slot_status = slot_status.value
    booked_spots = getattr(slot, "booked_spots", 0)
    if booked_spots is None:
        booked_spots = 0

    # 1. Determinar Pico vs Valle
    pico = is_pico_hour(slot_date, start_t)
    sport = getattr(slot, "sport_type", None) or (getattr(getattr(slot, "court", None), "sport_type", None) or "PADEL")

    if sport == "VOLLEYBALL":
        base_price = Decimal("120000.00")
    else:
        base_valle = CLUB_SETTINGS.get("valle_price", VALLE_BASE_PRICE)
        base_pico = CLUB_SETTINGS.get("pico_price", PICO_BASE_PRICE)
        base_price = base_pico if pico else base_valle

    # 2. Evaluar Last-Minute Promo (< 3 horas hoy para turnos sin vender)
    is_promo = False
    discount_applied = Decimal("0.00")
    discount_percent = 0
    tier = "PICO" if pico else "VALLE"

    is_available = (slot_status == "AVAILABLE" and booked_spots == 0)

    if is_available and slot_date == today:
        # Calcular minutos faltantes hasta el inicio
        slot_dt = datetime.combine(slot_date, start_t).replace(tzinfo=BOGOTA_TZ)
        now_localized = now if now.tzinfo else now.replace(tzinfo=BOGOTA_TZ)
        mins_until_start = (slot_dt - now_localized).total_seconds() / 60

        if 0 < mins_until_start <= 180:  # Menos de 3 horas
            is_promo = True
            default_discount = CLUB_SETTINGS.get("promo_discount_percent", 25)
            discount_percent = int(promo_discount_percent) if promo_discount_percent is not None else default_discount
            pct = Decimal(str(discount_percent))
            discount_applied = (base_price * pct / Decimal("100")).quantize(Decimal("1.00"))
            recommended_price = base_price - discount_applied
            tier = "LAST_MINUTE_PROMO_PICO" if pico else "LAST_MINUTE_PROMO_VALLE"
        else:
            recommended_price = base_price
    else:
        recommended_price = base_price

    # 3. Aplicar piso mínimo de seguridad
    floor_price = min_safety_price if min_safety_price is not None else CLUB_SETTINGS.get("min_safety_price", DEFAULT_MIN_SAFETY_PRICE)
    if recommended_price < floor_price:
        recommended_price = floor_price

    # 4. Calcular precio por cupo (cancha estándar de 4 jugadores o tarifa prorrateada dinámica para Vóley)
    capacity = getattr(slot, "capacity", 4) or 4
    if sport == "VOLLEYBALL":
        players_list = getattr(slot, "players_names", None) or []
        count_p = len(players_list) if isinstance(players_list, list) else 0
        if count_p > 0:
            price_per_spot = (recommended_price / Decimal(count_p)).quantize(Decimal("1.00"))
        else:
            price_per_spot = (recommended_price / Decimal(capacity)).quantize(Decimal("1.00"))
    else:
        price_per_spot = (recommended_price / Decimal(capacity)).quantize(Decimal("1.00"))

    # Explicación para recepción y logs
    if is_promo:
        explanation = (
            f"⚡ Promo Last-Minute (-{discount_percent}%): Faltan menos de 3h para el turno libre hoy. "
            f"Tarifa optimizada de ${int(base_price):,} a ${int(recommended_price):,} COP."
        )
    elif pico:
        if slot_date.weekday() in (5, 6):
            explanation = "🔥 Horario Pico Fin de Semana: Tarifa completa de alta demanda ($120.000 COP)."
        else:
            explanation = "🔥 Horario Pico Nocturno (>= 18:00): Alta demanda prime time ($120.000 COP)."
    else:
        explanation = "☀️ Horario Valle Diurno (< 18:00): Tarifa accesible para fomento de ocupación ($80.000 COP)."

    return {
        "recommended_price": recommended_price,
        "price_per_spot": price_per_spot,
        "recommended_price_per_spot": price_per_spot,
        "base_price": base_price,
        "is_pico": pico,
        "is_valle": not pico,
        "is_promo": is_promo,
        "pricing_tier": tier,
        "discount_applied": discount_applied,
        "savings": discount_applied,
        "discount_percent": discount_percent,
        "promo_discount_percent": discount_percent,
        "safety_floor": floor_price,
        "explanation": explanation,
    }
