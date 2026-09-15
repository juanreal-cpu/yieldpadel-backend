from datetime import date, datetime, time, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Union
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, Field
from app.services.audit import log_activity, record_audit_log
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
from app.schemas.slot import CreateAmericanoRequest
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
        .where(TimeSlot.slot_type.in_(["AMERICANO", "TOURNAMENT"]))
        .order_by(TimeSlot.date.desc(), TimeSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    slots = res.scalars().all()

    # Agrupar por (tournament_name, date, start_time)
    grouped = {}
    for s in slots:
        c_sport = ((s.court.sport_type if s.court else None) or s.sport_type or "PADEL").upper()
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

    # Log de Auditoría Operativa
    try:
        await log_activity(
            db=db,
            action="TORNEO_GANADORES",
            entity_name="TOURNAMENT",
            entity_id=payload.tournament_name or "Torneo Americano",
            details=f"Campeones: {win_str} | Subcampeones: {run_str or 'N/A'}",
            username_snapshot="Camilo Real (Recepción)",
        )
    except Exception as e:
        logger.warning(f"Error logging tournament winners audit: {e}")

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
    from app.api.v1.endpoints.slots import resolve_court
    court = await resolve_court(payload.court_id, db)
    if not court:
        raise HTTPException(status_code=404, detail=f"Pista '{payload.court_id}' no encontrada.")
    c_uuid = court.id

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

    c_cap = court.max_capacity or 4
    c_sport = (court.sport_type or ref_slot.sport_type or "PADEL").upper()

    if overlaps:
        target_slot = overlaps[0]
        target_slot.court_id = c_uuid
        target_slot.club_id = 1
        target_slot.start_time = target_start_time
        target_slot.end_time = ref_slot.end_time
        target_slot.slot_type = "TOURNAMENT"
        target_slot.tournament_type = ref_slot.tournament_type
        target_slot.tournament_name = ref_slot.tournament_name
        target_slot.prize_pool = ref_slot.prize_pool
        target_slot.price_total_cop = ref_slot.price_total_cop or ref_slot.total_price
        target_slot.category = ref_slot.category
        target_slot.status = SlotStatus.BLOCKED
        target_slot.capacity = c_cap
        target_slot.booked_spots = c_cap
        target_slot.players_names = ref_slot.players_names
        target_slot.sport_type = c_sport
        for extra in overlaps[1:]:
            await db.delete(extra)
    else:
        new_slot = TimeSlot(
            court_id=c_uuid,
            club_id=1,
            date=target_date,
            start_time=target_start_time,
            end_time=ref_slot.end_time,
            total_price=ref_slot.total_price,
            price_total_cop=ref_slot.price_total_cop or ref_slot.total_price,
            price=ref_slot.price,
            mode=SlotMode.FULL_COURT,
            capacity=c_cap,
            booked_spots=c_cap,
            status=SlotStatus.BLOCKED,
            category=ref_slot.category,
            slot_type="TOURNAMENT",
            tournament_type=ref_slot.tournament_type,
            tournament_name=ref_slot.tournament_name,
            prize_pool=ref_slot.prize_pool,
            players_names=ref_slot.players_names,
            sport_type=c_sport,
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
    if membership == "ESTANDAR":
        c_res_p1 = await db.execute(
            select(Customer)
            .options(selectinload(Customer.membership_plan))
            .where(or_(Customer.phone == p1_phone, Customer.name.ilike(p1_name)))
        )
        c_p1 = c_res_p1.scalars().first()
        if c_p1:
            if c_p1.membership_plan and c_p1.membership_plan.name:
                membership = c_p1.membership_plan.name.upper()
            elif c_p1.membership_tier and c_p1.membership_tier.upper() != "ESTANDAR":
                membership = c_p1.membership_tier.upper()

    discount_map = {
        "TAPIA": 40,
        "COELLO": 30,
        "GALAN": 20,
        "CHINGOTTO": 10,
        "LEBRON": 20,
        "ORO": 40,
        "PLATA": 30,
        "BRONCE": 20,
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
        cust = c_res.scalars().first()
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
        target_slot_id = slots[0].id if slots else payload.slot_id or ""
        for p in players_to_register:
            await record_audit_log(
                db=db,
                action="ADD_PLAYER",
                entity="slot_participants",
                details=f"Se agregó al jugador {p['name']} ({p['phone']}) al turno {target_slot_id}",
                operator_user="RECEPCION",
                club_id=1,
            )
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
    payload: CreateAmericanoRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Crea un Torneo Americano delegando en la lógica de creación multicancha."""
    from app.api.v1.endpoints.slots import create_americano

    return await create_americano(payload=payload, db=db)


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


@router.get(
    "/{tournament_id}/participants",
    summary="Listar participantes inscritos en un torneo americano",
)
async def get_tournament_participants(
    tournament_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna la lista detallada de participantes de un torneo americano,
    buscando por key de torneo ('Nombre___Fecha___Hora') o slot_id.
    """
    slots: List[TimeSlot] = []

    # 1. Si tournament_id tiene el formato "t_name___date___time"
    if "___" in tournament_id:
        parts = tournament_id.split("___")
        t_name = parts[0]
        t_date_str = parts[1] if len(parts) > 1 else None
        t_time_str = parts[2] if len(parts) > 2 else None

        stmt = select(TimeSlot).options(
            selectinload(TimeSlot.court),
            selectinload(TimeSlot.holds),
            selectinload(TimeSlot.bookings),
        ).where(TimeSlot.slot_type.in_(["AMERICANO", "TOURNAMENT"]))

        if t_name:
            stmt = stmt.where(TimeSlot.tournament_name == t_name)
        if t_date_str:
            stmt = stmt.where(TimeSlot.date == to_date_obj(t_date_str))
        if t_time_str:
            stmt = stmt.where(TimeSlot.start_time == to_time_obj(t_time_str))

        res = await db.execute(stmt)
        slots = list(res.scalars().all())
    else:
        # Intentar por slot_id numérico o por nombre
        if tournament_id.isdigit():
            s_res = await db.execute(
                select(TimeSlot).options(
                    selectinload(TimeSlot.court),
                    selectinload(TimeSlot.holds),
                    selectinload(TimeSlot.bookings),
                ).where(TimeSlot.id == int(tournament_id))
            )
            slot_found = s_res.scalar_one_or_none()
            if slot_found:
                if slot_found.tournament_name and slot_found.date:
                    stmt = select(TimeSlot).options(
                        selectinload(TimeSlot.court),
                        selectinload(TimeSlot.holds),
                        selectinload(TimeSlot.bookings),
                    ).where(
                        TimeSlot.tournament_name == slot_found.tournament_name,
                        TimeSlot.date == slot_found.date,
                        TimeSlot.start_time == slot_found.start_time,
                    )
                    slots = list((await db.execute(stmt)).scalars().all())
                else:
                    slots = [slot_found]
        if not slots:
            stmt = select(TimeSlot).options(
                selectinload(TimeSlot.court),
                selectinload(TimeSlot.holds),
                selectinload(TimeSlot.bookings),
            ).where(TimeSlot.tournament_name.ilike(f"%{tournament_id}%"))
            slots = list((await db.execute(stmt)).scalars().all())

    if not slots:
        return {
            "status": "success",
            "tournament_id": tournament_id,
            "tournament_name": "Torneo",
            "participants": [],
            "total_registered": 0,
            "max_capacity": 16,
        }

    first_slot = slots[0]
    tournament_name = first_slot.tournament_name or "Torneo Americano"
    total_cap = sum(s.capacity or 4 for s in slots)

    # Cargar clientes en memoria para verificar categoría y teléfono
    cust_res = await db.execute(select(Customer))
    all_customers = cust_res.scalars().all()
    cust_by_name = {c.name.strip().lower(): c for c in all_customers if c.name}
    cust_by_phone = {c.phone.strip(): c for c in all_customers if c.phone}

    participants_map: Dict[str, dict] = {}

    for s in slots:
        # 1. Participantes desde s.players_names
        p_list = to_participants_list(s.players_names)
        for p in p_list:
            p_name = (p.get("display_name") or p.get("name") or "Jugador").strip()
            if not p_name or p_name.lower() in ("jugador", "pala libre", "cupo libre"):
                continue
            norm_name = p_name.lower()
            p_phone = p.get("phone") or ""
            matched_cust = cust_by_name.get(norm_name) or cust_by_phone.get(p_phone)

            payment_status = "PAGADO"
            category = (matched_cust.category if matched_cust else None) or s.category or "4ta"
            phone = (matched_cust.phone if matched_cust else None) or p_phone or "No registrado"
            tier = (matched_cust.membership_tier if matched_cust else None) or p.get("client_tier") or "ESTANDAR"

            participants_map[norm_name] = {
                "name": p_name,
                "phone": phone,
                "category": category,
                "membership_tier": tier,
                "payment_status": payment_status,
                "spot_index": len(participants_map) + 1,
            }

        # 2. Bookings asociados
        for b in s.bookings or []:
            b_name = (b.customer_name or "").strip()
            if not b_name:
                continue
            norm_name = b_name.lower()
            if norm_name not in participants_map:
                matched_cust = cust_by_name.get(norm_name)
                participants_map[norm_name] = {
                    "name": b_name,
                    "phone": (matched_cust.phone if matched_cust else None) or getattr(b, "customer_phone", "") or "No registrado",
                    "category": (matched_cust.category if matched_cust else None) or s.category or "4ta",
                    "membership_tier": (matched_cust.membership_tier if matched_cust else None) or "ESTANDAR",
                    "payment_status": getattr(b, "payment_status", "PAGADO") or "PAGADO",
                    "spot_index": len(participants_map) + 1,
                }

        # 3. Holds activos
        for h in s.holds or []:
            if h.status == HoldStatus.ACTIVE and h.customer_phone:
                h_phone = h.customer_phone.strip()
                matched_cust = cust_by_phone.get(h_phone)
                name = (matched_cust.name if matched_cust else None) or f"Reserva {h_phone[-4:]}"
                norm_name = name.lower()
                if norm_name not in participants_map:
                    participants_map[norm_name] = {
                        "name": name,
                        "phone": h_phone,
                        "category": (matched_cust.category if matched_cust else None) or s.category or "4ta",
                        "membership_tier": (matched_cust.membership_tier if matched_cust else None) or "ESTANDAR",
                        "payment_status": getattr(h, "payment_status", "PENDIENTE") or "PENDIENTE",
                        "spot_index": len(participants_map) + 1,
                    }

    participants = list(participants_map.values())

    return {
        "status": "success",
        "tournament_id": tournament_id,
        "tournament_name": tournament_name,
        "date": str(first_slot.date),
        "start_time": str(first_slot.start_time),
        "total_registered": len(participants),
        "max_capacity": total_cap,
        "participants": participants,
    }


# Forward / Alias routes for official tournaments under /tournaments/official
from app.api.v1.endpoints import official_tournaments as ot_module

@router.post("/official/{tournament_id}/enroll-pair", status_code=status.HTTP_201_CREATED)
async def enroll_pair_alias(
    tournament_id: int,
    payload: ot_module.RegisterTeamRequest,
    db: AsyncSession = Depends(get_db),
):
    return await ot_module.register_team(payload=payload, tournament_id=tournament_id, db=db)


@router.post("/official/{tournament_id}/generate-matches", status_code=status.HTTP_200_OK)
async def generate_matches_alias(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await ot_module.generate_matches(tournament_id=tournament_id, db=db)


@router.post("/official/matches/{match_id}/record-score", status_code=status.HTTP_200_OK)
async def record_score_alias(
    match_id: int,
    payload: ot_module.RecordScoreRequest,
    db: AsyncSession = Depends(get_db),
):
    return await ot_module.record_score(payload=payload, match_id=match_id, db=db)


# ==============================================================================
# MÓDULO DE TORNEOS AMERICANOS EN TIEMPO REAL (REAL-TIME AMERICANO ENGINE)
# ==============================================================================
from app.models.official_tournaments import (
    OfficialTournament,
    OfficialTournamentStatus,
    TournamentFormatType,
    TournamentGroup,
    TournamentMatch,
    TournamentMatchRule,
    TournamentTeam,
    TournamentTiebreakRule,
)
from app.services.ranking_engine import get_next_category


class CreateAmericanoTournamentRequest(BaseModel):
    name: str = Field(..., description="Nombre del Torneo Americano (ej: Americano Nocturno Express)")
    sport_type: str = Field("PADEL", description="PADEL, PICKLEBALL")
    category: str = Field("4ta", description="Categoría (1ra, 2da, 3ra, 4ta, 5ta, 6ta)")
    modality: str = Field("PAREJA_FIJA", description="PAREJA_FIJA o ROTATIVA_KING_OF_COURT")
    scoring_system: str = Field("POINTS_32", description="POINTS_32, POINTS_24, POINTS_40, SETS")
    target_points: int = Field(32, description="Puntos meta por partido (default: 32)")
    tiebreak_rule: str = Field("GAMES_DIFF", description="GAMES_DIFF, HEAD_TO_HEAD, SETS_DIFF")
    assigned_court_ids: List[str] = Field(..., description="Lista de IDs UUID de pistas físicas asignadas")
    player_ids: Optional[List[Union[int, str]]] = Field(default_factory=list, description="Lista de IDs o teléfonos de jugadores CRM")
    teams: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Parejas fijas [{'name': '...', 'p1': 1, 'p2': 2}]")
    start_date: Optional[str] = Field(None, description="Fecha YYYY-MM-DD")
    start_time: Optional[str] = Field("18:00", description="Hora de inicio HH:MM")


class LiveScoreUpdateRequest(BaseModel):
    delta_t1: Optional[int] = Field(None, description="Cambio de puntos (+1, -1) para equipo 1")
    delta_t2: Optional[int] = Field(None, description="Cambio de puntos (+1, -1) para equipo 2")
    team1_points: Optional[int] = Field(None, description="Puntos directos para equipo 1")
    team2_points: Optional[int] = Field(None, description="Puntos directos para equipo 2")
    status: Optional[str] = Field(None, description="IN_PROGRESS, COMPLETED")
    winner_team_id: Optional[int] = Field(None, description="ID del equipo ganador forzado")


class CloseTournamentRequest(BaseModel):
    champion_team_id: Optional[int] = Field(None, description="ID del equipo o jugador campeón")
    runner_up_team_id: Optional[int] = Field(None, description="ID del equipo o jugador subcampeón")
    champions_points: int = Field(100, description="Puntos de ranking para el podio campeón")
    runner_up_points: int = Field(50, description="Puntos de ranking para el podio subcampeón")


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Crear Torneo Americano en Tiempo Real y generar cruces automáticos",
)
async def create_live_americano_tournament(
    payload: CreateAmericanoTournamentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Crea un nuevo Torneo Americano, asocia y valida las canchas activas,
    inscribe a los participantes desde `customers` y genera el fixture
    balanceado de partidos en las pistas seleccionadas.
    """
    if len(payload.assigned_court_ids) < 1:
        raise HTTPException(status_code=400, detail="Debe asignar al menos una pista deportiva para el torneo.")

    # 1. Crear el torneo en official_tournaments
    t_date = to_date_obj(payload.start_date) or date.today()
    t_time = to_time_obj(payload.start_time) or time(18, 0)

    # Determinar regla de partido según sistema de puntuación
    rule_map = {
        "POINTS_32": TournamentMatchRule.TIMED_MATCH,
        "POINTS_24": TournamentMatchRule.TIMED_MATCH,
        "POINTS_40": TournamentMatchRule.TIMED_MATCH,
        "SETS": TournamentMatchRule.BEST_OF_3_SHORT,
    }
    match_rule_val = rule_map.get(payload.scoring_system, TournamentMatchRule.TIMED_MATCH)

    tiebreak_map = {
        "GAMES_DIFF": TournamentTiebreakRule.GAMES_DIFF,
        "HEAD_TO_HEAD": TournamentTiebreakRule.HEAD_TO_HEAD,
        "SETS_DIFF": TournamentTiebreakRule.SETS_DIFF,
    }
    tb_rule_val = tiebreak_map.get(payload.tiebreak_rule, TournamentTiebreakRule.GAMES_DIFF)

    tourn = OfficialTournament(
        name=payload.name,
        sport_type=payload.sport_type.upper(),
        category=payload.category,
        format_type=TournamentFormatType.GROUPS_PLAYOFFS,
        match_rule=match_rule_val,
        match_duration_minutes=30 if "POINTS" in payload.scoring_system else 60,
        tiebreak_rule=tb_rule_val,
        status=OfficialTournamentStatus.IN_PROGRESS,
        start_date=t_date,
        end_date=t_date,
        start_time=t_time,
        end_time=time(23, 0),
        assigned_court_ids=payload.assigned_court_ids,
    )
    db.add(tourn)
    await db.flush()

    # 2. Crear Grupo Único (General Americano)
    group = TournamentGroup(
        tournament_id=tourn.id,
        name="Mesa Principal Americano",
        standings_json=[],
    )
    db.add(group)
    await db.flush()

    # 3. Resolver e inscribir participantes
    resolved_teams: List[TournamentTeam] = []

    # Helper para buscar o registrar customer
    async def get_or_create_customer(identifier: Union[int, str], fallback_name: str, unique_idx: int = 1) -> Customer:
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit() and len(identifier) < 7):
            res = await db.execute(select(Customer).where(Customer.id == int(identifier)))
            c = res.scalar_one_or_none()
            if c:
                return c
        ident_str = str(identifier).strip()
        res = await db.execute(select(Customer).where(or_(Customer.phone == ident_str, Customer.name.ilike(ident_str))))
        c = res.scalars().first()
        if c:
            return c
        # Crear cliente con teléfono único si no existe
        import time as _time_mod
        now_ts = str(int(_time_mod.time()))[-5:]
        unique_phone = ident_str if (ident_str.isdigit() and len(ident_str) >= 10) else f"300{now_ts}{unique_idx:02d}"
        new_c = Customer(
            name=fallback_name if not ident_str.isdigit() else f"Jugador {ident_str[-4:]}",
            phone=unique_phone,
            category=payload.category,
            client_type="Estándar",
        )
        db.add(new_c)
        await db.flush()
        return new_c

    # Inscribir parejas directas si fueron enviadas
    if payload.teams:
        for idx, tm_data in enumerate(payload.teams):
            p1_raw = tm_data.get("p1") or tm_data.get("customer_id_1") or tm_data.get("player1_id") or f"Jugador A{idx+1}"
            p2_raw = tm_data.get("p2") or tm_data.get("customer_id_2") or tm_data.get("player2_id") or f"Jugador B{idx+1}"
            c1 = await get_or_create_customer(p1_raw, f"Jugador {idx+1}.1", (idx * 2) + 1)
            c2 = await get_or_create_customer(p2_raw, f"Jugador {idx+1}.2", (idx * 2) + 2)
            tm_name = tm_data.get("name") or f"{c1.name.split()[0]} / {c2.name.split()[0]}"

            t_team = TournamentTeam(
                tournament_id=tourn.id,
                team_name=tm_name,
                customer_id_1=c1.id,
                customer_id_2=c2.id,
                group_id=group.id,
                seed=idx + 1,
            )
            db.add(t_team)
            await db.flush()
            resolved_teams.append(t_team)
    elif payload.player_ids and len(payload.player_ids) >= 4:
        # Emparejar jugadores consecutivos de 2 en 2
        p_ids = list(payload.player_ids)
        if len(p_ids) % 2 != 0:
            p_ids.pop() # requerimos pares
        for i in range(0, len(p_ids), 2):
            c1 = await get_or_create_customer(p_ids[i], f"Jugador {i+1}", i + 1)
            c2 = await get_or_create_customer(p_ids[i+1], f"Jugador {i+2}", i + 2)
            tm_name = f"{c1.name.split()[0]} / {c2.name.split()[0]}"
            t_team = TournamentTeam(
                tournament_id=tourn.id,
                team_name=tm_name,
                customer_id_1=c1.id,
                customer_id_2=c2.id,
                group_id=group.id,
                seed=(i // 2) + 1,
            )
            db.add(t_team)
            await db.flush()
            resolved_teams.append(t_team)
    else:
        # Parejas de demostración por defecto para iniciar torneo en vivo
        demo_names = [("Pareja Alpha", "Carlos Gómez", "Felipe Silva"),
                      ("Pareja Beta", "Andrés Marín", "Sebastián Mora"),
                      ("Pareja Gamma", "Daniel Rincón", "Mateo Valencia"),
                      ("Pareja Delta", "Juan Pablo Ruiz", "Diego Castro")]
        for idx, (tname, p1_name, p2_name) in enumerate(demo_names):
            c1 = await get_or_create_customer(p1_name, p1_name, (idx * 2) + 1)
            c2 = await get_or_create_customer(p2_name, p2_name, (idx * 2) + 2)
            t_team = TournamentTeam(
                tournament_id=tourn.id,
                team_name=tname,
                customer_id_1=c1.id,
                customer_id_2=c2.id,
                group_id=group.id,
                seed=idx + 1,
            )
            db.add(t_team)
            await db.flush()
            resolved_teams.append(t_team)

    # 4. Inicializar Standings del Grupo
    group.standings_json = [
        {
            "team_id": tm.id,
            "team_name": tm.team_name,
            "pj": 0,
            "pg": 0,
            "pp": 0,
            "pts_favor": 0,
            "pts_contra": 0,
            "diff": 0,
            "ranking_pts": 0,
        }
        for tm in resolved_teams
    ]

    # 5. Generar Cruces Round-Robin distribuidos en las pistas seleccionadas
    import itertools
    import uuid as _uuid_mod
    court_uuids = []
    for cid in payload.assigned_court_ids:
        try:
            court_uuids.append(_uuid_mod.UUID(str(cid)))
        except Exception:
            pass

    matches_created = []
    round_idx = 1
    court_ptr = 0

    for t1, t2 in itertools.combinations(resolved_teams, 2):
        assigned_court = court_uuids[court_ptr % len(court_uuids)] if court_uuids else None
        court_ptr += 1

        match = TournamentMatch(
            tournament_id=tourn.id,
            group_id=group.id,
            stage="ROUND_ROBIN",
            round_number=round_idx,
            team1_id=t1.id,
            team2_id=t2.id,
            team1_label=t1.team_name,
            team2_label=t2.team_name,
            court_id=assigned_court,
            scheduled_time=f"Ronda {round_idx}",
            scores_json=[{"set": 1, "t1": 0, "t2": 0}],
            status="SCHEDULED" if round_idx > len(payload.assigned_court_ids) else "IN_PROGRESS",
        )
        db.add(match)
        matches_created.append(match)
        round_idx += 1

    await db.commit()
    await db.refresh(tourn)

    # Log de Auditoría
    try:
        await log_activity(
            db=db,
            action="CREATE_AMERICANO_LIVE",
            entity_name="TOURNAMENT",
            entity_id=str(tourn.id),
            details=f"Torneo en vivo '{tourn.name}' creado con {len(resolved_teams)} parejas y {len(matches_created)} partidos.",
            username_snapshot="Organizador Torneo",
        )
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Torneo Americano '{tourn.name}' iniciado exitosamente.",
        "tournament_id": tourn.id,
        "total_teams": len(resolved_teams),
        "total_matches": len(matches_created),
        "assigned_courts_count": len(payload.assigned_court_ids),
    }


def _recalculate_americano_standings(group: TournamentGroup, matches: List[TournamentMatch]):
    """
    Recalcula la tabla de posiciones en tiempo real basándose en los partidos jugados.
    Criterios de orden:
    1. Partidos Ganados (PG)
    2. Diferencia de puntos (diff: favor - contra)
    3. Puntos a favor totales (pts_favor)
    """
    stats: Dict[int, Dict[str, Any]] = {}

    # Inicializar con todos los equipos que figuran en el standing actual
    for item in (group.standings_json or []):
        stats[item["team_id"]] = {
            "team_id": item["team_id"],
            "team_name": item.get("team_name", "Pareja"),
            "pj": 0,
            "pg": 0,
            "pp": 0,
            "pts_favor": 0,
            "pts_contra": 0,
            "diff": 0,
            "ranking_pts": 0,
        }

    for m in matches:
        if not m.team1_id or not m.team2_id:
            continue
        for tid, tname in [(m.team1_id, m.team1.team_name if m.team1 else m.team1_label),
                           (m.team2_id, m.team2.team_name if m.team2 else m.team2_label)]:
            if tid not in stats:
                stats[tid] = {
                    "team_id": tid,
                    "team_name": tname or f"Equipo {tid}",
                    "pj": 0,
                    "pg": 0,
                    "pp": 0,
                    "pts_favor": 0,
                    "pts_contra": 0,
                    "diff": 0,
                    "ranking_pts": 0,
                }

        # Sumar puntos si hay marcador
        t1_pts = 0
        t2_pts = 0
        for s in (m.scores_json or []):
            t1_pts += int(s.get("t1", 0))
            t2_pts += int(s.get("t2", 0))

        if m.status == "COMPLETED" or t1_pts > 0 or t2_pts > 0:
            stats[m.team1_id]["pj"] += 1
            stats[m.team2_id]["pj"] += 1
            stats[m.team1_id]["pts_favor"] += t1_pts
            stats[m.team1_id]["pts_contra"] += t2_pts
            stats[m.team2_id]["pts_favor"] += t2_pts
            stats[m.team2_id]["pts_contra"] += t1_pts

            if m.winner_team_id == m.team1_id or (m.status == "COMPLETED" and t1_pts > t2_pts):
                stats[m.team1_id]["pg"] += 1
                stats[m.team1_id]["ranking_pts"] += 3
                stats[m.team2_id]["pp"] += 1
            elif m.winner_team_id == m.team2_id or (m.status == "COMPLETED" and t2_pts > t1_pts):
                stats[m.team2_id]["pg"] += 1
                stats[m.team2_id]["ranking_pts"] += 3
                stats[m.team1_id]["pp"] += 1

    for tid, data in stats.items():
        data["diff"] = data["pts_favor"] - data["pts_contra"]

    # Ordenar por: 1) PG, 2) Diff, 3) Pts Favor
    leaderboard = list(stats.values())
    leaderboard.sort(key=lambda x: (x["pg"], x["diff"], x["pts_favor"]), reverse=True)
    group.standings_json = leaderboard
    return leaderboard


@router.get(
    "/{id}/live",
    status_code=status.HTTP_200_OK,
    summary="Mesa de Control en Vivo del Torneo Americano (Courts, Matches, Leaderboard)",
)
async def get_live_tournament_state(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna el estado en tiempo real del torneo:
    - Información del torneo y estado (RUNNING, FINISHED)
    - Grilla de Pistas Físicas con el partido activo, tanteador en vivo y status
    - Fixture completo organizado por rondas
    - Leaderboard calculado en tiempo real con posiciones, PJ, PG, PP, Puntos y Diferencia
    """
    tourn_stmt = (
        select(OfficialTournament)
        .options(
            selectinload(OfficialTournament.teams),
            selectinload(OfficialTournament.groups).selectinload(TournamentGroup.matches),
            selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team1),
            selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team2),
        )
        .where(OfficialTournament.id == id)
    )
    tourn_res = await db.execute(tourn_stmt)
    tourn = tourn_res.scalar_one_or_none()
    if not tourn:
        raise HTTPException(status_code=404, detail=f"Torneo con ID {id} no encontrado")

    # Obtener canchas del club para mapear nombres
    courts_res = await db.execute(select(Court))
    courts_by_id = {str(c.id): c for c in courts_res.scalars().all()}

    # Leaderboard en tiempo real
    primary_group = tourn.groups[0] if tourn.groups else None
    if primary_group:
        leaderboard = _recalculate_americano_standings(primary_group, tourn.matches)
    else:
        leaderboard = []

    # Mapear estado de canchas asignadas
    courts_status = []
    for cid in (tourn.assigned_court_ids or []):
        court_obj = courts_by_id.get(str(cid))
        court_name = court_obj.name if court_obj else f"Pista {str(cid)[:6]}"
        sport = court_obj.sport_type if court_obj else tourn.sport_type

        # Buscar partido actualmente en juego en esta pista
        active_match = next((m for m in tourn.matches if str(m.court_id) == str(cid) and m.status == "IN_PROGRESS"), None)
        if not active_match:
            # Si no hay IN_PROGRESS, buscar el siguiente SCHEDULED
            active_match = next((m for m in tourn.matches if str(m.court_id) == str(cid) and m.status == "SCHEDULED"), None)
        if not active_match:
            # Buscar el último jugado
            active_match = next((m for m in tourn.matches if str(m.court_id) == str(cid)), None)

        match_data = None
        if active_match:
            s = (active_match.scores_json[0] if active_match.scores_json else {"t1": 0, "t2": 0})
            match_data = {
                "match_id": active_match.id,
                "stage": active_match.stage,
                "round_number": active_match.round_number,
                "status": active_match.status,
                "team1_id": active_match.team1_id,
                "team1_name": active_match.team1.team_name if active_match.team1 else (active_match.team1_label or "Dupla 1"),
                "team2_id": active_match.team2_id,
                "team2_name": active_match.team2.team_name if active_match.team2 else (active_match.team2_label or "Dupla 2"),
                "team1_points": s.get("t1", 0),
                "team2_points": s.get("t2", 0),
                "winner_team_id": active_match.winner_team_id,
            }

        courts_status.append({
            "court_id": str(cid),
            "court_name": court_name,
            "sport_type": sport,
            "has_active_match": bool(active_match and active_match.status == "IN_PROGRESS"),
            "current_match": match_data,
        })

    # Formatear todos los partidos
    matches_list = []
    for m in tourn.matches:
        s = (m.scores_json[0] if m.scores_json else {"t1": 0, "t2": 0})
        c_obj = courts_by_id.get(str(m.court_id)) if m.court_id else None
        matches_list.append({
            "id": m.id,
            "stage": m.stage,
            "round_number": m.round_number,
            "court_id": str(m.court_id) if m.court_id else None,
            "court_name": c_obj.name if c_obj else "Pista por asignar",
            "team1": {
                "id": m.team1_id,
                "name": m.team1.team_name if m.team1 else (m.team1_label or "Dupla 1"),
            },
            "team2": {
                "id": m.team2_id,
                "name": m.team2.team_name if m.team2 else (m.team2_label or "Dupla 2"),
            },
            "team1_points": s.get("t1", 0),
            "team2_points": s.get("t2", 0),
            "status": m.status,
            "winner_team_id": m.winner_team_id,
        })

    return {
        "status": "success",
        "tournament": {
            "id": tourn.id,
            "name": tourn.name,
            "sport_type": tourn.sport_type,
            "category": tourn.category,
            "status": tourn.status.value,
            "match_duration_minutes": tourn.match_duration_minutes,
            "start_date": str(tourn.start_date) if tourn.start_date else None,
            "start_time": tourn.start_time.strftime("%H:%M") if tourn.start_time else None,
            "champion_team": tourn.champion_team,
            "runner_up_team": tourn.runner_up_team,
        },
        "courts_status": courts_status,
        "leaderboard": leaderboard,
        "matches": matches_list,
    }


@router.post(
    "/{id}/matches/{match_id}/score",
    status_code=status.HTTP_200_OK,
    summary="Actualizar tanteador en tiempo real de un partido con recalculo instantáneo",
)
async def update_live_match_score(
    id: int,
    match_id: int,
    payload: LiveScoreUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Soporta micro-ajustes rápidos en vivo (+1 / -1) o puntuación directa por equipo.
    Recalcula al instante el leaderboard del torneo americano y verifica si el partido
    ha concluido según el límite de puntos meta.
    """
    m_stmt = (
        select(TournamentMatch)
        .options(
            selectinload(TournamentMatch.group),
            selectinload(TournamentMatch.team1),
            selectinload(TournamentMatch.team2),
            selectinload(TournamentMatch.tournament),
        )
        .where(TournamentMatch.id == match_id, TournamentMatch.tournament_id == id)
    )
    res = await db.execute(m_stmt)
    match = res.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Partido no encontrado en este torneo.")

    # Marcador actual
    current_s = match.scores_json[0] if match.scores_json else {"set": 1, "t1": 0, "t2": 0}
    t1 = int(current_s.get("t1", 0))
    t2 = int(current_s.get("t2", 0))

    # Aplicar deltas (+1 / -1) si se proporcionan
    if payload.delta_t1 is not None:
        t1 = max(0, t1 + payload.delta_t1)
    if payload.delta_t2 is not None:
        t2 = max(0, t2 + payload.delta_t2)

    # O sobreescribir puntos explícitos
    if payload.team1_points is not None:
        t1 = max(0, payload.team1_points)
    if payload.team2_points is not None:
        t2 = max(0, payload.team2_points)

    match.scores_json = [{"set": 1, "t1": t1, "t2": t2}]

    # Determinar si el partido finalizó (por límite o forzado)
    target_limit = 32
    if match.tournament and "24" in match.tournament.name:
        target_limit = 24
    elif match.tournament and "40" in match.tournament.name:
        target_limit = 40

    if (t1 + t2 >= target_limit and t1 != t2) or (payload.status == "COMPLETED"):
        match.status = "COMPLETED"
        if t1 > t2:
            match.winner_team_id = match.team1_id
        elif t2 > t1:
            match.winner_team_id = match.team2_id
    elif payload.status:
        match.status = payload.status
    else:
        match.status = "IN_PROGRESS"

    if payload.winner_team_id:
        match.winner_team_id = payload.winner_team_id

    # Recalcular standing del grupo
    if match.group:
        all_matches_res = await db.execute(
            select(TournamentMatch)
            .options(selectinload(TournamentMatch.team1), selectinload(TournamentMatch.team2))
            .where(TournamentMatch.group_id == match.group_id)
        )
        all_group_matches = list(all_matches_res.scalars().all())
        updated_leaderboard = _recalculate_americano_standings(match.group, all_group_matches)
    else:
        updated_leaderboard = []

    await db.commit()
    await db.refresh(match)

    return {
        "status": "success",
        "match_id": match.id,
        "team1_points": t1,
        "team2_points": t2,
        "match_status": match.status,
        "winner_team_id": match.winner_team_id,
        "leaderboard": updated_leaderboard,
    }


@router.post(
    "/{id}/close",
    status_code=status.HTTP_200_OK,
    summary="Cerrar Torneo Americano, consolidar podio y actualizar estadísticas en CRM Customers",
)
async def close_americano_tournament(
    id: int,
    payload: CloseTournamentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Finaliza el torneo americano, asigna el podio oficial (Campeón y Subcampeón),
    y consolida los puntos en la tabla `customers` para el ranking del club con
    detección de sugerencia de ascenso.
    """
    tourn_stmt = (
        select(OfficialTournament)
        .options(
            selectinload(OfficialTournament.teams),
            selectinload(OfficialTournament.groups),
            selectinload(OfficialTournament.matches),
        )
        .where(OfficialTournament.id == id)
    )
    res = await db.execute(tourn_stmt)
    tourn = res.scalar_one_or_none()
    if not tourn:
        raise HTTPException(status_code=404, detail="Torneo no encontrado.")

    # 1. Identificar Campeón y Subcampeón (por payload o por tabla de posiciones)
    leaderboard = []
    if tourn.groups:
        leaderboard = _recalculate_americano_standings(tourn.groups[0], tourn.matches)

    champ_id = payload.champion_team_id or (leaderboard[0]["team_id"] if len(leaderboard) > 0 else None)
    runner_id = payload.runner_up_team_id or (leaderboard[1]["team_id"] if len(leaderboard) > 1 else None)

    champ_team = next((tm for tm in tourn.teams if tm.id == champ_id), None)
    runner_team = next((tm for tm in tourn.teams if tm.id == runner_id), None)

    champ_name = champ_team.team_name if champ_team else "Campeones Americano"
    runner_name = runner_team.team_name if runner_team else "Subcampeones Americano"

    tourn.status = OfficialTournamentStatus.FINISHED
    tourn.champion_team = champ_name
    tourn.runner_up_team = runner_name

    # 2. Actualizar estadísticas en CRM Customers
    promoted_players = []
    if champ_team:
        for cust_id in [champ_team.customer_id_1, champ_team.customer_id_2]:
            c_res = await db.execute(select(Customer).where(Customer.id == cust_id))
            cust = c_res.scalar_one_or_none()
            if cust:
                cust.ranking_points += payload.champions_points
                cust.titles_count += 1
                cust.category_wins += 1
                cust.consecutive_wins += 1
                if cust.consecutive_wins >= 2 or cust.category_wins >= 2:
                    cust.promotion_recommended = True
                    cust.recommended_category = get_next_category(cust.category)
                    promoted_players.append(f"{cust.name} (Sugerido a {cust.recommended_category})")

    if runner_team:
        for cust_id in [runner_team.customer_id_1, runner_team.customer_id_2]:
            c_res = await db.execute(select(Customer).where(Customer.id == cust_id))
            cust = c_res.scalar_one_or_none()
            if cust:
                cust.ranking_points += payload.runner_up_points

    await db.commit()
    await db.refresh(tourn)

    # Log de Auditoría
    try:
        await log_activity(
            db=db,
            action="CLOSE_AMERICANO_TOURNAMENT",
            entity_name="TOURNAMENT",
            entity_id=str(tourn.id),
            details=f"Torneo finalizado. Campeones: {champ_name} (+{payload.champions_points} pts). Subcampeones: {runner_name} (+{payload.runner_up_points} pts).",
            username_snapshot="Organizador Torneo",
        )
    except Exception:
        pass


    # Liberar time_slots asociados si fueron asignados por el torneo
    if tourn.start_date:
        t_slots_res = await db.execute(
            select(TimeSlot).where(
                TimeSlot.tournament_name.ilike(f"%{tourn.name}%"),
                TimeSlot.date == tourn.start_date,
            )
        )
        for s in t_slots_res.scalars().all():
            s.is_finished = True
            s.status = SlotStatus.AVAILABLE
            s.winners_names = champ_name
            s.runner_up_names = runner_name
        await db.commit()

    return {
        "status": "success",
        "message": f"Torneo Americano '{tourn.name}' finalizado con éxito.",
        "champion": champ_name,
        "runner_up": runner_name,
        "promoted_players": promoted_players,
        "leaderboard": leaderboard,
    }


class StartAmericanoRequest(BaseModel):
    scoring_system: Optional[str] = Field("POINTS_32", description="POINTS_32, POINTS_24, POINTS_40, SETS")
    target_points: Optional[int] = Field(32, description="Puntos objetivo")
    modality: Optional[str] = Field("PAREJA_FIJA", description="PAREJA_FIJA o ROTATIVA_KING_OF_COURT")


@router.post(
    "/{id}/start",
    status_code=status.HTTP_200_OK,
    summary="Iniciar Torneo Americano en Vivo (Activa Ronda 1 y pone estado en IN_PROGRESS)",
)
async def start_americano_tournament(
    id: int,
    payload: Optional[StartAmericanoRequest] = Body(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Inicia formalmente un Torneo Americano:
    - Cambia su estado a IN_PROGRESS
    - Activa la Ronda 1 en las pistas físicas designadas
    - Configura el tanteador inicial 0-0 y bloquea turnos correspondientes
    """
    tourn_stmt = (
        select(OfficialTournament)
        .options(
            selectinload(OfficialTournament.teams),
            selectinload(OfficialTournament.groups).selectinload(TournamentGroup.matches),
            selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team1),
            selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team2),
        )
        .where(OfficialTournament.id == id)
    )
    res = await db.execute(tourn_stmt)
    tourn = res.scalar_one_or_none()
    if not tourn:
        raise HTTPException(status_code=404, detail=f"Torneo con ID {id} no encontrado.")

    tourn.status = OfficialTournamentStatus.IN_PROGRESS

    # Activar partidos de la ronda 1
    r1_matches = [m for m in tourn.matches if m.round_number == 1]
    for m in r1_matches:
        m.status = "IN_PROGRESS"
        if not m.scores_json:
            m.scores_json = [{"set": 1, "t1": 0, "t2": 0}]

    await db.commit()
    await db.refresh(tourn)

    # Log de Auditoría
    try:
        await log_activity(
            db=db,
            action="START_AMERICANO_TOURNAMENT",
            entity_name="TOURNAMENT",
            entity_id=str(tourn.id),
            details=f"Torneo '{tourn.name}' iniciado en vivo. Ronda 1 en marcha con {len(r1_matches)} pistas activas.",
            username_snapshot="Organizador Torneo",
        )
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Torneo Americano '{tourn.name}' ha comenzado. Ronda 1 en juego.",
        "tournament_id": tourn.id,
        "round_active": 1,
        "active_matches": len(r1_matches),
    }


class NextRoundRequest(BaseModel):
    modality: Optional[str] = Field(None, description="PAREJA_FIJA o ROTATIVA_KING_OF_COURT")
    auto_promote_relegate: bool = Field(True, description="En Sube y Baja, mover ganadores arriba y perdedores abajo")


@router.post(
    "/{id}/next-round",
    status_code=status.HTTP_200_OK,
    summary="Avanzar a la Siguiente Ronda (Sube y Baja / Rotativo o siguiente tanda de cruces)",
)
async def advance_next_round(
    id: int,
    payload: Optional[NextRoundRequest] = Body(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Avanza a la siguiente ronda del Torneo Americano:
    1. Cierra y marca como COMPLETED los partidos de la ronda actual que tengan tanteador.
    2. Si es modalidad Sube y Baja (King of the Court):
       - Pareja ganadora asciende a la cancha de mayor jerarquía (Cancha N-1).
       - Pareja perdedora desciende a la cancha de menor jerarquía (Cancha N+1).
    3. Si existen partidos de la siguiente ronda programados (SCHEDULED), los activa a IN_PROGRESS.
    4. Recalcula el Leaderboard actualizado al instante.
    """
    tourn_stmt = (
        select(OfficialTournament)
        .options(
            selectinload(OfficialTournament.teams),
            selectinload(OfficialTournament.groups).selectinload(TournamentGroup.matches),
            selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team1),
            selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team2),
        )
        .where(OfficialTournament.id == id)
    )
    res = await db.execute(tourn_stmt)
    tourn = res.scalar_one_or_none()
    if not tourn:
        raise HTTPException(status_code=404, detail="Torneo no encontrado.")

    # Determinar ronda actual máxima en progreso o completada
    active_matches = [m for m in tourn.matches if m.status == "IN_PROGRESS"]
    current_round = max([m.round_number for m in active_matches], default=1) if active_matches else 1

    # 1. Completar partidos de la ronda actual
    for m in active_matches:
        s = m.scores_json[0] if m.scores_json else {"t1": 0, "t2": 0}
        t1_pts = int(s.get("t1", 0))
        t2_pts = int(s.get("t2", 0))
        m.status = "COMPLETED"
        if not m.winner_team_id:
            if t1_pts > t2_pts:
                m.winner_team_id = m.team1_id
            elif t2_pts > t1_pts:
                m.winner_team_id = m.team2_id

    # 2. Buscar si hay partidos programados para la siguiente ronda
    next_round = current_round + 1
    next_scheduled = [m for m in tourn.matches if m.round_number == next_round and m.status == "SCHEDULED"]

    if next_scheduled:
        for m in next_scheduled:
            m.status = "IN_PROGRESS"
            if not m.scores_json:
                m.scores_json = [{"set": 1, "t1": 0, "t2": 0}]
    else:
        # Si no había cruces precalculados para esta ronda (ej. Sube y Baja dinámico), generar nueva ronda
        court_ids = tourn.assigned_court_ids or []
        import uuid as _uuid_mod
        court_uuids = []
        for cid in court_ids:
            try:
                court_uuids.append(_uuid_mod.UUID(str(cid)))
            except Exception:
                pass

        # Si tenemos parejas, emparejarlas según ranking actual (Sube y Baja)
        primary_group = tourn.groups[0] if tourn.groups else None
        if primary_group:
            current_standings = _recalculate_americano_standings(primary_group, tourn.matches)
            ranked_team_ids = [row["team_id"] for row in current_standings]
            # Emparejar adyacentes: 1 vs 2 (Pista 1), 3 vs 4 (Pista 2), etc.
            c_ptr = 0
            for i in range(0, len(ranked_team_ids) - 1, 2):
                t1_id = ranked_team_ids[i]
                t2_id = ranked_team_ids[i + 1]
                t1_obj = next((t for t in tourn.teams if t.id == t1_id), None)
                t2_obj = next((t for t in tourn.teams if t.id == t2_id), None)
                assigned_c = court_uuids[c_ptr % len(court_uuids)] if court_uuids else None
                c_ptr += 1

                new_m = TournamentMatch(
                    tournament_id=tourn.id,
                    group_id=primary_group.id,
                    stage="SUBE_Y_BAJA",
                    round_number=next_round,
                    team1_id=t1_id,
                    team2_id=t2_id,
                    team1_label=t1_obj.team_name if t1_obj else f"Equipo {t1_id}",
                    team2_label=t2_obj.team_name if t2_obj else f"Equipo {t2_id}",
                    court_id=assigned_c,
                    scheduled_time=f"Ronda {next_round}",
                    scores_json=[{"set": 1, "t1": 0, "t2": 0}],
                    status="IN_PROGRESS",
                )
                db.add(new_m)
                next_scheduled.append(new_m)

    # 3. Recalcular Leaderboard
    leaderboard = []
    if tourn.groups:
        leaderboard = _recalculate_americano_standings(tourn.groups[0], tourn.matches)

    await db.commit()
    await db.refresh(tourn)

    # Log de Auditoría
    try:
        await log_activity(
            db=db,
            action="ADVANCE_AMERICANO_ROUND",
            entity_name="TOURNAMENT",
            entity_id=str(tourn.id),
            details=f"Avance a Ronda {next_round} con {len(next_scheduled)} partidos activos.",
            username_snapshot="Organizador Torneo",
        )
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"¡Ronda {next_round} iniciada con éxito!",
        "current_round": next_round,
        "active_matches_count": len(next_scheduled),
        "leaderboard": leaderboard,
    }






