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


AMERICANO_CONFIG_FLAG = "_config"
DEFAULT_CLUB_UUID = uuid.UUID("2756f34a-7d24-4815-9f7e-6ed125ea5de7")


def _parse_club_uuid(raw: Optional[str]) -> Optional[uuid.UUID]:
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def resolve_club_id(request: Request, payload_club_id: Optional[str] = None) -> uuid.UUID:
    """Resuelve el club activo: body → header X-Club-Id → query → cookie user_club → sede default."""
    header = request.headers.get("X-Club-Id") or request.headers.get("x-club-id")
    query = request.query_params.get("club_id")
    cookie = request.cookies.get("user_club")
    return (
        _parse_club_uuid(payload_club_id)
        or _parse_club_uuid(header)
        or _parse_club_uuid(query)
        or _parse_club_uuid(cookie)
        or DEFAULT_CLUB_UUID
    )


def _club_scope(club_id: uuid.UUID):
    """Aislamiento multi-tenant. Filas legacy sin club_id solo son visibles en la sede default."""
    if club_id == DEFAULT_CLUB_UUID:
        return or_(OfficialTournament.club_id == club_id, OfficialTournament.club_id.is_(None))
    return OfficialTournament.club_id == club_id


def _public_status(status) -> str:
    raw = status.value if hasattr(status, "value") else str(status or "DRAFT")
    if raw in {"IN_PROGRESS", "RUNNING", "LIVE"}:
        return "RUNNING"
    return raw


def _running_status() -> OfficialTournamentStatus:
    return OfficialTournamentStatus.RUNNING


def _is_finished(status) -> bool:
    raw = status.value if hasattr(status, "value") else str(status or "")
    return raw == "FINISHED"


def _americano_eager_options():
    return (
        selectinload(OfficialTournament.teams),
        selectinload(OfficialTournament.groups).selectinload(TournamentGroup.matches),
        selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team1),
        selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team2),
    )


async def _get_tournament_for_club(
    db: AsyncSession,
    tourn_id: int,
    club_id: uuid.UUID,
    *,
    bind_legacy: bool = False,
) -> OfficialTournament:
    stmt = (
        select(OfficialTournament)
        .options(*_americano_eager_options())
        .where(OfficialTournament.id == tourn_id, _club_scope(club_id))
    )
    res = await db.execute(stmt)
    tourn = res.scalar_one_or_none()
    if not tourn:
        raise HTTPException(status_code=404, detail="Torneo no encontrado.")
    if bind_legacy and tourn.club_id is None:
        tourn.club_id = club_id
    return tourn


async def _assert_courts_belong_to_club(
    db: AsyncSession,
    court_uuids: List[uuid.UUID],
    club_id: uuid.UUID,
) -> None:
    if not court_uuids:
        raise HTTPException(status_code=400, detail="Debe asignar al menos una pista deportiva para el torneo.")
    courts_res = await db.execute(select(Court).where(Court.id.in_(court_uuids)))
    found = {c.id: c for c in courts_res.scalars().all()}
    for cid in court_uuids:
        court = found.get(cid)
        if not court:
            raise HTTPException(status_code=400, detail=f"Cancha {cid} no existe.")
        if court.club_id and court.club_id != club_id:
            raise HTTPException(
                status_code=403,
                detail="La cancha no pertenece al club activo. Aislamiento multi-tenant.",
            )


def _parse_court_uuids(court_ids: Optional[List[str]]) -> List[uuid.UUID]:
    parsed: List[uuid.UUID] = []
    for cid in court_ids or []:
        try:
            parsed.append(uuid.UUID(str(cid)))
        except Exception:
            continue
    return parsed


def _is_time_unlimited(scoring: Optional[str]) -> bool:
    s = str(scoring or "").upper()
    return s in {"TIME_UNLIMITED", "TIME", "TIME_INFINITE", "INFINITOS"} or s.startswith("TIME_")


def _is_sube_y_baja(modality: Optional[str]) -> bool:
    m = str(modality or "").upper()
    return m in {"SUBE_Y_BAJA", "INDIVIDUAL", "ROTATIVA", "ROTATIVA_KING_OF_COURT", "KING_OF_THE_COURT"}


def _target_points_for(scoring: Optional[str], explicit: Optional[int] = None) -> int:
    if _is_time_unlimited(scoring):
        return 0
    if explicit is not None and int(explicit) > 0:
        return int(explicit)
    s = str(scoring or "").upper()
    if "24" in s:
        return 24
    if "40" in s:
        return 40
    if s == "SETS":
        return 2
    return 32


