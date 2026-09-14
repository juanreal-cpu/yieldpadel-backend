import inspect
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Union, Any
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.models.audit import AuditLog

BOGOTA_TZ = ZoneInfo("America/Bogota")


def record_audit_log(
    db: Union[Session, AsyncSession],
    action: str,
    entity: str,
    details: Union[str, dict, list],
    operator_user: str = "RECEPCION",
    club_id: int = 1,
) -> Optional[AuditLog]:
    """
    Servicio centralizado de auditoría.
    Soporta sesiones síncronas (Session) y asíncronas (AsyncSession).
    Si db es asíncrono, se puede invocar con await record_audit_log(...) o de manera asíncrona.
    """
    details_str = json.dumps(details, ensure_ascii=False) if isinstance(details, (dict, list)) else str(details)
    now_utc = datetime.now(timezone.utc)
    now_bogota = datetime.now(BOGOTA_TZ).replace(tzinfo=None)

    new_log = AuditLog(
        club_id=club_id,
        operator_user=operator_user,
        username_snapshot=operator_user,
        action=action,
        entity=entity,
        entity_name=entity,
        details=details_str,
        created_at=now_utc,
        timestamp=now_bogota,
        ip_address="127.0.0.1",
    )

    if isinstance(db, AsyncSession):
        async def _async_record():
            try:
                db.add(new_log)
                await db.commit()
                return new_log
            except Exception as e:
                print(f"[AUDIT LOG WARNING] Error in record_audit_log async: {e}")
                try:
                    await db.rollback()
                except Exception:
                    pass
                return None
        return _async_record()
    else:
        try:
            db.add(new_log)
            db.commit()
            return new_log
        except Exception as e:
            print(f"[AUDIT LOG WARNING] Error in record_audit_log sync: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return None


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
    operator_user: Optional[str] = None,
    club_id: int = 1,
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

        op_user = operator_user or username_snapshot
        if not op_user:
            op_user = "Camilo Real (Recepción)" if not user_id else f"Usuario #{user_id}"

        details_str = None
        if details is not None:
            if isinstance(details, (dict, list)):
                details_str = json.dumps(details, ensure_ascii=False)
            else:
                details_str = str(details)

        now_utc = datetime.now(timezone.utc)
        now_bogota = datetime.now(BOGOTA_TZ).replace(tzinfo=None)

        audit_entry = AuditLog(
            club_id=club_id,
            user_id=user_id,
            operator_user=op_user,
            username_snapshot=op_user,
            action=action,
            entity=entity_name,
            entity_name=entity_name,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details_str,
            ip_address=ip_address or "127.0.0.1",
            created_at=now_utc,
            timestamp=now_bogota,
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

