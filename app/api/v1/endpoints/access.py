import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.access import (
    clear_debt_in_counter,
    get_active_now_data,
    perform_check_in,
    perform_check_out,
)

logger = logging.getLogger("yieldpadel.access")

router = APIRouter()


# ----------------------------------------------------
# Pydantic Schemas
# ----------------------------------------------------
class CheckInRequest(BaseModel):
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    phone: Optional[str] = None
    current_slot_id: Optional[int] = None
    membership_tier: Optional[str] = None


class CheckOutRequest(BaseModel):
    presence_id: Optional[int] = None
    player_id: Optional[int] = None
    force_clear: bool = False


# ----------------------------------------------------
# Endpoints
# ----------------------------------------------------
@router.post("/check-in", summary="Registrar entrada de jugador al club")
async def check_in_endpoint(
    payload: CheckInRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        presence = await perform_check_in(
            db=db,
            player_id=payload.player_id,
            player_name=payload.player_name,
            phone=payload.phone,
            current_slot_id=payload.current_slot_id,
            membership_tier=payload.membership_tier,
        )
        return {
            "success": True,
            "message": f"Entrada registrada para {presence.player_name}",
            "presence": {
                "id": presence.id,
                "player_id": presence.player_id,
                "player_name": presence.player_name,
                "phone": presence.phone,
                "check_in_time": presence.check_in_time.isoformat(),
                "membership_tier": presence.membership_tier,
                "current_slot_id": presence.current_slot_id,
                "is_inside": presence.is_inside,
            },
        }
    except Exception as e:
        logger.error(f"Error en check-in: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-out", summary="Registrar y validar salida de jugador (Bloqueo Financiero)")
async def check_out_endpoint(
    payload: CheckOutRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await perform_check_out(
            db=db,
            presence_id=payload.presence_id,
            player_id=payload.player_id,
            force_clear=payload.force_clear,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en check-out: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-debt/{presence_id}", summary="Liquidar consumos/turnos en counter y desbloquear")
async def clear_debt_endpoint(
    presence_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await clear_debt_in_counter(db=db, presence_id=presence_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error liquidando deuda: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active-now", summary="Obtener aforo activo, alertas y métricas en tiempo real")
async def active_now_endpoint(
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await get_active_now_data(db=db)
        return data
    except Exception as e:
        logger.error(f"Error obteniendo aforo activo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
