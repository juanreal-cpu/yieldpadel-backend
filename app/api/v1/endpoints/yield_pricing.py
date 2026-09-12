"""
YieldPadel - Yield Pricing & Econometric Optimization Endpoints
Provee endpoints para recomendación analítica en tiempo real y aplicación de precios dinámicos inteligentes.
"""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.timezone import get_bogota_now
from app.models.slot import TimeSlot
from app.services.audit import log_activity
from app.services import QuantitativeYieldEngine, CLUB_SETTINGS, get_club_config

logger = logging.getLogger(__name__)

router = APIRouter()


class ApplySmartPriceRequest(BaseModel):
    slot_id: int = Field(..., description="ID del turno a actualizar")
    recommended_price: float = Field(..., description="Nuevo precio total sugerido en COP")
    reason: Optional[str] = Field(None, description="Motivo o narrativa del ajuste")


class ApplyBatchSmartPriceRequest(BaseModel):
    updates: List[ApplySmartPriceRequest] = Field(..., description="Lista de slots a actualizar")


@router.get("/recommendation/{slot_id}")
async def get_slot_yield_recommendation(
    slot_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna el desglose econométrico completo y la recomendación de precio óptimo
    para un turno determinado (P_fill, benchmark, decaimiento de Lead Time y veredicto).
    """
    stmt = select(TimeSlot).where(TimeSlot.id == slot_id)
    res = await db.execute(stmt)
    slot = res.scalar_one_or_none()

    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turno con ID {slot_id} no encontrado.",
        )

    recommendation = await QuantitativeYieldEngine.compute_recommendation(db, slot)
    return {
        "status": "ok",
        "data": recommendation,
    }


@router.get("/recommendations/active")
async def get_active_slots_recommendations(
    date_str: Optional[str] = Query(None, description="Fecha YYYY-MM-DD para auditar recomendaciones"),
    sport: Optional[str] = Query("PADEL", description="Tipo de deporte"),
    limit: int = Query(50, description="Límite de turnos a retornar"),
    db: AsyncSession = Depends(get_db),
):
    """
    Obtiene la lista de turnos activos para una fecha con su precio actual, precio recomendado
    y desglose analítico para poblar el tablero de Yield Management en el frontend.
    """
    bogota_now = get_bogota_now()
    target_date = bogota_now.date()
    if date_str:
        try:
            from datetime import date
            target_date = date.fromisoformat(date_str)
        except Exception:
            pass

    stmt = (
        select(TimeSlot)
        .where(
            TimeSlot.date == target_date,
            TimeSlot.status != "CANCELLED",
        )
        .order_by(TimeSlot.start_time.asc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    slots = res.scalars().all()

    items = []
    for s in slots:
        if sport and getattr(s, "sport_type", "PADEL") != sport:
            continue
        try:
            rec = await QuantitativeYieldEngine.compute_recommendation(db, s, now=bogota_now)
            items.append(rec)
        except Exception as ex:
            logger.warning(f"Error calculando recomendación para slot {s.id}: {ex}")

    return {
        "status": "ok",
        "date": target_date.isoformat(),
        "sport": sport,
        "count": len(items),
        "recommendations": items,
    }


@router.post("/apply-smart-price")
async def apply_smart_price(
    payload: ApplySmartPriceRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Aplica el precio inteligente recomendado sobre el turno en base de datos.
    Actualiza time_slots.total_price, price, price_total_cop y price_per_player_cop.
    Registra evento en la bitácora de auditoría.
    """
    stmt = select(TimeSlot).where(TimeSlot.id == payload.slot_id)
    res = await db.execute(stmt)
    slot = res.scalar_one_or_none()

    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turno con ID {payload.slot_id} no encontrado.",
        )

    old_price = float(slot.price_total_cop or slot.total_price or 0.0)
    new_price_dec = Decimal(str(round(payload.recommended_price, 2)))

    # Actualizar campos de precio
    slot.total_price = new_price_dec
    slot.price = new_price_dec
    slot.price_total_cop = new_price_dec
    cap = slot.capacity or 4
    slot.price_per_player_cop = (new_price_dec / Decimal(cap)).quantize(Decimal("1.00"))

    # Auditoría
    try:
        await log_activity(
            db=db,
            action="APPLY_SMART_PRICE",
            entity_type="time_slots",
            entity_id=str(slot.id),
            details={
                "old_price": old_price,
                "new_price": float(new_price_dec),
                "delta": float(new_price_dec) - old_price,
                "reason": payload.reason or "Ajuste dinámico cuantitativo Yield Management",
            },
        )
    except Exception as ex:
        logger.warning(f"No se pudo registrar auditoría de yield price: {ex}")

    await db.commit()
    await db.refresh(slot)

    return {
        "status": "ok",
        "message": f"Precio del turno {slot.id} actualizado exitosamente a ${int(new_price_dec):,} COP.",
        "slot_id": slot.id,
        "new_price_total_cop": float(new_price_dec),
        "new_price_per_player_cop": float(slot.price_per_player_cop),
    }
