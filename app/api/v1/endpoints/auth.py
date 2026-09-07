from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import verify_password, create_access_token, decode_access_token
from app.models.user import User, UserRole
from app.services.audit import log_activity

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    query = select(User).where(User.username == req.username.strip().lower())
    res = await db.execute(query)
    user = res.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        # Audit failed login attempt
        await log_activity(
            db=db,
            action="LOGIN_FAILED",
            entity_name="AUTH",
            details=f"Intento fallido de inicio de sesión para usuario: {req.username}",
            username_snapshot=req.username,
            request=request
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas o usuario no encontrado"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de usuario está desactivada"
        )

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name
    }
    token = create_access_token(token_data)

    # Audit successful login
    await log_activity(
        db=db,
        action="LOGIN_SUCCESS",
        entity_name="AUTH",
        entity_id=user.id,
        user_id=user.id,
        username_snapshot=f"{user.full_name} ({user.role})",
        details=f"Inicio de sesión exitoso desde {request.client.host if request.client else '127.0.0.1'}",
        request=request
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # Check Authorization header or fallback to default staff
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            user_id = int(payload["sub"])
            user = await db.get(User, user_id)
            if user and user.is_active:
                return UserResponse.model_validate(user)

    # Fallback default active user (Camilo Real) for seamless single-page operation
    res = await db.execute(select(User).where(User.username == "recepcion"))
    user = res.scalar_one_or_none()
    if not user:
        res_admin = await db.execute(select(User).where(User.username == "admin"))
        user = res_admin.scalar_one_or_none()

    if user:
        return UserResponse.model_validate(user)

    # Default fallback user representation if database is fresh
    return UserResponse(
        id=1,
        username="recepcion",
        email="recepcion@capitalpadel.com",
        full_name="Camilo Real (Recepción)",
        phone="+57 310 987 6543",
        role="STAFF_RECEPCION",
        is_active=True
    )
