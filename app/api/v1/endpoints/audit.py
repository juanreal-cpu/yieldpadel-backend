from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from app.core.database import get_db
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.user import User, UserRole
from app.services.audit import log_activity

router = APIRouter()


class AuditLogResponse(BaseModel):
    id: int
    club_id: Optional[int] = 1
    user_id: Optional[int] = None
    operator_user: Optional[str] = "RECEPCION"
    username_snapshot: str
    action: str
    entity: Optional[str] = None
    entity_name: str
    entity_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


class CreateAuditLogRequest(BaseModel):
    action: str
    entity_name: str = "SYSTEM"
    entity_id: Optional[str] = None
    details: Optional[str] = None
    username: Optional[str] = "Camilo Real (Recepción)"


async def ensure_seed_audit_logs(db: AsyncSession):
    count_res = await db.execute(select(func.count(AuditLog.id)))
    count = count_res.scalar() or 0
    if count == 0:
        sample_logs = [
            ("RESERVA_CREADA", "SLOT", "101", "Reserva confirmada en Cancha Central 1 (18:00 - 19:30) | Cliente: Juan David"),
            ("VENTA_POS", "ORDER", "12", "Venta POS (PAID) por $28.000 COP para Juan David | Tubo de Bolas"),
            ("ACCESO_REGISTRADO", "ACCESS", "5", "Check-In de Camilo Real (Membresía: TAPIA)"),
            ("TORNEO_GANADORES", "TOURNAMENT", "Americano 4ta", "Campeones: Juanda & Camilo | Subcampeones: David & Pipe"),
            ("RESERVA_MODIFICADA", "SLOT", "102", "Modificación de horario en Cancha 2 | Cliente: Carlos Gómez"),
            ("ACCESO_REGISTRADO", "ACCESS", "6", "Check-In de Mariana Restrepo (Membresía: COELLO)"),
        ]
        for act, ent, ent_id, det in sample_logs:
            await log_activity(
                db=db,
                action=act,
                entity_name=ent,
                entity_id=ent_id,
                details=det,
                username_snapshot="Camilo Real (Recepción)"
            )


class UserCreateRequest(BaseModel):
    username: str
    password: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str = "STAFF_RECEPCION"


class UserItemResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    start_date: Optional[str] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    action_type: Optional[str] = Query(None, description="Tipo de acción: ALL, RESERVAS, AMERICANOS, CANCELACIONES, PRECIOS, JUGADORES"),
    action: Optional[str] = Query(None, description="Filtrar por acción específica"),
    entity_name: Optional[str] = Query(None, description="Filtrar por entidad (SLOT, TOURNAMENT, etc.)"),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    await ensure_seed_audit_logs(db)
    
    # Ordenar por created_at DESC (o timestamp DESC)
    order_col = func.coalesce(AuditLog.created_at, AuditLog.timestamp)
    query = select(AuditLog).order_by(desc(order_col))

    # Filtro por rango de fechas
    if isinstance(start_date, str) and start_date.strip():
        start_str = start_date.strip()
        try:
            start_dt = datetime.strptime(f"{start_str} 00:00:00", "%Y-%m-%d %H:%M:%S")
            query = query.where(order_col >= start_dt)
        except ValueError:
            pass

    if isinstance(end_date, str) and end_date.strip():
        end_str = end_date.strip()
        try:
            end_dt = datetime.strptime(f"{end_str} 23:59:59", "%Y-%m-%d %H:%M:%S")
            query = query.where(order_col <= end_dt)
        except ValueError:
            pass

    # Filtro por categoría o tipo de acción
    act_raw = action_type if isinstance(action_type, str) else (action if isinstance(action, str) else "ALL")
    act_filter = act_raw.upper().strip()
    if act_filter and act_filter != "ALL":
        if act_filter in ("RESERVAS", "RESERVATION", "RESERVE_SLOT"):
            query = query.where(
                AuditLog.action.in_([
                    "CREATE_RESERVATION", "RESERVA_CREADA", "RESERVE_SLOT", "RESERVA_MODIFICADA"
                ]) | AuditLog.action.ilike("%RESERV%") | AuditLog.action.ilike("%BOOK%")
            )
        elif act_filter in ("AMERICANOS", "AMERICANO", "TOURNAMENT", "CREATE_AMERICANO"):
            query = query.where(
                AuditLog.action.in_([
                    "CREATE_AMERICANO", "TORNEO_GANADORES", "ENROLL_AMERICANO"
                ]) | AuditLog.action.ilike("%AMERICANO%") | AuditLog.action.ilike("%TOURNAMENT%")
            )
        elif act_filter in ("CANCELACIONES", "CANCEL", "CANCEL_RESERVATION", "CANCEL_AMERICANO"):
            query = query.where(
                AuditLog.action.in_([
                    "CANCEL_RESERVATION", "CANCEL_AMERICANO", "CANCEL_RESERVATION_AND_FREE",
                    "CANCEL_SLOT_PLAYER", "WHATSAPP_CANCEL_SPOT"
                ]) | AuditLog.action.ilike("%CANCEL%") | AuditLog.action.ilike("%DROP%")
            )
        elif act_filter in ("PRECIOS", "PRICE", "UPDATE_CONFIG", "UPDATE_PRICE"):
            query = query.where(
                AuditLog.action.in_([
                    "UPDATE_PRICE", "UPDATE_SLOT_PRICE", "UPDATE_CONFIG"
                ]) | AuditLog.action.ilike("%PRICE%") | AuditLog.action.ilike("%PRECIO%") | AuditLog.action.ilike("%CONFIG%")
            )
        elif act_filter in ("JUGADORES", "PLAYER"):
            query = query.where(
                AuditLog.action.in_([
                    "ADD_PLAYER", "REMOVE_PLAYER", "CANCEL_SLOT_PLAYER", "WHATSAPP_CANCEL_SPOT"
                ]) | AuditLog.action.ilike("%PLAYER%") | AuditLog.action.ilike("%JUGADOR%")
            )
        else:
            query = query.where((AuditLog.action == act_filter) | AuditLog.action.ilike(f"%{act_filter}%"))

    if isinstance(entity_name, str) and entity_name.strip() and entity_name != "ALL":
        query = query.where((AuditLog.entity_name == entity_name.strip()) | (AuditLog.entity == entity_name.strip()))

    query = query.limit(limit)

    res = await db.execute(query)
    logs = res.scalars().all()
    return [AuditLogResponse.model_validate(l) for l in logs]


@router.post("/log", response_model=AuditLogResponse)
async def record_audit_log(
    req: CreateAuditLogRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    entry = await log_activity(
        db=db,
        action=req.action,
        entity_name=req.entity_name,
        entity_id=req.entity_id,
        details=req.details,
        username_snapshot=req.username or "Camilo Real (Recepción)",
        request=request
    )
    if not entry:
        raise HTTPException(status_code=500, detail="Error registrando evento de auditoría")
    return AuditLogResponse.model_validate(entry)


@router.get("/users", response_model=List[UserItemResponse])
async def list_users(
    db: AsyncSession = Depends(get_db)
):
    query = select(User).order_by(User.id)
    res = await db.execute(query)
    users = res.scalars().all()
    return [UserItemResponse.model_validate(u) for u in users]


@router.post("/users", response_model=UserItemResponse)
async def create_user(
    req: UserCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # Check if username already exists
    res = await db.execute(select(User).where(User.username == req.username.strip().lower()))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")

    new_user = User(
        username=req.username.strip().lower(),
        hashed_password=hash_password(req.password),
        full_name=req.full_name.strip(),
        email=req.email.strip().lower() if req.email else None,
        phone=req.phone.strip() if req.phone else None,
        role=req.role.strip().upper(),
        is_active=True
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Audit new user creation
    await log_activity(
        db=db,
        action="USER_CREATED",
        entity_name="USER",
        entity_id=new_user.id,
        details=f"Nuevo usuario creado: {new_user.username} con rol {new_user.role}",
        username_snapshot="Superadmin / Sistema",
        request=request
    )

    return UserItemResponse.model_validate(new_user)
