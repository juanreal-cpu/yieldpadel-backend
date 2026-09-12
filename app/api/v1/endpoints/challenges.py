from datetime import datetime, date
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.timezone import get_bogota_today, get_bogota_now
from app.models.customer import Customer
from app.models.predictions import (
    MatchPrediction,
    PredictionLeaderboard,
    PredictedWinner,
    PredictionStatus,
)
from app.models.slot import SlotStatus, TimeSlot
from app.api.v1.endpoints.slots import to_participants_list
from app.services.audit import log_activity

logger = logging.getLogger("yieldpadel.challenges")

router = APIRouter()


class ChallengeVoteRequest(BaseModel):
    slot_id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    predicted_winner: str = "TEAM_A"  # 'TEAM_A' or 'TEAM_B'


@router.get("/list", summary="Listar retos y partidos cerrados 4/4 con votación y apuestas")
async def list_challenges(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna el listado de partidos de reto y partidos cerrados 4/4 para pronóstico y apuestas lúdicas.
    """
    today = get_bogota_today()
    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court))
        .where(
            or_(
                TimeSlot.slot_type.in_(["RETO", "CHALLENGE"]),
                TimeSlot.status == SlotStatus.FULLY_BOOKED,
                TimeSlot.booked_spots >= 4,
            )
        )
        .order_by(TimeSlot.date.desc(), TimeSlot.start_time.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    slots = list(res.scalars().all())

    # Cargar predicciones asociadas para calcular % votos
    slot_ids = [s.id for s in slots]
    preds_map = {}
    if slot_ids:
        p_stmt = select(MatchPrediction).where(MatchPrediction.slot_id.in_(slot_ids))
        p_res = await db.execute(p_stmt)
        for p in p_res.scalars().all():
            if p.slot_id not in preds_map:
                preds_map[p.slot_id] = {"A": 0, "B": 0}
            if p.predicted_winner == PredictedWinner.TEAM_A:
                preds_map[p.slot_id]["A"] += 1
            else:
                preds_map[p.slot_id]["B"] += 1

    items: List[dict] = []
    active_count = 0
    total_hits = 0
    points_awarded_total = 0

    for s in slots:
        participants = to_participants_list(s.players_names)
        names = [p.get("display_name", "Jugador") for p in participants if p.get("display_name")]
        
        team_a = " / ".join(names[:2]) if len(names) >= 2 else (names[0] if names else "Pareja A")
        team_b = " / ".join(names[2:4]) if len(names) >= 4 else (names[2] if len(names) > 2 else "Pareja B")

        v = preds_map.get(s.id, {"A": 0, "B": 0})
        total_v = v["A"] + v["B"]
        pct_a = round((v["A"] / total_v * 100), 1) if total_v > 0 else 50.0
        pct_b = round((v["B"] / total_v * 100), 1) if total_v > 0 else 50.0

        is_active = (s.date >= today and not s.is_finished)
        if is_active:
            active_count += 1

        c_name = s.court.name if s.court else "Cancha Central"
        official_res = "PENDIENTE"
        if s.is_finished and s.winners_names:
            official_res = f"Ganó: {s.winners_names}"

        items.append({
            "id": s.id,
            "slot_id": s.id,
            "date": str(s.date),
            "time": s.start_time.strftime("%H:%M") if s.start_time else "",
            "court_name": c_name,
            "team_a": team_a,
            "team_b": team_b,
            "bet": "🍔 Hamburguesa Tato & Pola (+30 pts)" if s.slot_type in ("RETO", "CHALLENGE") else "🏆 Puntos de Ranking (+30 pts)",
            "votes_a": v["A"],
            "votes_b": v["B"],
            "pct_a": pct_a,
            "pct_b": pct_b,
            "status": "EN_JUEGO" if is_active else ("FINALIZADO" if s.is_finished else "PROGRAMADO"),
            "official_result": official_res,
            "points_awarded": 30,
            "winner_names": s.winners_names,
        })

    # KPIs de la comunidad
    lb_stmt = select(PredictionLeaderboard)
    lb_res = await db.execute(lb_stmt)
    lbs = lb_res.scalars().all()
    for lb in lbs:
        total_hits += (lb.hits_count or 0)
        points_awarded_total += (lb.monthly_points or 0)

    if total_hits == 0:
        c_res = await db.execute(select(Customer))
        custs = c_res.scalars().all()
        for c in custs:
            total_hits += (c.category_wins or 0)
            points_awarded_total += (c.ranking_points or 0)

    return {
        "status": "success",
        "kpis": {
            "active_challenges_today": active_count,
            "community_hits_count": total_hits,
            "points_awarded_total": points_awarded_total,
            "points_per_winner": 30,
            "points_per_prediction": 3,
        },
        "challenges": items,
    }


@router.post("/vote", summary="Emitir voto/pronóstico para un reto o partido (+3 pts polla)")
async def vote_challenge(
    payload: ChallengeVoteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Registra el pronóstico del usuario para Pareja A o Pareja B.
    """
    slot_stmt = select(TimeSlot).where(TimeSlot.id == payload.slot_id)
    slot_res = await db.execute(slot_stmt)
    slot = slot_res.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Turno no encontrado")

    pw = PredictedWinner.TEAM_A if payload.predicted_winner.upper() == "TEAM_A" else PredictedWinner.TEAM_B

    cust: Optional[Customer] = None
    if payload.customer_id:
        c_res = await db.execute(select(Customer).where(Customer.id == payload.customer_id))
        cust = c_res.scalar_one_or_none()
    elif payload.phone:
        c_res = await db.execute(select(Customer).where(Customer.phone == payload.phone.strip()))
        cust = c_res.scalar_one_or_none()
    elif payload.customer_name:
        c_res = await db.execute(select(Customer).where(Customer.name.ilike(payload.customer_name.strip())))
        cust = c_res.scalars().first()

    pred = MatchPrediction(
        club_id=1,
        slot_id=slot.id,
        customer_id=cust.id if cust else 1,
        phone=cust.phone if cust else (payload.phone or "+57-300-000-0000"),
        predicted_winner=pw,
        status=PredictionStatus.PENDING,
        points_awarded=0,
    )
    db.add(pred)
    await db.commit()

    return {
        "status": "success",
        "message": f"¡Pronóstico registrado! Has votado por {payload.predicted_winner}. Si aciertas recibirás +3 puntos.",
        "slot_id": slot.id,
        "predicted_winner": payload.predicted_winner,
    }


@router.get("/challenges-lookup", summary="Lookup de retos y partidos para WhatsApp")
async def challenges_lookup(
    phone: Optional[str] = Query(None, description="Teléfono del cliente que consulta"),
    db: AsyncSession = Depends(get_db),
):
    today = get_bogota_today()
    now_t = get_bogota_now().time()

    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court))
        .where(
            TimeSlot.date == today,
            or_(
                TimeSlot.slot_type.in_(["RETO", "CHALLENGE"]),
                TimeSlot.status == SlotStatus.FULLY_BOOKED,
                TimeSlot.booked_spots >= 4,
            ),
            TimeSlot.start_time > now_t,
        )
        .order_by(TimeSlot.start_time.asc())
        .limit(5)
    )
    res = await db.execute(stmt)
    slots = list(res.scalars().all())

    duels = []
    for s in slots:
        participants = to_participants_list(s.players_names)
        names = [p.get("display_name", "Jugador") for p in participants if p.get("display_name")]
        team_a = " / ".join(names[:2]) if len(names) >= 2 else "Pareja A"
        team_b = " / ".join(names[2:4]) if len(names) >= 4 else "Pareja B"
        c_name = s.court.name if s.court else "Pista"
        duels.append({
            "slot_id": s.id,
            "time": s.start_time.strftime("%I:%M %p").lstrip("0"),
            "court": c_name,
            "team_a": team_a,
            "team_b": team_b,
            "bet": "🍔 Hamburguesa & Pola (+30 pts)",
            "points_at_stake": 30,
        })

    return {
        "status": "success",
        "date": str(today),
        "duels_count": len(duels),
        "duels": duels,
        "rules": "Gana +30 puntos por victoria en reto oficial o +3 puntos en la Pola comunitaria por acertar el ganador."
    }
