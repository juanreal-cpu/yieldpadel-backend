from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.court import Court
from app.schemas.slot import CourtResponse
from app.api.v1.endpoints.slots import ensure_five_courts

router = APIRouter()


class CourtUpdateRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    sport_type: Optional[str] = None
    max_capacity: Optional[int] = None


@router.get("", response_model=List[CourtResponse], status_code=status.HTTP_200_OK)
@router.get("/", response_model=List[CourtResponse], status_code=status.HTTP_200_OK)
async def get_courts(
    sport: Optional[str] = Query(None, description="Filtrar por deporte (PADEL, PICKLEBALL, VOLLEYBALL, PILATES, CONSOLE)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna el listado completo de canchas y pistas multideporte del club:
    - Pádel 1 a 5
    - Pickleball 1 y 2
    - Arena Vóley
    - Estudio Pilates
    - Sala Gaming / Consola
    """
    courts = await ensure_five_courts(db)
    if sport and sport.upper() not in ["ALL", "TODAS", ""]:
        courts = [
            c for c in courts
            if (getattr(c, "sport_type", "PADEL") or "PADEL").upper() == sport.strip().upper()
        ]
    return courts


@router.put("/{court_id}", response_model=CourtResponse)
@router.post("/{court_id}", response_model=CourtResponse)
async def update_court(
    court_id: str,
    payload: CourtUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza la parametrización de una pista (nombre, capacidad, estado)."""
    try:
        c_uuid = uuid.UUID(court_id)
        stmt = select(Court).where(Court.id == c_uuid)
    except ValueError:
        stmt = select(Court).where(Court.name.ilike(f"%{court_id}%"))

    result = await db.execute(stmt)
    court = result.scalar_one_or_none()
    if not court:
        raise HTTPException(status_code=404, detail="Pista no encontrada.")

    if payload.name is not None:
        court.name = payload.name.strip()
    if payload.is_active is not None:
        court.is_active = payload.is_active
    if payload.sport_type is not None:
        court.sport_type = payload.sport_type.upper()
    if payload.max_capacity is not None:
        court.max_capacity = payload.max_capacity

    await db.commit()
    await db.refresh(court)
    return court


class CourtStatusUpdateRequest(BaseModel):
    court_id: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None


@router.post("/update-status", response_model=CourtResponse)
@router.put("/update-status", response_model=CourtResponse)
async def update_court_status(
    payload: CourtStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza el estado (Activa / Mantenimiento) y nombre de una pista."""
    target_id = payload.court_id or payload.id
    if not target_id and not payload.name:
        raise HTTPException(status_code=400, detail="Debe especificar court_id o name.")

    court = None
    if target_id:
        try:
            c_uuid = uuid.UUID(str(target_id))
            res = await db.execute(select(Court).where(Court.id == c_uuid))
            court = res.scalar_one_or_none()
        except ValueError:
            res = await db.execute(select(Court).where(Court.name.ilike(f"%{target_id}%")))
            court = res.scalars().first()

    if not court and payload.name:
        res = await db.execute(select(Court).where(Court.name.ilike(f"%{payload.name.strip()}%")))
        court = res.scalars().first()

    if not court:
        raise HTTPException(status_code=404, detail="Pista no encontrada.")

    if payload.name is not None and payload.name.strip():
        court.name = payload.name.strip()

    if payload.is_active is not None:
        court.is_active = payload.is_active
    elif payload.status is not None:
        s_clean = payload.status.lower().strip()
        if s_clean in ["active", "activa", "habilitada", "true", "1"]:
            court.is_active = True
        elif s_clean in ["maintenance", "mantenimiento", "inactiva", "disabled", "false", "0"]:
            court.is_active = False

    await db.commit()
    await db.refresh(court)
    return court

