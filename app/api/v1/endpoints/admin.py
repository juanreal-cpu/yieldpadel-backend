from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import importlib
from app.core.database import get_db
from app.models.court import Court
from app.schemas.slot import CourtResponse
from app.services.audit import log_activity

_yield_service = importlib.import_module("app.services.yield")
get_club_config = _yield_service.get_club_config
update_club_config = _yield_service.update_club_config


router = APIRouter()


class CourtStatusUpdateRequest(BaseModel):
    court_id: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None



class PricingRulesBySportRequest(BaseModel):
    padel_valle: Optional[float] = None
    padel_pico: Optional[float] = None
    padel_floor: Optional[float] = None
    pickleball_valle: Optional[float] = None
    pickleball_pico: Optional[float] = None
    volleyball_individual: Optional[float] = None
    volleyball_base: Optional[float] = None
    pilates_per_mat: Optional[float] = None
    promo_discount_percent: Optional[int] = None
    cancellation_grace_minutes: Optional[int] = None
    confirmation_grace_minutes: Optional[int] = None
    whatsapp_group_id: Optional[str] = None
    base_valle: Optional[float] = None
    base_pico: Optional[float] = None
    floor_price: Optional[float] = None
    discount_pct: Optional[int] = None
    cancel_grace: Optional[int] = None
    confirm_grace: Optional[int] = None
    whatsapp_group: Optional[str] = None


@router.get("/pricing-rules-by-sport", status_code=status.HTTP_200_OK)
@router.get("/club-settings", status_code=status.HTTP_200_OK)
async def get_pricing_rules():
    """Retorna las tarifas dinámicas y reglas diferenciadas por deporte."""
    return {
        "status": "success",
        "config": get_club_config(),
    }


@router.post("/pricing-rules-by-sport", status_code=status.HTTP_200_OK)
@router.post("/club-settings", status_code=status.HTTP_200_OK)
async def update_pricing_rules(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """
    Actualiza las reglas de precios diferenciadas por deporte:
    - Pádel: Valle ($80.000), Pico ($120.000), Suelo ($60.000)
    - Pickleball: Valle ($50.000), Pico ($80.000)
    - Vóley: Individual ($15.000/persona) y Cancha Completa ($120.000)
    - Pilates: Clase individual ($35.000/cupo)
    """
    # Mapeo de campos compatibles
    clean_updates: Dict[str, Any] = {}
    for k, v in payload.items():
        if v is not None:
            clean_updates[k] = v

    if "discount_pct" in clean_updates and "promo_discount_percent" not in clean_updates:
        clean_updates["promo_discount_percent"] = clean_updates["discount_pct"]
    if "cancel_grace" in clean_updates and "cancellation_grace_minutes" not in clean_updates:
        clean_updates["cancellation_grace_minutes"] = clean_updates["cancel_grace"]
    if "confirm_grace" in clean_updates and "confirmation_grace_minutes" not in clean_updates:
        clean_updates["confirmation_grace_minutes"] = clean_updates["confirm_grace"]
    if "whatsapp_group" in clean_updates and "whatsapp_group_id" not in clean_updates:
        clean_updates["whatsapp_group_id"] = clean_updates["whatsapp_group"]

    updated_config = update_club_config(clean_updates)

    # Registro de auditoría operativa
    try:
        await log_activity(
            db=db,
            action="UPDATE_CONFIG",
            entity_name="PRICING",
            details=f"Actualización de tarifas multideporte: Pádel (V: ${updated_config.get('padel_valle')}, P: ${updated_config.get('padel_pico')}), Pickleball (V: ${updated_config.get('pickleball_valle')}, P: ${updated_config.get('pickleball_pico')}), Vóley (Ind: ${updated_config.get('volleyball_individual')}, Base: ${updated_config.get('volleyball_base')}), Pilates ($: ${updated_config.get('pilates_per_mat')}).",
            username_snapshot="Camilo Real (Recepción)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error logging admin pricing update: {e}")

    return {
        "status": "success",
        "message": "Reglas de precios por deporte actualizadas exitosamente.",
        "config": updated_config,
    }


@router.post("/courts/update-status", response_model=CourtResponse)
@router.put("/courts/update-status", response_model=CourtResponse)
async def update_court_status_admin(
    payload: CourtStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza el estado y nombre de una pista desde el panel de administración."""
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

    try:
        status_label = "Activa" if court.is_active else "En Mantenimiento"
        await log_activity(
            db=db,
            action="UPDATE_COURT_STATUS",
            entity_name="COURTS",
            details=f"Pista '{court.name}' actualizada a {status_label}.",
            username_snapshot="Camilo Real (Recepción)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error logging court status update: {e}")

    return court

