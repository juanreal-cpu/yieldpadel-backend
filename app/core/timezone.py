"""
YieldPadel - Timezone Configuration
Garantiza el uso correcto de la zona horaria de Colombia (America/Bogota, UTC-5)
tanto en entornos locales como en despliegues cloud (Render, AWS, Docker) que corren en UTC.
"""

from datetime import date, datetime, time, timedelta, timezone
from fastapi import HTTPException, status

try:
    from zoneinfo import ZoneInfo
    BOGOTA_TZ = ZoneInfo("America/Bogota")
except Exception:
    BOGOTA_TZ = timezone(timedelta(hours=-5))


def get_bogota_now() -> datetime:
    """
    Retorna la fecha y hora actual en la zona horaria de Colombia ('America/Bogota').
    """
    try:
        return datetime.now(BOGOTA_TZ)
    except Exception:
        return datetime.now(timezone.utc) - timedelta(hours=5)


def get_bogota_today() -> date:
    """Retorna la fecha de hoy en Colombia."""
    return get_bogota_now().date()


def validate_slot_not_past(slot) -> None:
    """
    Valida estrictamente que el slot no sea del pasado en zona horaria de Colombia ('America/Bogota').
    Si slot.date < today o (slot.date == today y slot.end_time <= currentTime),
    lanza HTTPException(status_code=400, detail="No se pueden crear reservas en turnos pasados").
    """
    now_b = get_bogota_now()
    today_b = now_b.date()
    current_time_b = now_b.time()

    slot_date = slot.date
    slot_end = slot.end_time

    # Manejo de borde: slot que termina a las 00:00 (medianoche / final del día)
    if slot_end == time(0, 0) and getattr(slot, "start_time", time(0, 0)) >= time(23, 0):
        if slot_date < today_b:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pueden crear reservas en turnos pasados",
            )
        return

    if (slot_date < today_b) or (slot_date == today_b and slot_end <= current_time_b):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pueden crear reservas en turnos pasados",
        )
