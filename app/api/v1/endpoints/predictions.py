from datetime import datetime
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.customer import Customer
from app.models.predictions import (
    MatchPrediction,
    PredictionLeaderboard,
    PredictedWinner,
    PredictionStatus,
)
from app.models.slot import TimeSlot

logger = logging.getLogger("yieldpadel.predictions")

router = APIRouter()


class VotePredictionRequest(BaseModel):
    slot_id: int = Field(..., description="ID del turno o partido a pronosticar")
    customer_id: Optional[int] = Field(None, description="ID del cliente/socio si está identificado")
    phone: Optional[str] = Field(None, description="Teléfono del cliente si vota desde WhatsApp/web")
    predicted_winner: PredictedWinner = Field(..., description="Ganador pronosticado: TEAM_A o TEAM_B")


class ResolveMatchRequest(BaseModel):
    slot_id: int = Field(..., description="ID del turno/partido disputado")
    winning_team: PredictedWinner = Field(..., description="Equipo ganador real: TEAM_A o TEAM_B")
    is_tournament_final: Optional[bool] = Field(False, description="True si es la final de un torneo oficial (+5 pts)")


class LeaderboardItem(BaseModel):
    rank: int
    customer_id: int
    customer_name: str
    phone: str
    avatar_url: Optional[str] = None
    monthly_points: int
    hits_count: int
    total_predictions: int
    accuracy_pct: float
    category: str


class LeaderboardResponse(BaseModel):
    month: int
    year: int
    club_id: int
    top_predictors: List[LeaderboardItem]


@router.post(
    "/vote",
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un pronóstico de partido (Pola/Puntos)",
)
async def vote_match_prediction(
    payload: VotePredictionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Registra un voto o pronóstico sobre un partido.
    Valida:
    1. Que el partido (slot) exista.
    2. Que el partido aún no haya iniciado (start_time > now() en la fecha correspondiente).
    3. Que no haya votado previamente para este mismo slot (un voto por cliente/partido).
    """
    # 1. Obtener el slot
    slot_stmt = select(TimeSlot).where(TimeSlot.id == payload.slot_id)
    slot_res = await db.execute(slot_stmt)
    slot = slot_res.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="El turno o partido indicado no existe")

    # 2. Validar que no haya iniciado
    now_dt = datetime.now()
    slot_datetime = datetime.combine(slot.date, slot.start_time)
    if slot_datetime <= now_dt:
        raise HTTPException(
            status_code=400,
            detail="El partido ya inició o ha finalizado. Las predicciones están cerradas.",
        )

    # 3. Resolver customer
    customer: Optional[Customer] = None
    if payload.customer_id:
        cust_res = await db.execute(select(Customer).where(Customer.id == payload.customer_id))
        customer = cust_res.scalar_one_or_none()
    elif payload.phone:
        clean_phone = payload.phone.strip()
        cust_res = await db.execute(
            select(Customer).where(Customer.phone.ilike(f"%{clean_phone}%"))
        )
        customer = cust_res.scalars().first()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="No se encontró un jugador registrado con ese ID o número de teléfono.",
        )

    # 4. Validar voto existente
    exist_stmt = select(MatchPrediction).where(
        MatchPrediction.slot_id == slot.id,
        MatchPrediction.customer_id == customer.id,
    )
    exist_res = await db.execute(exist_stmt)
    existing_pred = exist_res.scalar_one_or_none()
    if existing_pred:
        # Permitir actualizar predicción si el partido no ha iniciado
        existing_pred.predicted_winner = payload.predicted_winner
        await db.commit()
        await db.refresh(existing_pred)
        return {
            "status": "updated",
            "message": f"Pronóstico actualizado para {customer.name}: {payload.predicted_winner.value}",
            "prediction_id": existing_pred.id,
            "predicted_winner": existing_pred.predicted_winner.value,
        }

    # 5. Crear predicción
    new_pred = MatchPrediction(
        slot_id=slot.id,
        customer_id=customer.id,
        predicted_winner=payload.predicted_winner,
        points_awarded=0,
        status=PredictionStatus.PENDING,
    )
    db.add(new_pred)
    await db.commit()
    await db.refresh(new_pred)

    return {
        "status": "created",
        "message": f"¡Pronóstico registrado exitosamente para {customer.name} a favor de {payload.predicted_winner.value}!",
        "prediction_id": new_pred.id,
        "predicted_winner": new_pred.predicted_winner.value,
    }


@router.post(
    "/resolve-match",
    status_code=status.HTTP_200_OK,
    summary="Cerrar y evaluar pronósticos de un partido disputado",
)
async def resolve_match_predictions(
    payload: ResolveMatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Cierra los votos, evalúa aciertos (+3 pts regular, +5 pts campeón de torneo),
    actualiza el status ('HIT' | 'MISSED') y actualiza la tabla acumulada PredictionLeaderboard mensual.
    """
    # 1. Obtener el slot
    slot_stmt = select(TimeSlot).where(TimeSlot.id == payload.slot_id)
    slot_res = await db.execute(slot_stmt)
    slot = slot_res.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="El turno o partido indicado no existe")

    # 2. Obtener todas las predicciones PENDING
    preds_stmt = (
        select(MatchPrediction)
        .options(selectinload(MatchPrediction.customer))
        .where(
            MatchPrediction.slot_id == payload.slot_id,
            MatchPrediction.status == PredictionStatus.PENDING,
        )
    )
    preds_res = await db.execute(preds_stmt)
    predictions = list(preds_res.scalars().all())

    if not predictions:
        return {
            "status": "no_predictions",
            "message": "No había pronósticos pendientes para este partido.",
            "processed_count": 0,
            "hits": 0,
        }

    target_year = slot.date.year
    target_month = slot.date.month
    club_id_val = slot.club_id or 1
    pts_per_hit = 5 if payload.is_tournament_final else 3

    hits_count = 0
    misses_count = 0

    for pred in predictions:
        is_hit = pred.predicted_winner == payload.winning_team
        if is_hit:
            pred.status = PredictionStatus.HIT
            pred.points_awarded = pts_per_hit
            hits_count += 1
        else:
            pred.status = PredictionStatus.MISSED
            pred.points_awarded = 0
            misses_count += 1

        # Actualizar Leaderboard mensual
        lb_stmt = select(PredictionLeaderboard).where(
            PredictionLeaderboard.club_id == club_id_val,
            PredictionLeaderboard.year == target_year,
            PredictionLeaderboard.month == target_month,
            PredictionLeaderboard.customer_id == pred.customer_id,
        )
        lb_res = await db.execute(lb_stmt)
        leaderboard_entry = lb_res.scalar_one_or_none()

        if not leaderboard_entry:
            leaderboard_entry = PredictionLeaderboard(
                club_id=club_id_val,
                year=target_year,
                month=target_month,
                customer_id=pred.customer_id,
                monthly_points=0,
                hits_count=0,
                total_predictions=0,
            )
            db.add(leaderboard_entry)

        leaderboard_entry.total_predictions += 1
        if is_hit:
            leaderboard_entry.hits_count += 1
            leaderboard_entry.monthly_points += pts_per_hit

    await db.commit()

    return {
        "status": "success",
        "message": f"Partido resuelto. {hits_count} aciertos (+{pts_per_hit} pts c/u) y {misses_count} fallos.",
        "processed_count": len(predictions),
        "hits": hits_count,
        "misses": misses_count,
        "winning_team": payload.winning_team.value,
    }


