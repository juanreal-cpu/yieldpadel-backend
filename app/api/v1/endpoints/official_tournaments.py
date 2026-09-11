from datetime import date, datetime, time
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Union
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.court import Court
from app.models.customer import Customer
from app.models.official_tournaments import (
    OfficialTournament,
    TournamentFormatType,
    TournamentGroup,
    TournamentMatch,
    TournamentMatchRule,
    TournamentTeam,
    TournamentTiebreakRule,
    OfficialTournamentStatus,
)
from app.models.slot import SlotMode, SlotStatus, TimeSlot
from app.services.ranking_engine import award_tournament_points, get_next_category

logger = logging.getLogger("yieldpadel.official_tournaments")

router = APIRouter()


# ----------------------------------------------------
# Pydantic Schemas
# ----------------------------------------------------
class CreateOfficialTournamentRequest(BaseModel):
    name: str = Field(..., description="Nombre del torneo oficial, ej: Copa Aniversario Capital Pádel")
    sport_type: str = Field("PADEL", description="Deporte: PADEL, PICKLEBALL, etc.")
    category: str = Field("4ta", description="Categoría oficial: 1ra, 2da, 3ra, 4ta, 5ta, 6ta")
    format_type: TournamentFormatType = Field(TournamentFormatType.GROUPS_PLAYOFFS)
    match_rule: TournamentMatchRule = Field(TournamentMatchRule.BEST_OF_3)
    match_duration_minutes: int = Field(60, ge=30, le=180)
    tiebreak_rule: TournamentTiebreakRule = Field(TournamentTiebreakRule.SETS_DIFF)
    start_date: str = Field(..., description="Fecha de inicio YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="Fecha de fin YYYY-MM-DD")
    start_time: str = Field("08:00", description="Hora de inicio HH:MM")
    end_time: str = Field("22:00", description="Hora fin HH:MM")
    assigned_court_ids: List[str] = Field(..., description="IDs de las canchas físicas asignadas")
    num_groups: Optional[int] = Field(2, ge=1, le=8, description="Número de grupos iniciales (default: 2)")


class RegisterTeamRequest(BaseModel):
    tournament_id: int
    team_name: str
    customer_id_1: int
    customer_id_2: int
    group_id: Optional[int] = None
    seed: Optional[int] = None


class RecordScoreRequest(BaseModel):
    match_id: int
    scores: List[Dict[str, int]] = Field(
        ...,
        description="Lista de sets, ej: [{'set': 1, 't1': 6, 't2': 4}, {'set': 2, 't1': 6, 't2': 3}]",
    )
    winner_team_id: int
    status: Optional[str] = Field("COMPLETED", description="COMPLETED o IN_PROGRESS")


class FinalizeTournamentRequest(BaseModel):
    tournament_id: int
    champion_team_id: int
    runner_up_team_id: int
    champions_points: int = Field(100, description="Puntos de ranking para campeones (default: 100)")
    runner_up_points: int = Field(50, description="Puntos de ranking para subcampeones (default: 50)")


# ----------------------------------------------------
# Endpoints
# ----------------------------------------------------
@router.get("/", summary="Listar torneos oficiales con grupos y partidos")
async def list_official_tournaments(
    status_filter: Optional[str] = Query(None, description="Filtrar por status"),
    category_filter: Optional[str] = Query(None, description="Filtrar por categoría"),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(OfficialTournament)
        .options(
            selectinload(OfficialTournament.teams).selectinload(TournamentTeam.player1),
            selectinload(OfficialTournament.teams).selectinload(TournamentTeam.player2),
            selectinload(OfficialTournament.groups).selectinload(TournamentGroup.matches),
            selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team1),
            selectinload(OfficialTournament.matches).selectinload(TournamentMatch.team2),
        )
        .order_by(desc(OfficialTournament.created_at))
    )
    if status_filter:
        stmt = stmt.where(OfficialTournament.status == status_filter)
    if category_filter and category_filter != "ALL":
        stmt = stmt.where(OfficialTournament.category == category_filter)

    res = await db.execute(stmt)
    tournaments = res.scalars().all()

    output = []
    for t in tournaments:
        output.append({
            "id": t.id,
            "name": t.name,
            "sport_type": t.sport_type,
            "category": t.category,
            "format_type": t.format_type.value,
            "match_rule": t.match_rule.value,
            "match_duration_minutes": t.match_duration_minutes,
            "tiebreak_rule": t.tiebreak_rule.value,
            "status": t.status.value,
            "start_date": str(t.start_date) if t.start_date else None,
            "end_date": str(t.end_date) if t.end_date else None,
            "start_time": t.start_time.strftime("%H:%M") if t.start_time else None,
            "end_time": t.end_time.strftime("%H:%M") if t.end_time else None,
            "assigned_court_ids": t.assigned_court_ids or [],
            "champion_team": t.champion_team,
            "runner_up_team": t.runner_up_team,
            "teams_count": len(t.teams),
            "groups": [
                {
                    "id": g.id,
                    "name": g.name,
                    "standings": g.standings_json or [],
                    "matches_count": len(g.matches),
                }
                for g in t.groups
            ],
            "matches": [
                {
                    "id": m.id,
                    "stage": m.stage,
                    "round_number": m.round_number,
                    "group_id": m.group_id,
                    "team1": {
                        "id": m.team1.id if m.team1 else None,
                        "name": m.team1.team_name if m.team1 else (m.team1_label or "Por definir"),
                    },
                    "team2": {
                        "id": m.team2.id if m.team2 else None,
                        "name": m.team2.team_name if m.team2 else (m.team2_label or "Por definir"),
                    },
                    "court_id": str(m.court_id) if m.court_id else None,
                    "scheduled_time": m.scheduled_time,
                    "scores": m.scores_json or [],
                    "status": m.status,
                    "winner_team_id": m.winner_team_id,
                }
                for m in t.matches
            ],
            "teams": [
                {
                    "id": tm.id,
                    "team_name": tm.team_name,
                    "player1": {"id": tm.player1.id, "name": tm.player1.name, "category": tm.player1.category} if tm.player1 else None,
                    "player2": {"id": tm.player2.id, "name": tm.player2.name, "category": tm.player2.category} if tm.player2 else None,
                    "group_id": tm.group_id,
                    "seed": tm.seed,
                }
                for tm in t.teams
            ],
        })

    return output


