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
    user_id: Optional[int] = None
    username_snapshot: str
    action: str
    entity_name: str
    entity_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime

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
    action: Optional[str] = Query(None, description="Filtrar por acción específica"),
    entity_name: Optional[str] = Query(None, description="Filtrar por entidad (SLOT, TOURNAMENT, etc.)"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    await ensure_seed_audit_logs(db)
    query = select(AuditLog).order_by(desc(AuditLog.timestamp))
    if action and action != "ALL":
        query = query.where(AuditLog.action == action)
    if entity_name and entity_name != "ALL":
        query = query.where(AuditLog.entity_name == entity_name)
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