def _split_standings_config(standings: Optional[List[dict]]) -> tuple:
    cfg: Dict[str, Any] = {}
    rows: List[dict] = []
    for item in standings or []:
        if isinstance(item, dict) and item.get(AMERICANO_CONFIG_FLAG):
            cfg = item
        elif isinstance(item, dict):
            rows.append(item)
    return cfg, rows


def _merge_standings_config(cfg: Optional[dict], rows: Optional[List[dict]]) -> List[dict]:
    merged = [r for r in (rows or []) if isinstance(r, dict) and not r.get(AMERICANO_CONFIG_FLAG)]
    if cfg:
        payload = dict(cfg)
        payload[AMERICANO_CONFIG_FLAG] = True
        return [payload] + merged
    return merged


def _build_americano_config(
    scoring_system: str = "POINTS_32",
    target_points: Optional[int] = None,
    modality: str = "PAREJA_FIJA",
    tiebreak_rule: str = "MATCHES_WON",
    round_minutes: int = 15,
    pair_count: int = 4,
) -> Dict[str, Any]:
    scoring = str(scoring_system or "POINTS_32").upper()
    minutes = max(1, int(round_minutes or 15))
    return {
        AMERICANO_CONFIG_FLAG: True,
        "scoring_system": scoring,
        "target_points": _target_points_for(scoring, target_points),
        "modality": str(modality or "PAREJA_FIJA").upper(),
        "tiebreak_rule": str(tiebreak_rule or "MATCHES_WON").upper(),
        "round_minutes": minutes,
        "pair_count": max(2, min(int(pair_count or 4), 20)),
    }


def _head_to_head_margin(matches: List[TournamentMatch], team_a: int, team_b: int) -> int:
    won_a = won_b = 0
    for m in matches:
        if m.status != "COMPLETED" or not m.team1_id or not m.team2_id:
            continue
        ids = {m.team1_id, m.team2_id}
        if team_a not in ids or team_b not in ids:
            continue
        if m.winner_team_id == team_a:
            won_a += 1
        elif m.winner_team_id == team_b:
            won_b += 1
    return won_a - won_b


def _sort_americano_leaderboard(rows: List[dict], matches: List[TournamentMatch], rule: str) -> List[dict]:
    """Desempate canónico: 1) partidos ganados  2) puntos a favor  3) enfrentamiento directo."""
    r = str(rule or "MATCHES_WON").upper()

    def key_fn(row: dict):
        pg = int(row.get("pg") or 0)
        diff = int(row.get("diff") or 0)
        pf = int(row.get("pts_favor") or 0)
        if r in {"POINTS_FOR", "PTS_FAVOR", "PUNTOS_A_FAVOR"}:
            return (pf, pg, diff)
        if r in {"GAMES_DIFF", "DIFF", "POINTS_DIFF", "DIFERENCIA"}:
            return (diff, pg, pf)
        if r in {"SETS_DIFF"}:
            return (pg, diff, pf)
        # MATCHES_WON (default) y HEAD_TO_HEAD: PG → puntos a favor → diff
        return (pg, pf, diff)

    ordered = sorted(rows, key=key_fn, reverse=True)

    apply_h2h = r in {"MATCHES_WON", "HEAD_TO_HEAD", "H2H", "ENFRENTAMIENTO_DIRECTO", ""}
    if apply_h2h:
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                if int(ordered[i].get("pg") or 0) != int(ordered[j].get("pg") or 0):
                    break
                if r != "HEAD_TO_HEAD" and int(ordered[i].get("pts_favor") or 0) != int(ordered[j].get("pts_favor") or 0):
                    break
                if _head_to_head_margin(matches, ordered[i]["team_id"], ordered[j]["team_id"]) < 0:
                    ordered[i], ordered[j] = ordered[j], ordered[i]
    return ordered


def _circle_round_robin(teams: List[TournamentTeam]) -> List[List[tuple]]:
    ts: List[Optional[TournamentTeam]] = list(teams)
    if len(ts) < 2:
        return []
    if len(ts) % 2 == 1:
        ts.append(None)
    n = len(ts)
    arr = ts[:]
    rounds: List[List[tuple]] = []
    for _ in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            if a is not None and b is not None:
                pairs.append((a, b))
        rounds.append(pairs)
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return rounds