@router.post(
    "/create",
    status_code=status.HTTP_201_CREATED,
    summary="Crear torneo oficial y bloquear masivamente canchas",
)
async def create_official_tournament(
    payload: CreateOfficialTournamentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Crea la entidad de Torneo Oficial, inicializa los grupos y bloquea masivamente
    los turnos en time_slots bajo la etiqueta 🏆 TORNEO OFICIAL para evitar solapamiento con reservas regulares.
    """
    try:
        start_d = date.fromisoformat(payload.start_date)
        end_d = date.fromisoformat(payload.end_date) if payload.end_date else start_d
        s_parts = payload.start_time.split(":")
        start_t = time(int(s_parts[0]), int(s_parts[1]))
        e_parts = payload.end_time.split(":")
        end_t = time(int(e_parts[0]), int(e_parts[1]))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en formato de fechas u horas: {e}")

    # 1. Crear el torneo
    tournament = OfficialTournament(
        name=payload.name.strip(),
        sport_type=payload.sport_type.upper().strip(),
        category=payload.category.strip(),
        format_type=payload.format_type,
        match_rule=payload.match_rule,
        match_duration_minutes=payload.match_duration_minutes,
        tiebreak_rule=payload.tiebreak_rule,
        status=OfficialTournamentStatus.ENROLLMENT,
        start_date=start_d,
        end_date=end_d,
        start_time=start_t,
        end_time=end_t,
        assigned_court_ids=payload.assigned_court_ids,
    )
    db.add(tournament)
    await db.flush()

    # 2. Inicializar Grupos (Ej: Grupo A, Grupo B)
    group_letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
    num_grps = min(len(group_letters), max(1, payload.num_groups or 2))
    for i in range(num_grps):
        grp = TournamentGroup(
            tournament_id=tournament.id,
            name=f"Grupo {group_letters[i]}",
            standings_json=[],
        )
        db.add(grp)

    # 3. Bloqueo masivo en time_slots para evitar solapamientos con reservas regulares
    blocked_count = 0
    for court_id_str in payload.assigned_court_ids:
        try:
            c_uuid = uuid.UUID(court_id_str)
        except ValueError:
            continue

        court_res = await db.execute(select(Court).where(Court.id == c_uuid))
        court = court_res.scalar_one_or_none()
        if not court:
            continue

        # Bloquear slots existentes en el rango de fecha
        slots_stmt = select(TimeSlot).where(
            TimeSlot.court_id == c_uuid,
            TimeSlot.date >= start_d,
            TimeSlot.date <= end_d,
            TimeSlot.start_time >= start_t,
            TimeSlot.end_time <= end_t,
        )
        existing_slots = (await db.execute(slots_stmt)).scalars().all()

        if existing_slots:
            for s in existing_slots:
                s.status = SlotStatus.BLOCKED
                s.slot_type = "TOURNAMENT"
                s.tournament_type = "OFFICIAL"
                s.tournament_name = f"🏆 TORNEO OFICIAL: {tournament.name}"
                s.players_names = [f"Torneo: {tournament.name} ({tournament.category})"]
                s.booked_spots = s.capacity
                blocked_count += 1
        else:
            # Si no hay slot generado, crear el slot bloqueado representativo
            new_slot = TimeSlot(
                court_id=c_uuid,
                club_id=1,
                date=start_d,
                start_time=start_t,
                end_time=end_t,
                total_price=Decimal("0.0"),
                price_total_cop=Decimal("0.0"),
                mode=SlotMode.FULL_COURT,
                capacity=4,
                booked_spots=4,
                status=SlotStatus.BLOCKED,
                category=tournament.category,
                slot_type="TOURNAMENT",
                tournament_type="OFFICIAL",
                tournament_name=f"🏆 TORNEO OFICIAL: {tournament.name}",
                players_names=[f"Torneo: {tournament.name} ({tournament.category})"],
                sport_type=tournament.sport_type,
            )
            db.add(new_slot)
            blocked_count += 1

    await db.commit()
    await db.refresh(tournament)

    return {
        "status": "success",
        "message": f"Torneo '{tournament.name}' creado exitosamente. Se protegieron {blocked_count} turnos de pista contra solapamiento.",
        "tournament_id": tournament.id,
        "category": tournament.category,
        "format": tournament.format_type.value,
    }


@router.post(
    "/register-team",
    status_code=status.HTTP_201_CREATED,
    summary="Inscribir pareja desde el CRM con validación de categoría",
)
async def register_team(
    payload: RegisterTeamRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Inscribe una pareja de jugadores validando su existencia y categoría en el CRM.
    """
    # 1. Validar torneo
    tourn_res = await db.execute(
        select(OfficialTournament)
        .options(selectinload(OfficialTournament.teams), selectinload(OfficialTournament.groups))
        .where(OfficialTournament.id == payload.tournament_id)
    )
    tourn = tourn_res.scalar_one_or_none()
    if not tourn:
        raise HTTPException(status_code=404, detail="Torneo oficial no encontrado")

    # 2. Obtener y validar ambos jugadores
    cust1_res = await db.execute(select(Customer).where(Customer.id == payload.customer_id_1))
    cust1 = cust1_res.scalar_one_or_none()
    cust2_res = await db.execute(select(Customer).where(Customer.id == payload.customer_id_2))
    cust2 = cust2_res.scalar_one_or_none()

    if not cust1 or not cust2:
        raise HTTPException(status_code=404, detail="Uno o ambos jugadores no existen en el CRM.")

    if cust1.id == cust2.id:
        raise HTTPException(status_code=400, detail="Una pareja debe estar compuesta por dos jugadores distintos.")

    # 3. Validar categoría
    t_cat = tourn.category.strip().lower()
    c1_cat = (cust1.category or "4ta").strip().lower()
    c2_cat = (cust2.category or "4ta").strip().lower()

    # Si la categoría del jugador es significativamente superior a la del torneo (ej: 1ra jugando en 5ta)
    cat_order = ["6ta", "5ta", "4ta", "3ra", "2da", "1ra"]
    t_idx = cat_order.index(t_cat) if t_cat in cat_order else 2
    c1_idx = cat_order.index(c1_cat) if c1_cat in cat_order else 2
    c2_idx = cat_order.index(c2_cat) if c2_cat in cat_order else 2

    if c1_idx > t_idx or c2_idx > t_idx:
        higher_player = cust1.name if c1_idx > t_idx else cust2.name
        higher_cat = cust1.category if c1_idx > t_idx else cust2.category
        logger.warning(
            f"Alerta de categoría: {higher_player} tiene nivel {higher_cat} e ingresa a torneo {tourn.category}"
        )

    # 4. Asignar grupo si no viene especificado (distribución balanceada round-robin)
    group_id_val = payload.group_id
    if not group_id_val and tourn.groups:
        # Contar equipos por grupo
        groups_list = tourn.groups
        min_group = min(
            groups_list,
            key=lambda g: sum(1 for tm in tourn.teams if tm.group_id == g.id),
        )
        group_id_val = min_group.id

    # 5. Crear el equipo
    team = TournamentTeam(
        tournament_id=tourn.id,
        team_name=payload.team_name.strip(),
        customer_id_1=cust1.id,
        customer_id_2=cust2.id,
        group_id=group_id_val,
        seed=payload.seed,
    )
    db.add(team)
    await db.flush()

    # Actualizar la tabla de posiciones del grupo (standings_json)
    if group_id_val:
        for g in tourn.groups:
            if g.id == group_id_val:
                cur_standings = list(g.standings_json or [])
                cur_standings.append({
                    "team_id": team.id,
                    "team_name": team.team_name,
                    "pj": 0,
                    "pg": 0,
                    "pp": 0,
                    "sf": 0,
                    "sc": 0,
                    "gf": 0,
                    "gc": 0,
                    "pts": 0,
                })
                g.standings_json = cur_standings
                break

    await db.commit()
    await db.refresh(team)

    return {
        "status": "success",
        "message": f"Pareja '{team.team_name}' inscrita con éxito ({cust1.name} y {cust2.name}).",
        "team_id": team.id,
        "group_id": group_id_val,
    }


@router.post(
    "/record-score",
    status_code=status.HTTP_200_OK,
    summary="Registrar marcador y recalcular tabla de posiciones / bracket",
)
async def record_score(
    payload: RecordScoreRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Recibe el marcador de un partido, recalcula en tiempo real los puntos (PJ, PG, PP, SF, SC, GF, GC)
    del grupo o avanza a la dupla ganadora en la fase de playoffs.
    """
    match_stmt = (
        select(TournamentMatch)
        .options(
            selectinload(TournamentMatch.group),
            selectinload(TournamentMatch.team1),
            selectinload(TournamentMatch.team2),
            selectinload(TournamentMatch.tournament),
        )
        .where(TournamentMatch.id == payload.match_id)
    )
    res = await db.execute(match_stmt)
    match = res.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Partido no encontrado")

    match.scores_json = payload.scores
    match.winner_team_id = payload.winner_team_id
    match.status = payload.status or "COMPLETED"

    # 1. Si pertenece a fase de grupos, recalcular la tabla del grupo
    if match.group and match.team1 and match.team2:
        group = match.group
        standings = {item["team_id"]: item for item in (group.standings_json or [])}

        # Inicializar si no estaban en el standing
        for tm in [match.team1, match.team2]:
            if tm.id not in standings:
                standings[tm.id] = {
                    "team_id": tm.id,
                    "team_name": tm.team_name,
                    "pj": 0,
                    "pg": 0,
                    "pp": 0,
                    "sf": 0,
                    "sc": 0,
                    "gf": 0,
                    "gc": 0,
                    "pts": 0,
                }

        # Calcular sets y games
        t1_sets, t2_sets = 0, 0
        t1_games, t2_games = 0, 0
        for s in payload.scores:
            g1 = s.get("t1", 0)
            g2 = s.get("t2", 0)
            t1_games += g1
            t2_games += g2
            if g1 > g2:
                t1_sets += 1
            elif g2 > g1:
                t2_sets += 1

        t1_won = payload.winner_team_id == match.team1_id
        t2_won = payload.winner_team_id == match.team2_id

        # Actualizar Team 1
        st1 = standings[match.team1_id]
        st1["pj"] += 1
        st1["sf"] += t1_sets
        st1["sc"] += t2_sets
        st1["gf"] += t1_games
        st1["gc"] += t2_games
        if t1_won:
            st1["pg"] += 1
            st1["pts"] += 3
        else:
            st1["pp"] += 1

        # Actualizar Team 2
        st2 = standings[match.team2_id]
        st2["pj"] += 1
        st2["sf"] += t2_sets
        st2["sc"] += t1_sets
        st2["gf"] += t2_games
        st2["gc"] += t1_games
        if t2_won:
            st2["pg"] += 1
            st2["pts"] += 3
        else:
            st2["pp"] += 1

        # Ordenar tabla por PTS, luego diferencia de sets (SF-SC), luego games (GF-GC)
        sorted_standings = list(standings.values())
        sorted_standings.sort(
            key=lambda x: (
                x.get("pts", 0),
                (x.get("sf", 0) - x.get("sc", 0)),
                (x.get("gf", 0) - x.get("gc", 0)),
            ),
            reverse=True,
        )
        group.standings_json = sorted_standings

    await db.commit()

    return {
        "status": "success",
        "message": f"Marcador guardado y tabla del grupo actualizada. Ganador: ID {payload.winner_team_id}.",
        "match_id": match.id,
        "winner_team_id": match.winner_team_id,
    }


@router.post(
    "/finalize",
    status_code=status.HTTP_200_OK,
    summary="Cerrar torneo oficial, asignar puntos de ranking y activar sugerencia de ascenso CRM",
)
async def finalize_official_tournament(
    payload: FinalizeTournamentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Cierra el torneo, asigna paramétricamente los puntos de ranking a campeones/subcampeones
    y dispara la regla de recomendación de ascenso de categoría en el CRM.
    """
    tourn_res = await db.execute(
        select(OfficialTournament)
        .options(selectinload(OfficialTournament.teams))
        .where(OfficialTournament.id == payload.tournament_id)
    )
    tourn = tourn_res.scalar_one_or_none()
    if not tourn:
        raise HTTPException(status_code=404, detail="Torneo oficial no encontrado")

    # Identificar parejas de campeones y subcampeones
    champ_team: Optional[TournamentTeam] = None
    runner_team: Optional[TournamentTeam] = None

    for tm in tourn.teams:
        if tm.id == payload.champion_team_id:
            champ_team = tm
        if tm.id == payload.runner_up_team_id:
            runner_team = tm

    if not champ_team:
        raise HTTPException(status_code=404, detail="Equipo campeón no encontrado en el torneo")

    tourn.status = OfficialTournamentStatus.FINISHED
    tourn.champion_team = champ_team.team_name
    tourn.runner_up_team = runner_team.team_name if runner_team else "Finalista"

    # Asignar puntos y ascensos a los jugadores campeones
    champions_players_ids = [champ_team.customer_id_1, champ_team.customer_id_2]
    promoted_names = []

    for cust_id in champions_players_ids:
        c_res = await db.execute(select(Customer).where(Customer.id == cust_id))
        cust = c_res.scalar_one_or_none()
        if cust:
            cust.ranking_points += payload.champions_points
            cust.titles_count += 1
            cust.category_wins += 1
            cust.consecutive_wins += 1

            # Disparar regla de ascenso si ha ganado 2 torneos consecutivos o título en su categoría
            if cust.consecutive_wins >= 2 or cust.category_wins >= 2:
                cust.promotion_recommended = True
                cust.recommended_category = get_next_category(cust.category)
                promoted_names.append(f"{cust.name} (Sugerido a {cust.recommended_category})")

    # Asignar puntos a subcampeones
    if runner_team:
        for cust_id in [runner_team.customer_id_1, runner_team.customer_id_2]:
            c_res = await db.execute(select(Customer).where(Customer.id == cust_id))
            cust = c_res.scalar_one_or_none()
            if cust:
                cust.ranking_points += payload.runner_up_points

    await db.commit()
    await db.refresh(tourn)

    msg_ascensos = f" | Sugerencias de ascenso generadas: {', '.join(promoted_names)}" if promoted_names else ""
    return {
        "status": "success",
        "message": f"Torneo '{tourn.name}' finalizado con éxito. Campeón: {champ_team.team_name} (+{payload.champions_points} pts).{msg_ascensos}",
        "tournament_id": tourn.id,
        "champion_team": champ_team.team_name,
        "promoted_players": promoted_names,
    }
