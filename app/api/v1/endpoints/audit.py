from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

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
    query = select(AuditLog).order_by(desc(AuditLog.timestamp))
    if action and action != "ALL":
        query = query.where(AuditLog.action == action)
    if entity_name and entity_name != "ALL":
        query = query.where(AuditLog.entity_name == entity_name)
    query = query.limit(limit)

    res = await db.execute(query)
    logs = res.scalars().all()
    return [AuditLogResponse.model_validate(l) for l in logs]


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