def _build_fixture_rounds(
    teams: List[TournamentTeam],
    court_uuids: List[uuid.UUID],
    modality: str,
) -> List[List[tuple]]:
    """Cada ronda: lista de (team1, team2, court_uuid|None) limitada a canchas simultáneas."""
    if len(teams) < 2:
        return []
    n_courts = max(1, len(court_uuids) or 1)
    if _is_sube_y_baja(modality):
        pairings = []
        max_pairs = min(len(teams) // 2, n_courts)
        for i in range(max_pairs):
            court = court_uuids[i] if i < len(court_uuids) else None
            pairings.append((teams[i * 2], teams[i * 2 + 1], court))
        return [pairings] if pairings else []

    out: List[List[tuple]] = []
    for pairs in _circle_round_robin(teams):
        for start in range(0, len(pairs), n_courts):
            chunk = pairs[start:start + n_courts]
            assigned = []
            for i, (t1, t2) in enumerate(chunk):
                court = court_uuids[i] if i < len(court_uuids) else (court_uuids[i % len(court_uuids)] if court_uuids else None)
                assigned.append((t1, t2, court))
            if assigned:
                out.append(assigned)
    return out


def _make_match(tourn_id: int, group_id: int, round_number: int, t1: TournamentTeam, t2: TournamentTeam, court, stage: str, status: str) -> TournamentMatch:
    return TournamentMatch(
        tournament_id=tourn_id,
        group_id=group_id,
        stage=stage,
        round_number=round_number,
        team1_id=t1.id,
        team2_id=t2.id,
        team1_label=t1.team_name,
        team2_label=t2.team_name,
        court_id=court,
        scheduled_time=f"Ronda {round_number}",
        scores_json=[{"set": 1, "t1": 0, "t2": 0}],
        status=status,
    )


class CreateAmericanoTournamentRequest(BaseModel):
    name: str = Field(..., description="Nombre del Torneo Americano (ej: Americano Nocturno Express)")
    sport_type: str = Field("PADEL", description="PADEL, PICKLEBALL")
    category: str = Field("4ta", description="Categoría (1ra, 2da, 3ra, 4ta, 5ta, 6ta)")
    modality: str = Field("PAREJA_FIJA", description="PAREJA_FIJA, INDIVIDUAL, SUBE_Y_BAJA, ROTATIVA_KING_OF_COURT")
    scoring_system: str = Field("POINTS_32", description="TIME_UNLIMITED, POINTS_24, POINTS_32, POINTS_40, SETS")
    target_points: int = Field(32, description="Puntos meta por partido; 0 = infinitos (por tiempo)")
    round_minutes: int = Field(15, ge=1, le=180, description="Duración de cada ronda en minutos (cronómetro)")
    pair_count: int = Field(4, ge=2, le=20, description="Cantidad de parejas inscritas / plazas")
    tiebreak_rule: str = Field("MATCHES_WON", description="MATCHES_WON (PG → PF → H2H), POINTS_FOR, GAMES_DIFF, HEAD_TO_HEAD")
    assigned_court_ids: List[str] = Field(..., description="Lista de IDs UUID de pistas físicas asignadas")
    player_ids: Optional[List[Union[int, str]]] = Field(default_factory=list, description="Lista de IDs o teléfonos de jugadores CRM")
    teams: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Parejas fijas [{'name': '...', 'p1': 1, 'p2': 2}]")
    start_date: Optional[str] = Field(None, description="Fecha YYYY-MM-DD")
    start_time: Optional[str] = Field("18:00", description="Hora de inicio HH:MM")
    club_id: Optional[str] = Field(None, description="UUID de la sede (multi-tenant). Si se omite, se toma cookie/header.")
    start_immediately: bool = Field(True, description="True = RUNNING (mesa en vivo). False = DRAFT.")


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
    request: Request,
    db: AsyncSession = Depends(get_db),
    club_id: Optional[str] = Query(None, description="UUID de la sede activa"),
):
    """
    Setup del Americano: canchas, modalidad (Pareja Fija / Sube y Baja) y formato
    de puntuación (puntos acumulados vs sets). Aislado por club_id.
    """
    if len(payload.assigned_court_ids) < 1:
        raise HTTPException(status_code=400, detail="Debe asignar al menos una pista deportiva para el torneo.")

    club_uuid = resolve_club_id(request, payload.club_id or club_id)
    court_uuids_setup = _parse_court_uuids(payload.assigned_court_ids)
    await _assert_courts_belong_to_club(db, court_uuids_setup, club_uuid)
    start_now = bool(payload.start_immediately)

    # 1. Crear el torneo en official_tournaments
    t_date = to_date_obj(payload.start_date) or date.today()
    t_time = to_time_obj(payload.start_time) or time(18, 0)

    # Determinar regla de partido según sistema de puntuación
    scoring = str(payload.scoring_system or "POINTS_32").upper()
    rule_map = {
        "POINTS_32": TournamentMatchRule.TIMED_MATCH,
        "POINTS_24": TournamentMatchRule.TIMED_MATCH,
        "POINTS_40": TournamentMatchRule.TIMED_MATCH,
        "TIME_UNLIMITED": TournamentMatchRule.TIMED_MATCH,
        "TIME": TournamentMatchRule.TIMED_MATCH,
        "SETS": TournamentMatchRule.BEST_OF_3_SHORT,
    }
    match_rule_val = rule_map.get(scoring, TournamentMatchRule.TIMED_MATCH)

    tiebreak_map = {
        "GAMES_DIFF": TournamentTiebreakRule.GAMES_DIFF,
        "HEAD_TO_HEAD": TournamentTiebreakRule.HEAD_TO_HEAD,
        "SETS_DIFF": TournamentTiebreakRule.SETS_DIFF,
        "MATCHES_WON": TournamentTiebreakRule.GAMES_DIFF,
        "POINTS_FOR": TournamentTiebreakRule.GAMES_DIFF,
    }
    tb_rule_val = tiebreak_map.get(str(payload.tiebreak_rule or "").upper(), TournamentTiebreakRule.GAMES_DIFF)
    cfg = _build_americano_config(
        scoring_system=scoring,
        target_points=payload.target_points,
        modality=payload.modality,
        tiebreak_rule=payload.tiebreak_rule,
        round_minutes=payload.round_minutes,
        pair_count=payload.pair_count,
    )
    round_minutes = int(cfg["round_minutes"])

    tourn = OfficialTournament(
        club_id=club_uuid,
        name=payload.name,
        sport_type=payload.sport_type.upper(),
        category=payload.category,
        format_type=TournamentFormatType.GROUPS_PLAYOFFS,
        match_rule=match_rule_val,
        match_duration_minutes=round_minutes,
        tiebreak_rule=tb_rule_val,
        status=_running_status() if start_now else OfficialTournamentStatus.DRAFT,
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
        # Parejas placeholder según pair_count (hasta 20) para arrancar la mesa de control
        pair_n = int(cfg.get("pair_count") or 4)
        for idx in range(pair_n):
            p1_name = f"Jugador {idx + 1}A"
            p2_name = f"Jugador {idx + 1}B"
            c1 = await get_or_create_customer(p1_name, p1_name, (idx * 2) + 1)
            c2 = await get_or_create_customer(p2_name, p2_name, (idx * 2) + 2)
            t_team = TournamentTeam(
                tournament_id=tourn.id,
                team_name=f"Pareja {idx + 1}",
                customer_id_1=c1.id,
                customer_id_2=c2.id,
                group_id=group.id,
                seed=idx + 1,
            )
            db.add(t_team)
            await db.flush()
            resolved_teams.append(t_team)

    # 4. Inicializar Standings del Grupo + config persistida
    standing_rows = [
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
    group.standings_json = _merge_standings_config(cfg, standing_rows)

    # 5. Generar cruces por rondas (round-robin por canchas o Ronda 1 Sube y Baja)
    court_uuids = _parse_court_uuids(payload.assigned_court_ids)
    stage_name = "SUBE_Y_BAJA" if _is_sube_y_baja(payload.modality) else "ROUND_ROBIN"
    fixture_rounds = _build_fixture_rounds(resolved_teams, court_uuids, payload.modality)

    matches_created = []
    for r_idx, pairings in enumerate(fixture_rounds, start=1):
        match_status = "IN_PROGRESS" if (start_now and r_idx == 1) else "SCHEDULED"
        for t1, t2, court in pairings:
            match = _make_match(tourn.id, group.id, r_idx, t1, t2, court, stage_name, match_status)
            db.add(match)
            matches_created.append(match)

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
        "message": f"Torneo Americano '{tourn.name}' {'iniciado' if start_now else 'configurado en DRAFT'} exitosamente.",
        "tournament_id": tourn.id,
        "club_id": str(club_uuid),
        "tournament_status": _public_status(tourn.status),
        "total_teams": len(resolved_teams),
        "total_matches": len(matches_created),
        "assigned_courts_count": len(payload.assigned_court_ids),
        "config": cfg,
        "current_round": 1,
    }


def _recalculate_americano_standings(group: TournamentGroup, matches: List[TournamentMatch]):
    """
    Recalcula la tabla de posiciones en tiempo real.
    Desempate canónico MATCHES_WON: 1. Partidos ganados  2. Puntos a favor  3. Enfrentamiento directo.
    """
    cfg, existing_rows = _split_standings_config(group.standings_json)
    stats: Dict[int, Dict[str, Any]] = {}

    for item in existing_rows:
        tid = item.get("team_id")
        if tid is None:
            continue
        stats[tid] = {
            "team_id": tid,
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
        for tid, tname in [
            (m.team1_id, m.team1.team_name if m.team1 else m.team1_label),
            (m.team2_id, m.team2.team_name if m.team2 else m.team2_label),
        ]:
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

    for data in stats.values():
        data["diff"] = data["pts_favor"] - data["pts_contra"]

    leaderboard = _sort_americano_leaderboard(
        list(stats.values()),
        matches,
        cfg.get("tiebreak_rule") or "MATCHES_WON",
    )
    group.standings_json = _merge_standings_config(cfg, leaderboard)
    return leaderboard


@router.get(
    "/americanos",
    status_code=status.HTTP_200_OK,
    summary="Listar Americanos de la sede (DRAFT / RUNNING / FINISHED) aislados por club_id",
)
async def list_club_americanos(
    request: Request,
    db: AsyncSession = Depends(get_db),
    club_id: Optional[str] = Query(None),
    include_finished: bool = Query(False),
):
    club_uuid = resolve_club_id(request, club_id)
    stmt = (
        select(OfficialTournament)
        .where(_club_scope(club_uuid))
        .order_by(OfficialTournament.created_at.desc())
    )
    if not include_finished:
        stmt = stmt.where(
            OfficialTournament.status.in_(
                [
                    OfficialTournamentStatus.DRAFT,
                    OfficialTournamentStatus.RUNNING,
                    OfficialTournamentStatus.IN_PROGRESS,
                    OfficialTournamentStatus.ENROLLMENT,
                ]
            )
        )
    res = await db.execute(stmt)
    rows = res.scalars().all()
    return [
        {
            "id": t.id,
            "club_id": str(t.club_id) if t.club_id else str(club_uuid),
            "name": t.name,
            "category": t.category,
            "sport_type": t.sport_type,
            "status": _public_status(t.status),
            "assigned_court_ids": t.assigned_court_ids or [],
        }
        for t in rows
    ]


@router.get(
    "/{id}/live",
    status_code=status.HTTP_200_OK,
    summary="Mesa de Control en Vivo del Torneo Americano (Courts, Matches, Leaderboard)",
)
async def get_live_tournament_state(
    id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    club_id: Optional[str] = Query(None),
):
    """
    Retorna el estado en tiempo real del torneo:
    - Información del torneo y estado (DRAFT, RUNNING, FINISHED)
    - Grilla de Pistas Físicas con el partido activo, tanteador en vivo y status
    - Fixture completo organizado por rondas
    - Leaderboard calculado en tiempo real con desempate PG → PF → H2H
    """
    club_uuid = resolve_club_id(request, club_id)
    tourn = await _get_tournament_for_club(db, id, club_uuid)

    # Obtener canchas del club para mapear nombres
    courts_res = await db.execute(
        select(Court).where(or_(Court.club_id == club_uuid, Court.club_id.is_(None)))
    )
    courts_by_id = {str(c.id): c for c in courts_res.scalars().all()}

    # Leaderboard en tiempo real
    primary_group = tourn.groups[0] if tourn.groups else None
    cfg = {}
    if primary_group:
        cfg, _rows = _split_standings_config(primary_group.standings_json)
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

    active_matches = [m for m in tourn.matches if m.status == "IN_PROGRESS"]
    current_round = max([m.round_number for m in active_matches], default=1) if active_matches else max(
        [m.round_number for m in tourn.matches], default=1
    ) if tourn.matches else 1
    scoring = cfg.get("scoring_system") or (
        "TIME_UNLIMITED" if tourn.match_rule == TournamentMatchRule.TIMED_MATCH and int(tourn.match_duration_minutes or 0) <= 20 else "POINTS_32"
    )
    modality = cfg.get("modality") or "PAREJA_FIJA"
    tiebreak = cfg.get("tiebreak_rule") or "MATCHES_WON"
    target_pts = cfg.get("target_points")
    if target_pts is None:
        target_pts = _target_points_for(scoring)

    return {
        "status": "success",
        "club_id": str(tourn.club_id or club_uuid),
        "tournament": {
            "id": tourn.id,
            "club_id": str(tourn.club_id or club_uuid),
            "name": tourn.name,
            "sport_type": tourn.sport_type,
            "category": tourn.category,
            "status": _public_status(tourn.status),
            "match_duration_minutes": int(cfg.get("round_minutes") or tourn.match_duration_minutes or 15),
            "scoring_system": scoring,
            "target_points": target_pts,
            "modality": modality,
            "tiebreak_rule": tiebreak,
            "pair_count": cfg.get("pair_count") or len(tourn.teams or []),
            "current_round": current_round,
            "start_date": str(tourn.start_date) if tourn.start_date else None,
            "start_time": tourn.start_time.strftime("%H:%M") if tourn.start_time else None,
            "champion_team": tourn.champion_team,
            "runner_up_team": tourn.runner_up_team,
        },
        "courts_status": courts_status,
        "leaderboard": leaderboard,
        "matches": matches_list,
        "config": cfg,
        "tiebreak_order": ["MATCHES_WON", "POINTS_FOR", "HEAD_TO_HEAD"],
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    club_id: Optional[str] = Query(None),
):
    """
    Soporta micro-ajustes rápidos en vivo (+1 / -1) o puntuación directa por equipo.
    Recalcula al instante el leaderboard (PG → puntos a favor → H2H).
    """
    club_uuid = resolve_club_id(request, club_id)
    tourn = await _get_tournament_for_club(db, id, club_uuid)
    if _is_finished(tourn.status):
        raise HTTPException(status_code=409, detail="El torneo ya está finalizado.")

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

    cfg = {}
    if match.group:
        cfg, _ = _split_standings_config(match.group.standings_json)
    scoring = cfg.get("scoring_system") or ""
    target_limit = int(cfg.get("target_points") if cfg.get("target_points") is not None else _target_points_for(scoring))
    time_based = _is_time_unlimited(scoring)

    auto_complete = False
    if payload.status == "COMPLETED":
        auto_complete = True
    elif not time_based and target_limit > 0:
        if scoring == "SETS":
            auto_complete = max(t1, t2) >= target_limit and t1 != t2
        else:
            auto_complete = (t1 + t2 >= target_limit and t1 != t2) or (max(t1, t2) >= target_limit and abs(t1 - t2) >= 2)

    if auto_complete:
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
        "club_id": str(club_uuid),
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    club_id: Optional[str] = Query(None),
):
    """
    Finaliza el torneo americano, asigna el podio oficial (Campeón y Subcampeón),
    y consolida los puntos en la tabla `customers` para el ranking del club con
    detección de sugerencia de ascenso.
    """
    club_uuid = resolve_club_id(request, club_id)
    tourn = await _get_tournament_for_club(db, id, club_uuid, bind_legacy=True)
    if _is_finished(tourn.status):
        raise HTTPException(status_code=409, detail="El torneo ya está finalizado.")

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

    # 2. Consolidar puntos de ranking en CRM Customers (todas las parejas + bonus de podio)
    promoted_players = []
    customers_updated = []
    teams_by_id = {tm.id: tm for tm in (tourn.teams or [])}

    async def _apply_customer_points(cust_id: Optional[int], points: int, as_champion: bool) -> Optional[Customer]:
        if not cust_id:
            return None
        c_res = await db.execute(select(Customer).where(Customer.id == cust_id))
        cust = c_res.scalar_one_or_none()
        if not cust:
            return None
        cust.ranking_points = int(cust.ranking_points or 0) + max(0, int(points))
        if as_champion:
            cust.titles_count = int(cust.titles_count or 0) + 1
            cust.category_wins = int(cust.category_wins or 0) + 1
            cust.consecutive_wins = int(cust.consecutive_wins or 0) + 1
            if cust.consecutive_wins >= 2 or cust.category_wins >= 2:
                cust.promotion_recommended = True
                cust.recommended_category = get_next_category(cust.category)
                promoted_players.append(f"{cust.name} (Sugerido a {cust.recommended_category})")
        customers_updated.append({"customer_id": cust.id, "name": cust.name, "points_added": max(0, int(points))})
        return cust

    for row in leaderboard:
        team = teams_by_id.get(row.get("team_id"))
        if not team:
            continue
        base_pts = int(row.get("ranking_pts") or 0)
        extra = 0
        is_champ = team.id == champ_id
        if is_champ:
            extra = int(payload.champions_points or 0)
        elif team.id == runner_id:
            extra = int(payload.runner_up_points or 0)
        total = base_pts + extra
        await _apply_customer_points(team.customer_id_1, total, is_champ)
        await _apply_customer_points(team.customer_id_2, total, is_champ)

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
        "club_id": str(tourn.club_id or club_uuid),
        "tournament_status": "FINISHED",
        "champion": champ_name,
        "runner_up": runner_name,
        "promoted_players": promoted_players,
        "customers_updated": customers_updated,
        "leaderboard": leaderboard,
        "podium": {
            "champion": champ_name,
            "runner_up": runner_name,
            "third": (leaderboard[2]["team_name"] if len(leaderboard) > 2 else None),
        },
        "history_saved": True,
    }


