from datetime import date, datetime, time, timezone
from decimal import Decimal
import logging
from typing import List, Optional, Union
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, Field
from app.services.audit import log_activity
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.court import Court
from app.models.customer import Customer
from app.models.slot import HoldStatus, SlotMode, SlotStatus, TimeSlot
from app.schemas.tournament import (
    CancelTournamentRequest,
    RecordWinnersRequest,
    TournamentCardItem,
    TournamentCourtActionRequest,
    TournamentListResponse,
)
from app.services.ranking_engine import award_tournament_points
from app.api.v1.endpoints.slots import to_participants_list


logger = logging.getLogger("yieldpadel.tournaments")

router = APIRouter()


def to_date_obj(val: Optional[Union[date, str]]) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val))


def to_time_obj(val: Optional[Union[time, str]]) -> Optional[time]:
    if val is None:
        return None
    if isinstance(val, time):
        return val
    parts = str(val).split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


@router.get(
    "/",
    response_model=TournamentListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar torneos americanos (Próximos y Pasados)",
)
async def list_tournaments(
    sport: str = Query("ALL", description="Filtrar por deporte ('PADEL', 'PICKLEBALL', 'ALL')"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna el listado de Torneos Americanos agrupados por evento,
    clasificados en Próximos/Activos y Pasados/Finalizados.
    """
    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court), selectinload(TimeSlot.holds))
        .where(TimeSlot.slot_type == "AMERICANO")
        .order_by(TimeSlot.date.desc(), TimeSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    slots = res.scalars().all()

    # Agrupar por (tournament_name, date, start_time)
    grouped = {}
    for s in slots:
        c_sport = (s.sport_type or (s.court.sport_type if s.court else "PADEL") or "PADEL").upper()
        if sport.upper() != "ALL" and c_sport != sport.upper():
            continue

        t_name = s.tournament_name or "Torneo Americano"
        group_key = f"{t_name}___{s.date}___{s.start_time}"

        if group_key not in grouped:
            grouped[group_key] = {
                "tournament_name": t_name,
                "date": s.date,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "sport_type": c_sport,
                "modality": s.tournament_type or "PAREJA_FIJA",
                "prize_pool": float(s.prize_pool or 250000.0),
                "is_finished": bool(s.is_finished),
                "winners_names": s.winners_names,
                "runner_up_names": s.runner_up_names,
                "courts": [],
                "slot_ids": [],
                "slots": [],
            }

        grouped[group_key]["courts"].append(s.court)
        grouped[group_key]["slot_ids"].append(s.id)
        grouped[group_key]["slots"].append(s)

    today = date.today()
    upcoming: List[TournamentCardItem] = []
    past: List[TournamentCardItem] = []

    for key, data in grouped.items():
        court_names = [c.name for c in data["courts"] if c]
        court_ids = [str(c.id) for c in data["courts"] if c]
        num_courts = len(court_names)

        # Capacidad real según pistas asignadas
        total_cap = sum(s.capacity or 4 for s in data["slots"]) if data["slots"] else (num_courts * 4)
        actual_booked = sum(s.booked_spots or 0 for s in data["slots"]) if data["slots"] else 0
        booked_spots = total_cap if data["is_finished"] else min(total_cap, actual_booked)

        is_past = (data["date"] < today) or data["is_finished"]

        item = TournamentCardItem(
            id=key,
            tournament_name=data["tournament_name"],
            date=data["date"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            sport_type=data["sport_type"],
            modality=data["modality"],
            courts_count=num_courts,
            court_names=court_names,
            court_ids=court_ids,
            slot_ids=data["slot_ids"],
            booked_spots=booked_spots,
            total_capacity=total_cap,
            registered_players_count=booked_spots,
            max_players=total_cap,
            price_per_player=45000.0,
            prize_pool=data["prize_pool"],
            is_finished=data["is_finished"],
            winners_names=data["winners_names"],
            runner_up_names=data["runner_up_names"],
            is_active_or_upcoming=not is_past,
        )

        if is_past:
            past.append(item)
        else:
            upcoming.append(item)

    return TournamentListResponse(
        status="success",
        sport=sport.upper(),
        upcoming=upcoming,
        past=past,
        total_count=len(upcoming) + len(past),
    )


@router.post(
    "/record-winners",
    status_code=status.HTTP_200_OK,
    summary="Registrar campeones y subcampeones de un torneo americano",
)
async def record_winners(
    payload: RecordWinnersRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Registra los ganadores de un torneo, asigna puntos (+100 campeones, +50 subcampeones),
    evalúa victorias consecutivas para sugerir ascensos y finaliza el torneo.
    """
    if not payload.winner_names:
        raise HTTPException(status_code=400, detail="Debe ingresar al menos un nombre de ganador/campeón.")

    # 1. Buscar los slots asociados al torneo
    target_date = to_date_obj(payload.date)
    target_start_time = to_time_obj(payload.start_time)
    slots_to_update: List[TimeSlot] = []

    if payload.slot_ids:
        stmt = select(TimeSlot).where(TimeSlot.id.in_(payload.slot_ids))
        res = await db.execute(stmt)
        slots_to_update = list(res.scalars().all())

    if not slots_to_update and payload.slot_id:
        stmt = select(TimeSlot).where(TimeSlot.id == payload.slot_id)
        res = await db.execute(stmt)
        s = res.scalar_one_or_none()
        if s:
            # Buscar todos los slots hermanos del torneo
            if s.tournament_name and s.date:
                t_stmt = select(TimeSlot).where(
                    TimeSlot.tournament_name == s.tournament_name,
                    TimeSlot.date == s.date,
                    TimeSlot.start_time == s.start_time,
                )
                slots_to_update = list((await db.execute(t_stmt)).scalars().all())
            else:
                slots_to_update = [s]

    if not slots_to_update and payload.tournament_name and target_date:
        stmt = select(TimeSlot).where(
            TimeSlot.tournament_name.ilike(f"%{payload.tournament_name}%"),
            TimeSlot.date == target_date,
        )
        slots_to_update = list((await db.execute(stmt)).scalars().all())

    if not slots_to_update and payload.tournament_name:
        stmt = select(TimeSlot).where(
            TimeSlot.tournament_name.ilike(f"%{payload.tournament_name}%")
        )
        slots_to_update = list((await db.execute(stmt)).scalars().all())

    win_str = ", ".join(payload.winner_names)
    run_str = ", ".join(payload.runner_up_names) if payload.runner_up_names else None

    for slot in slots_to_update:
        slot.is_finished = True
        slot.winners_names = win_str
        slot.runner_up_names = run_str

    # 2. Asignar puntos en el motor de ranking
    champs, runners = await award_tournament_points(
        db=db,
        winner_names=payload.winner_names,
        winner_phones=payload.winner_phones,
        runner_up_names=payload.runner_up_names,
        runner_up_phones=payload.runner_up_phones,
    )

    await db.commit()

    return {
        "status": "success",
        "message": f"🏆 Ganadores registrados exitosamente: {win_str}",
        "champions": [
            {
                "id": c.id,
                "name": c.name,
                "category": c.category,
                "ranking_points": c.ranking_points,
                "titles_count": c.titles_count,
                "consecutive_wins": c.consecutive_wins,
                "promotion_recommended": c.promotion_recommended,
                "recommended_category": c.recommended_category,
            }
            for c in champs
        ],
        "runners_up": [
            {
                "id": r.id,
                "name": r.name,
                "category": r.category,
                "ranking_points": r.ranking_points,
            }
            for r in runners
        ],
        "slots_updated": len(slots_to_update),
    }


@router.post(
    "/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancelar torneo americano y liberar las pistas asignadas",
)
async def cancel_tournament(
    payload: CancelTournamentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Cancela un evento americano, liberando las pistas asociadas a estado AVAILABLE.
    """
    target_date = to_date_obj(payload.date)
    target_start_time = to_time_obj(payload.start_time)
    stmt = select(TimeSlot).where(
        TimeSlot.tournament_name.ilike(f"%{payload.tournament_name}%"),
        TimeSlot.date == target_date,
        TimeSlot.start_time == target_start_time,
    )
    res = await db.execute(stmt)
    slots = res.scalars().all()

    if not slots:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontraron pistas asociadas al torneo '{payload.tournament_name}' en esa fecha y horario.",
        )

    for slot in slots:
        slot.slot_type = "MATCH"
        slot.status = SlotStatus.AVAILABLE
        slot.tournament_type = None
        slot.tournament_name = None
        slot.prize_pool = None
        slot.category = "4ta"
        slot.booked_spots = 0
        slot.players_names = []
        slot.is_finished = False
        slot.winners_names = None
        slot.runner_up_names = None

    await db.commit()

    # Operational Audit Trail
    try:
        await log_activity(
            db=db,
            action="CANCEL_TOURNAMENT",
            entity_name="TOURNAMENT",
            details=f"Cancelación del Torneo Americano '{payload.tournament_name}' del {payload.date} ({payload.start_time}). Se liberaron {len(slots)} pistas.",
            username_snapshot="Camilo Real (Director Deportivo)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error in cancel_tournament: {e}")

    return {
        "status": "success",
        "message": f"Torneo '{payload.tournament_name}' cancelado con éxito. {len(slots)} pistas liberadas a DISPONIBLE.",
        "freed_slots_count": len(slots),
    }


@router.post(
    "/add-court",
    status_code=status.HTTP_200_OK,
    summary="Agregar una pista adicional a un torneo americano",
)
async def add_court_to_tournament(
    payload: TournamentCourtActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Agrega una pista adicional al torneo americano tras validar que no haya colisión.
    """
    try:
        c_uuid = uuid.UUID(payload.court_id)
    except Exception:
        court_res = await db.execute(select(Court).where(Court.name.ilike(f"%{payload.court_id}%")))
        c_obj = court_res.scalars().first()
        if not c_obj:
            raise HTTPException(status_code=404, detail="Pista no encontrada.")
        c_uuid = c_obj.id

    target_date = to_date_obj(payload.date)
    target_start_time = to_time_obj(payload.start_time)

    # Obtener un slot existente del torneo para copiar duración, nombre y premio
    ref_stmt = select(TimeSlot).where(
        TimeSlot.tournament_name.ilike(f"%{payload.tournament_name}%"),
        TimeSlot.date == target_date,
        TimeSlot.start_time == target_start_time,
    )
    ref_slot = (await db.execute(ref_stmt)).scalars().first()
    if not ref_slot:
        raise HTTPException(status_code=404, detail="No se encontró el torneo de referencia.")

    # Validar que la nueva cancha no tenga reservas activas en ese horario
    overlap_stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.holds), selectinload(TimeSlot.court))
        .where(
            TimeSlot.court_id == c_uuid,
            TimeSlot.date == target_date,
            TimeSlot.start_time < ref_slot.end_time,
            TimeSlot.end_time > target_start_time,
        )
    )
    overlaps = list((await db.execute(overlap_stmt)).scalars().all())
    for s in overlaps:
        has_active_holds = any(h.status == HoldStatus.ACTIVE for h in s.holds)
        is_booked = s.status in [SlotStatus.FULLY_BOOKED, SlotStatus.PARTIALLY_BOOKED]
        is_class = s.slot_type in ["CLASS", "ACADEMY"]
        if is_booked or has_active_holds or is_class or s.booked_spots > 0:
            c_name = s.court.name if s.court else "Pista seleccionada"
            raise HTTPException(
                status_code=400,
                detail=f"Colisión: {c_name} ya tiene una reserva activa ({s.start_time}-{s.end_time}).",
            )

    if overlaps:
        target_slot = overlaps[0]
        target_slot.start_time = target_start_time
        target_slot.end_time = ref_slot.end_time
        target_slot.slot_type = "AMERICANO"
        target_slot.tournament_type = ref_slot.tournament_type
        target_slot.tournament_name = ref_slot.tournament_name
        target_slot.prize_pool = ref_slot.prize_pool
        target_slot.category = ref_slot.category
        target_slot.status = SlotStatus.FULLY_BOOKED
        target_slot.booked_spots = 4
        target_slot.players_names = ref_slot.players_names
        for extra in overlaps[1:]:
            await db.delete(extra)
    else:
        new_slot = TimeSlot(
            court_id=c_uuid,
            date=target_date,
            start_time=target_start_time,
            end_time=ref_slot.end_time,
            total_price=ref_slot.total_price,
            mode=SlotMode.SPLIT_MATCH,
            capacity=4,
            booked_spots=4,
            status=SlotStatus.FULLY_BOOKED,
            category=ref_slot.category,
            slot_type="AMERICANO",
            tournament_type=ref_slot.tournament_type,
            tournament_name=ref_slot.tournament_name,
            prize_pool=ref_slot.prize_pool,
            players_names=ref_slot.players_names,
            sport_type=ref_slot.sport_type,
        )
        db.add(new_slot)

    await db.commit()
    return {"status": "success", "message": f"Pista agregada al torneo '{payload.tournament_name}' con éxito."}


