import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Union, Any
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog

BOGOTA_TZ = ZoneInfo("America/Bogota")


async def log_activity(
    db: AsyncSession,
    action: str,
    entity_name: str,
    entity_id: Optional[Union[str, int]] = None,
    details: Optional[Union[dict, list, str]] = None,
    user_id: Optional[int] = None,
    username_snapshot: Optional[str] = None,
    ip_address: Optional[str] = None,
    request: Optional[Request] = None,
) -> Optional[AuditLog]:
    """
    Registra un evento de auditoria en base de datos de manera defensiva.
    """
    try:
        if request and not ip_address:
            client = request.client
            ip_address = client.host if client else "127.0.0.1"
            xff = request.headers.get("x-forwarded-for")
            if xff:
                ip_address = xff.split(",")[0].strip()

        if not username_snapshot:
            username_snapshot = "Camilo Real (Recepción)" if not user_id else f"Usuario #{user_id}"

        details_str = None
        if details is not None:
            if isinstance(details, (dict, list)):
                details_str = json.dumps(details, ensure_ascii=False)
            else:
                details_str = str(details)

        audit_entry = AuditLog(
            user_id=user_id,
            username_snapshot=username_snapshot,
            action=action,
            entity_name=entity_name,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details_str,
            ip_address=ip_address or "127.0.0.1",
            timestamp=datetime.now(BOGOTA_TZ).replace(tzinfo=None),
        )
        db.add(audit_entry)
        await db.commit()
        await db.refresh(audit_entry)
        return audit_entry
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error al guardar registro de auditoria: {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return None
