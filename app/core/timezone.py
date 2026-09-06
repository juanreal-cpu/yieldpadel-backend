"""
YieldPadel - Timezone Configuration
Garantiza el uso correcto de la zona horaria de Colombia (America/Bogota, UTC-5)
tanto en entornos locales como en despliegues cloud (Render, AWS, Docker) que corren en UTC.
"""

from datetime import date, datetime, timedelta, timezone

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
