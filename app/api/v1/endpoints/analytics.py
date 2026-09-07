from datetime import date
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.analytics import AnalyticsService

router = APIRouter()


@router.get("/occupancy-matrix", response_model=Dict[str, Any])
async def get_occupancy_matrix(
    start_date: Optional[date] = Query(None, description="Fecha de inicio de la semana a consultar (por defecto semana actual)"),
    sport: Optional[str] = Query("PADEL", description="Deporte a filtrar (PADEL, PICKLEBALL, VOLLEYBALL, PILATES, CONSOLE, ALL)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Obtiene la matriz semanal de ocupación (Horas vs Días), RevPAST,
    y comparativas con Semana Anterior (WoW) y Mes Anterior (MoM, 28 días).
    Si no existen registros históricos pasados, delta_last_week y delta_last_month devuelven None sin error.
    """
    return await AnalyticsService.get_weekly_occupancy_matrix(
        db=db,
        start_date=start_date,
        sport=sport,
    )