@router.get(
    "/leaderboard",
    response_model=LeaderboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Top pronosticadores del mes para WhatsApp y Counter",
)
async def get_predictions_leaderboard(
    club_id: int = Query(1, description="ID del Club (default: 1)"),
    month: Optional[int] = Query(None, description="Mes (1-12, default actual)"),
    year: Optional[int] = Query(None, description="Año (default actual)"),
    limit: int = Query(10, description="Cantidad máxima de jugadores (Top 10)"),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now()
    target_month = month or now.month
    target_year = year or now.year

    stmt = (
        select(PredictionLeaderboard)
        .options(selectinload(PredictionLeaderboard.customer))
        .where(
            PredictionLeaderboard.club_id == club_id,
            PredictionLeaderboard.year == target_year,
            PredictionLeaderboard.month == target_month,
        )
        .order_by(
            desc(PredictionLeaderboard.monthly_points),
            desc(PredictionLeaderboard.hits_count),
        )
        .limit(limit)
    )

    res = await db.execute(stmt)
    entries = list(res.scalars().all())

    top_list: List[LeaderboardItem] = []
    for idx, entry in enumerate(entries, start=1):
        cust = entry.customer
        accuracy = (
            round((entry.hits_count / entry.total_predictions) * 100, 1)
            if entry.total_predictions > 0
            else 0.0
        )
        top_list.append(
            LeaderboardItem(
                rank=idx,
                customer_id=entry.customer_id,
                customer_name=cust.name if cust else "Jugador",
                phone=cust.phone if cust else "",
                avatar_url=getattr(cust, "avatar_url", None),
                monthly_points=entry.monthly_points,
                hits_count=entry.hits_count,
                total_predictions=entry.total_predictions,
                accuracy_pct=accuracy,
                category=cust.category if cust else "4ta",
            )
        )

    # Si aún no hay registros para el mes, complementar con los mejores clientes del CRM para visualización amigable
    if not top_list:
        sample_custs_stmt = (
            select(Customer)
            .order_by(desc(Customer.ranking_points), desc(Customer.total_bookings_completed))
            .limit(limit)
        )
        sample_res = await db.execute(sample_custs_stmt)
        sample_custs = sample_res.scalars().all()
        for idx, c in enumerate(sample_custs, start=1):
            top_list.append(
                LeaderboardItem(
                    rank=idx,
                    customer_id=c.id,
                    customer_name=c.name,
                    phone=c.phone,
                    avatar_url=c.avatar_url,
                    monthly_points=c.titles_count * 5 + c.category_wins * 3,
                    hits_count=c.category_wins,
                    total_predictions=max(c.category_wins, c.total_bookings_completed),
                    accuracy_pct=round((c.category_wins / max(1, c.total_bookings_completed)) * 100, 1),
                    category=c.category,
                )
            )

    return LeaderboardResponse(
        month=target_month,
        year=target_year,
        club_id=club_id,
        top_predictors=top_list,
    )