@router.post(
    "/remove-court",
    status_code=status.HTTP_200_OK,
    summary="Quitar una pista de un torneo americano",
)
async def remove_court_from_tournament(
    payload: TournamentCourtActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Quita una pista de un torneo americano, liberando el slot a DISPONIBLE.
    """
    try:
        c_uuid = uuid.UUID(payload.court_id)
    except Exception:
        court_res = await db.execute(select(Court).where(Court.name.ilike(f"%{payload.court_id}%")))
        c_obj = court_res.scalars().first()
        if not c_obj:
            raise HTTPException(status_code=404, detail="Pista no encontrada.")
        c_uuid = c_obj.id

    target_date = to_date_obj(payload.date)
    target_start_time = to_time_obj(payload.start_time)

    stmt = select(TimeSlot).where(
        TimeSlot.tournament_name.ilike(f"%{payload.tournament_name}%"),
        TimeSlot.date == target_date,
        TimeSlot.start_time == target_start_time,
        TimeSlot.court_id == c_uuid,
    )
    slot = (await db.execute(stmt)).scalars().first()
    if not slot:
        raise HTTPException(status_code=404, detail="No se encontró la pista asignada a este torneo.")

    slot.slot_type = "MATCH"
    slot.status = SlotStatus.AVAILABLE
    slot.tournament_type = None
    slot.tournament_name = None
    slot.prize_pool = None
    slot.category = "4ta"
    slot.booked_spots = 0
    slot.players_names = []

    await db.commit()
    return {"status": "success", "message": f"Pista removida del torneo '{payload.tournament_name}' exitosamente."}


class RegisterTournamentPlayerRequest(BaseModel):
    tournament_name: Optional[str] = None
    slot_id: Optional[int] = None
    slot_ids: Optional[List[int]] = None
    date: Optional[Union[date, str]] = None
    start_time: Optional[Union[time, str]] = None
    player1_name: str
    player1_phone: str
    player2_name: Optional[str] = None
    player2_phone: Optional[str] = None
    membership_tier: Optional[str] = "ESTANDAR"


@router.post(
    "/register-player",
    status_code=status.HTTP_200_OK,
    summary="Inscribir jugador o pareja en un torneo americano",
)
@router.post(
    "/register-pair",
    status_code=status.HTTP_200_OK,
    summary="Inscribir pareja en un torneo americano",
)
async def register_player_to_tournament(
    payload: RegisterTournamentPlayerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Inscribe una pareja o jugador en un torneo americano, calcula el descuento según
    su membresía (TAPIA: 40%, COELLO: 30%, GALAN: 20%, CHINGOTTO: 10%, LEBRON: 20%),
    actualiza los cupos inscritos y guarda el cliente en el CRM si no existía.
    """
    p1_name = payload.player1_name.strip()
    p1_phone = payload.player1_phone.strip()
    if not p1_name or not p1_phone:
        raise HTTPException(status_code=400, detail="Nombre y teléfono del Jugador 1 son requeridos.")

    players_to_register = [{"name": p1_name, "phone": p1_phone}]
    if payload.player2_name and payload.player2_name.strip():
        p2_name = payload.player2_name.strip()
        p2_phone = (payload.player2_phone or f"{p1_phone}#P2").strip()
        players_to_register.append({"name": p2_name, "phone": p2_phone})

    # 1. Buscar slots del torneo
    target_date = to_date_obj(payload.date)
    target_start_time = to_time_obj(payload.start_time)
    slots: List[TimeSlot] = []

    if payload.slot_ids:
        stmt = select(TimeSlot).where(TimeSlot.id.in_(payload.slot_ids)).with_for_update()
        slots = list((await db.execute(stmt)).scalars().all())
    elif payload.slot_id:
        stmt = select(TimeSlot).where(TimeSlot.id == payload.slot_id).with_for_update()
        s = (await db.execute(stmt)).scalar_one_or_none()
        if s:
            if s.tournament_name and s.date:
                t_stmt = select(TimeSlot).where(
                    TimeSlot.tournament_name == s.tournament_name,
                    TimeSlot.date == s.date,
                    TimeSlot.start_time == s.start_time,
                ).with_for_update()
                slots = list((await db.execute(t_stmt)).scalars().all())
            else:
                slots = [s]
    elif payload.tournament_name and target_date:
        stmt = select(TimeSlot).where(
            TimeSlot.tournament_name.ilike(f"%{payload.tournament_name}%"),
            TimeSlot.date == target_date,
        ).with_for_update()
        slots = list((await db.execute(stmt)).scalars().all())
    elif payload.tournament_name:
        stmt = select(TimeSlot).where(
            TimeSlot.tournament_name.ilike(f"%{payload.tournament_name}%")
        ).with_for_update()
        slots = list((await db.execute(stmt)).scalars().all())

    if not slots:
        raise HTTPException(status_code=404, detail="No se encontraron pistas asociadas a este torneo.")

    # 2. Descuento según membresía
    membership = (payload.membership_tier or "ESTANDAR").upper()
    discount_map = {
        "TAPIA": 40,
        "COELLO": 30,
        "GALAN": 20,
        "CHINGOTTO": 10,
        "LEBRON": 20,
        "ESTANDAR": 0,
    }
    discount_pct = discount_map.get(membership, 0)
    base_price = 45000.0
    final_price_per_player = base_price * (1.0 - discount_pct / 100.0)

    # 3. Asignar jugadores en las pistas con espacio
    remaining_to_assign = list(players_to_register)
    for s in slots:
        if not remaining_to_assign:
            break
        available = (s.capacity or 4) - (s.booked_spots or 0)
        if available <= 0:
            continue

        take = min(available, len(remaining_to_assign))
        current_participants = to_participants_list(s.players_names)

        for _ in range(take):
            p = remaining_to_assign.pop(0)
            current_participants.append({
                "spot_index": len(current_participants) + 1,
                "phone": p["phone"],
                "display_name": p["name"],
                "client_tier": membership,
                "host_phone": p1_phone if p["name"] != p1_name else None,
            })
            s.booked_spots = (s.booked_spots or 0) + 1

        s.players_names = current_participants
        if s.booked_spots >= (s.capacity or 4):
            s.status = SlotStatus.FULLY_BOOKED
        else:
            s.status = SlotStatus.PARTIALLY_BOOKED

    # 4. Asegurar o actualizar los jugadores en la tabla de Customer
    for p in players_to_register:
        c_res = await db.execute(select(Customer).where(Customer.phone == p["phone"]))
        cust = c_res.scalar_one_or_none()
        if not cust:
            cust = Customer(
                name=p["name"],
                phone=p["phone"],
                category="4ta",
                client_type="Socio VIP" if membership != "ESTANDAR" else "Estándar",
                membership_tier=membership,
                is_first_visit=True,
                onboarding_status="PENDING",
            )
            db.add(cust)
        else:
            if membership != "ESTANDAR":
                cust.membership_tier = membership

    await db.commit()

    total_cap = sum(s.capacity or 4 for s in slots)
    total_booked = sum(s.booked_spots or 0 for s in slots)

    try:
        await log_activity(
            db=db,
            action="REGISTER_TOURNAMENT_PLAYER",
            entity_name="TOURNAMENT",
            details=f"Inscripción de '{p1_name}' ({membership} - {discount_pct}% desc) en torneo. Cupos totales: {total_booked}/{total_cap}.",
            username_snapshot="Camilo Real (Recepción)"
        )
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Error in register_player: {e}")

    return {
        "status": "success",
        "message": f"Inscripción exitosa para {p1_name}. Descuento aplicado: {discount_pct}% (Tarifa: ${final_price_per_player:,.0f} COP).",
        "tournament_name": payload.tournament_name or (slots[0].tournament_name if slots else "Americano"),
        "registered_players_count": total_booked,
        "max_players": total_cap,
        "booked_spots": total_booked,
        "total_capacity": total_cap,
        "discount_percent": discount_pct,
        "price_paid_per_player": final_price_per_player,
    }


@router.post("/create", status_code=status.HTTP_201_CREATED)
@router.post("/create-americano", status_code=status.HTTP_201_CREATED)
async def create_tournament_endpoint(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Crea un Torneo Americano delegando en la lógica de creación multicancha."""
    from app.schemas.slot import CreateAmericanoRequest
    from app.api.v1.endpoints.slots import create_americano

    parsed = CreateAmericanoRequest(**payload)
    return await create_americano(payload=parsed, db=db)


class RecordChallengeWinnerRequest(BaseModel):
    winner_id: Optional[int] = None
    winner_name: str
    challenger_name: Optional[str] = None
    rival_name: Optional[str] = None
    bet: Optional[str] = None
    slot_id: Optional[int] = None


@router.post(
    "/record-challenge-winner",
    status_code=status.HTTP_200_OK,
    summary="Registrar ganador de un partido de reto y otorgar +30 puntos de ranking",
)
async def record_challenge_winner(
    payload: RecordChallengeWinnerRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.services.ranking_engine import find_or_create_player_by_name_or_phone

    customer: Optional[Customer] = None
    if payload.winner_id:
        stmt = select(Customer).where(Customer.id == payload.winner_id)
        res = await db.execute(stmt)
        customer = res.scalar_one_or_none()

    if not customer and payload.winner_name:
        customer = await find_or_create_player_by_name_or_phone(db, payload.winner_name.strip())

    if not customer:
        raise HTTPException(status_code=404, detail="Jugador ganador no encontrado")

    # Sumar +30 puntos de ranking directamente
    customer.ranking_points += 30
    customer.consecutive_wins = (customer.consecutive_wins or 0) + 1

    await db.commit()
    await db.refresh(customer)

    try:
        await log_activity(
            db=db,
            action="CHALLENGE_WINNER_RECORDED",
            entity_name="customer",
            entity_id=str(customer.id),
            details={
                "winner_name": customer.name,
                "challenger": payload.challenger_name,
                "rival": payload.rival_name,
                "bet": payload.bet,
                "points_awarded": 30,
                "new_total_points": customer.ranking_points,
            },
        )
    except Exception as e:
        logger.warning(f"Error logging challenge activity: {e}")

    return {
        "success": True,
        "message": f"¡Victoria registrada! Se sumaron +30 puntos a {customer.name} (Total: {customer.ranking_points} pts).",
        "winner": {
            "id": customer.id,
            "name": customer.name,
            "ranking_points": customer.ranking_points,
            "category": customer.category,
            "consecutive_wins": customer.consecutive_wins,
        },
        "points_awarded": 30,
        "bet": payload.bet,
    }