class StartAmericanoRequest(BaseModel):
    scoring_system: Optional[str] = Field("POINTS_32", description="TIME_UNLIMITED, POINTS_24, POINTS_32, POINTS_40, SETS")
    target_points: Optional[int] = Field(32, description="Puntos objetivo; 0 = infinitos")
    modality: Optional[str] = Field("PAREJA_FIJA", description="PAREJA_FIJA, INDIVIDUAL, SUBE_Y_BAJA")
    round_minutes: Optional[int] = Field(15, ge=1, le=180)
    pair_count: Optional[int] = Field(None, ge=2, le=20)
    tiebreak_rule: Optional[str] = Field("MATCHES_WON")


@router.post(
    "/{id}/start",
    status_code=status.HTTP_200_OK,
    summary="Iniciar Torneo Americano en Vivo (Activa Ronda 1 y pone estado RUNNING)",
)
async def start_americano_tournament(
    id: int,
    request: Request,
    payload: Optional[StartAmericanoRequest] = Body(None),
    db: AsyncSession = Depends(get_db),
    club_id: Optional[str] = Query(None),
):
    """
    Inicia formalmente un Torneo Americano:
    - Persiste scoring / modalidad / desempate / minutos de ronda
    - Genera Ronda 1 si aún no hay cruces
    - Pasa el estado a RUNNING y activa tanteador 0-0 en las pistas
    """
    club_uuid = resolve_club_id(request, club_id)
    tourn = await _get_tournament_for_club(db, id, club_uuid, bind_legacy=True)
    if _is_finished(tourn.status):
        raise HTTPException(status_code=409, detail="El torneo ya está finalizado.")

    payload = payload or StartAmericanoRequest()
    primary_group = tourn.groups[0] if tourn.groups else None
    prev_cfg = {}
    if primary_group:
        prev_cfg, _ = _split_standings_config(primary_group.standings_json)

    cfg = _build_americano_config(
        scoring_system=payload.scoring_system or prev_cfg.get("scoring_system") or "POINTS_32",
        target_points=payload.target_points if payload.target_points is not None else prev_cfg.get("target_points"),
        modality=payload.modality or prev_cfg.get("modality") or "PAREJA_FIJA",
        tiebreak_rule=payload.tiebreak_rule or prev_cfg.get("tiebreak_rule") or "MATCHES_WON",
        round_minutes=payload.round_minutes or prev_cfg.get("round_minutes") or tourn.match_duration_minutes or 15,
        pair_count=payload.pair_count or prev_cfg.get("pair_count") or len(tourn.teams or []) or 4,
    )
    tourn.status = _running_status()
    tourn.match_duration_minutes = int(cfg["round_minutes"])

    if primary_group:
        _, rows = _split_standings_config(primary_group.standings_json)
        if not rows:
            rows = [
                {
                    "team_id": tm.id,
                    "team_name": tm.team_name,
                    "pj": 0, "pg": 0, "pp": 0,
                    "pts_favor": 0, "pts_contra": 0, "diff": 0, "ranking_pts": 0,
                }
                for tm in (tourn.teams or [])
            ]
        primary_group.standings_json = _merge_standings_config(cfg, rows)

    if not tourn.matches and primary_group and tourn.teams:
        court_uuids = _parse_court_uuids(tourn.assigned_court_ids or [])
        stage_name = "SUBE_Y_BAJA" if _is_sube_y_baja(cfg.get("modality")) else "ROUND_ROBIN"
        for r_idx, pairings in enumerate(_build_fixture_rounds(list(tourn.teams), court_uuids, cfg.get("modality")), start=1):
            st = "IN_PROGRESS" if r_idx == 1 else "SCHEDULED"
            for t1, t2, court in pairings:
                db.add(_make_match(tourn.id, primary_group.id, r_idx, t1, t2, court, stage_name, st))
        await db.flush()
        await db.refresh(tourn)

    r1_matches = [m for m in tourn.matches if m.round_number == 1]
    for m in r1_matches:
        m.status = "IN_PROGRESS"
        if not m.scores_json:
            m.scores_json = [{"set": 1, "t1": 0, "t2": 0}]

    await db.commit()
    await db.refresh(tourn)

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
        "club_id": str(tourn.club_id or club_uuid),
        "tournament_status": "RUNNING",
        "round_active": 1,
        "active_matches": len(r1_matches),
        "config": cfg,
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
    request: Request,
    payload: Optional[NextRoundRequest] = Body(None),
    db: AsyncSession = Depends(get_db),
    club_id: Optional[str] = Query(None),
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
    club_uuid = resolve_club_id(request, club_id)
    tourn = await _get_tournament_for_club(db, id, club_uuid)
    if _is_finished(tourn.status):
        raise HTTPException(status_code=409, detail="El torneo ya está finalizado.")

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
    primary_group = tourn.groups[0] if tourn.groups else None
    cfg = {}
    if primary_group:
        cfg, _ = _split_standings_config(primary_group.standings_json)
    modality = (payload.modality if payload and payload.modality else None) or cfg.get("modality") or "PAREJA_FIJA"

    if next_scheduled and not _is_sube_y_baja(modality):
        for m in next_scheduled:
            m.status = "IN_PROGRESS"
            if not m.scores_json:
                m.scores_json = [{"set": 1, "t1": 0, "t2": 0}]
    else:
        court_uuids = _parse_court_uuids(tourn.assigned_court_ids or [])
        teams_by_id = {tm.id: tm for tm in (tourn.teams or [])}
        new_pairings = []

        if _is_sube_y_baja(modality) and (payload is None or payload.auto_promote_relegate) and court_uuids:
            round_matches = [m for m in tourn.matches if m.round_number == current_round]
            by_court = {}
            for m in round_matches:
                key = str(m.court_id) if m.court_id else ""
                by_court[key] = m

            winners, losers = [], []
            for cu in court_uuids:
                m = by_court.get(str(cu))
                if not m or not m.team1_id or not m.team2_id:
                    continue
                s = m.scores_json[0] if m.scores_json else {"t1": 0, "t2": 0}
                t1_pts = int(s.get("t1", 0))
                t2_pts = int(s.get("t2", 0))
                w = m.winner_team_id
                if not w:
                    if t1_pts > t2_pts:
                        w = m.team1_id
                    elif t2_pts > t1_pts:
                        w = m.team2_id
                    else:
                        w = m.team1_id
                l = m.team2_id if w == m.team1_id else m.team1_id
                winners.append(w)
                losers.append(l)

            n = len(winners)
            if n == 1:
                new_pairings = [(winners[0], losers[0], court_uuids[0])]
            elif n >= 2:
                new_pairings.append((winners[0], winners[1], court_uuids[0]))
                for i in range(1, n - 1):
                    new_pairings.append((losers[i - 1], winners[i + 1], court_uuids[i]))
                new_pairings.append((losers[n - 2], losers[n - 1], court_uuids[n - 1]))

        if not new_pairings and primary_group:
            current_standings = _recalculate_americano_standings(primary_group, tourn.matches)
            ranked_team_ids = [row["team_id"] for row in current_standings]
            for i in range(0, len(ranked_team_ids) - 1, 2):
                court = court_uuids[(i // 2) % len(court_uuids)] if court_uuids else None
                new_pairings.append((ranked_team_ids[i], ranked_team_ids[i + 1], court))

        if primary_group:
            for (t1_id, t2_id, assigned_c) in new_pairings:
                if t1_id == t2_id:
                    continue
                t1_obj = teams_by_id.get(t1_id)
                t2_obj = teams_by_id.get(t2_id)
                new_m = TournamentMatch(
                    tournament_id=tourn.id,
                    group_id=primary_group.id,
                    stage="SUBE_Y_BAJA" if _is_sube_y_baja(modality) else "ROUND_ROBIN",
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
        "club_id": str(tourn.club_id or club_uuid),
    }






