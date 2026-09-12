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
    tournament_id: Optional[int] = None
    team_name: Optional[str] = None
    pair_name: Optional[str] = None
    customer_id_1: Optional[Union[int, str]] = None
    customer_id_2: Optional[Union[int, str]] = None
    player1_id: Optional[Union[int, str]] = None
    player2_id: Optional[Union[int, str]] = None
    group_id: Optional[Union[int, str]] = None
    assigned_group: Optional[Union[int, str]] = None
    seed: Optional[int] = None


class RecordScoreRequest(BaseModel):
    match_id: Optional[int] = None
    scores: Optional[Union[List[Dict[str, Any]], Dict[str, Any], List[Any]]] = Field(
        None,
        description="Lista de sets o dict con sets",
    )
    winner_team_id: Optional[Union[int, str]] = None
    winner: Optional[Union[int, str]] = None
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
@router.post(
    "/{tournament_id}/enroll-pair",
    status_code=status.HTTP_201_CREATED,
    summary="Inscribir pareja oficial en torneo",
)
@router.post(
    "/official/{tournament_id}/enroll-pair",
    status_code=status.HTTP_201_CREATED,
    summary="Inscribir pareja oficial en torneo (alias)",
)
async def register_team(
    payload: RegisterTeamRequest,
    tournament_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Inscribe una pareja de jugadores validando su existencia y categoría en el CRM.
    Soporta tanto register-team como /{tournament_id}/enroll-pair.
    """
    t_id = tournament_id or payload.tournament_id
    if not t_id:
        raise HTTPException(status_code=400, detail="Falta el ID del torneo.")

    # 1. Validar torneo
    tourn_res = await db.execute(
        select(OfficialTournament)
        .options(selectinload(OfficialTournament.teams), selectinload(OfficialTournament.groups))
        .where(OfficialTournament.id == t_id)
    )
    tourn = tourn_res.scalar_one_or_none()
    if not tourn:
        raise HTTPException(status_code=404, detail="Torneo oficial no encontrado")

    # 2. Obtener y validar ambos jugadores (soportando customer_id_1 o player1_id, y enteros o strings de teléfono/nombre)
    p1_val = payload.customer_id_1 if payload.customer_id_1 is not None else payload.player1_id
    p2_val = payload.customer_id_2 if payload.customer_id_2 is not None else payload.player2_id

    if not p1_val or not p2_val:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos los 2 jugadores de la dupla.")

    async def resolve_customer(val: Union[int, str]) -> Customer:
        # Si es int o string de digitos
        if isinstance(val, int) or (isinstance(val, str) and val.isdigit()):
            c_res = await db.execute(select(Customer).where(Customer.id == int(val)))
            cust = c_res.scalar_one_or_none()
            if cust:
                return cust
        # Si es string (telefono o nombre)
        val_str = str(val).strip()
        c_res = await db.execute(select(Customer).where(or_(Customer.phone == val_str, Customer.name.ilike(val_str))))
        cust = c_res.scalars().first()
        if cust:
            return cust
        # Crear nuevo cliente externo si no existe
        new_c = Customer(
            name=val_str if not val_str.startswith("+") and not val_str.isdigit() else f"Jugador {val_str[-4:]}",
            phone=val_str if val_str.isdigit() or val_str.startswith("+") else "3000000000",
            category=tourn.category or "4ta",
            client_type="Estándar",
        )
        db.add(new_c)
        await db.flush()
        return new_c

    cust1 = await resolve_customer(p1_val)
    cust2 = await resolve_customer(p2_val)

    if cust1.id == cust2.id:
        raise HTTPException(status_code=400, detail="Una pareja debe estar compuesta por dos jugadores distintos.")

    # 3. Validar categoría
    t_cat = (tourn.category or "4ta").strip().lower()
    c1_cat = (cust1.category or "4ta").strip().lower()
    c2_cat = (cust2.category or "4ta").strip().lower()

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

    # 4. Asignar grupo
    grp_input = payload.group_id if payload.group_id is not None else payload.assigned_group
    group_id_val = None

    if grp_input is not None:
        grp_str = str(grp_input).strip()
        if grp_str.isdigit():
            group_id_val = int(grp_str)
        else:
            # Buscar por nombre (ej: "Grupo A", "A")
            for g in tourn.groups:
                if grp_str.lower() in g.name.lower():
                    group_id_val = g.id
                    break

    if not group_id_val and tourn.groups:
        # Distribución balanceada
        group_id_val = min(
            tourn.groups,
            key=lambda g: sum(1 for tm in tourn.teams if tm.group_id == g.id),
        ).id

    # Nombre de la pareja
    team_name_final = (payload.team_name or payload.pair_name or f"{cust1.name.split()[0]} / {cust2.name.split()[0]}").strip()

    # 5. Crear el equipo
    team = TournamentTeam(
        tournament_id=tourn.id,
        team_name=team_name_final,
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
    "/{tournament_id}/generate-matches",
    status_code=status.HTTP_200_OK,
    summary="Generar cruces de partidos round-robin para los grupos",
)
@router.post(
    "/official/{tournament_id}/generate-matches",
    status_code=status.HTTP_200_OK,
    summary="Generar cruces de partidos round-robin (alias)",
)
async def generate_matches(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Genera automáticamente el fixture y los cruces de todos contra todos (Round-Robin)
    para cada grupo del torneo oficial que tenga al menos 2 parejas.
    """
    tourn_res = await db.execute(
        select(OfficialTournament)
        .options(
            selectinload(OfficialTournament.groups).selectinload(TournamentGroup.matches),
            selectinload(OfficialTournament.teams),
        )
        .where(OfficialTournament.id == tournament_id)
    )
    tourn = tourn_res.scalar_one_or_none()
    if not tourn:
        raise HTTPException(status_code=404, detail="Torneo oficial no encontrado")

    created_matches = 0
    import itertools

    for group in tourn.groups:
        grp_teams = [t for t in tourn.teams if t.group_id == group.id]
        if len(grp_teams) < 2:
            continue

        existing_pairs = set()
        for m in group.matches:
            if m.team1_id and m.team2_id:
                pair_key = tuple(sorted([m.team1_id, m.team2_id]))
                existing_pairs.add(pair_key)

        round_num = 1
        for t1, t2 in itertools.combinations(grp_teams, 2):
            pair_key = tuple(sorted([t1.id, t2.id]))
            if pair_key in existing_pairs:
                continue

            match = TournamentMatch(
                tournament_id=tourn.id,
                group_id=group.id,
                stage="GROUP_STAGE",
                round_number=round_num,
                team1_id=t1.id,
                team2_id=t2.id,
                team1_label=t1.team_name,
                team2_label=t2.team_name,
                scores_json=[],
                status="SCHEDULED",
            )
            db.add(match)
            existing_pairs.add(pair_key)
            created_matches += 1
            round_num += 1

    if created_matches > 0:
        tourn.status = OfficialTournamentStatus.IN_PROGRESS

    await db.commit()

    return {
        "status": "success",
        "message": f"Se generaron {created_matches} cruces de grupo exitosamente.",
        "matches_created": created_matches,
    }


@router.post(
    "/record-score",
    status_code=status.HTTP_200_OK,
    summary="Registrar marcador y recalcular tabla de posiciones / bracket",
)
@router.post(
    "/matches/{match_id}/record-score",
    status_code=status.HTTP_200_OK,
    summary="Registrar marcador por id de partido",
)
@router.post(
    "/official/matches/{match_id}/record-score",
    status_code=status.HTTP_200_OK,
    summary="Registrar marcador oficial (alias)",
)
async def record_score(
    payload: RecordScoreRequest,
    match_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Recibe el marcador de un partido, recalcula en tiempo real los puntos (PJ, PG, PP, SF, SC, GF, GC)
    del grupo o avanza a la dupla ganadora en la fase de playoffs.
    """
    m_id = match_id or payload.match_id
    if not m_id:
        raise HTTPException(status_code=400, detail="Falta el ID del partido.")

    match_stmt = (
        select(TournamentMatch)
        .options(
            selectinload(TournamentMatch.group),
            selectinload(TournamentMatch.team1),
            selectinload(TournamentMatch.team2),
            selectinload(TournamentMatch.tournament),
        )
        .where(TournamentMatch.id == m_id)
    )
    res = await db.execute(match_stmt)
    match = res.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Partido no encontrado")

    # Normalizar scores
    raw_scores = payload.scores or []
    norm_scores = []
    if isinstance(raw_scores, list):
        for idx, s in enumerate(raw_scores):
            if isinstance(s, dict):
                norm_scores.append({
                    "set": s.get("set", idx + 1),
                    "t1": int(s.get("t1", 0)),
                    "t2": int(s.get("t2", 0)),
                })
            elif isinstance(s, str) and "-" in s:
                p = s.split("-")
                try:
                    norm_scores.append({"set": idx + 1, "t1": int(p[0].strip()), "t2": int(p[1].strip())})
                except Exception:
                    pass
    elif isinstance(raw_scores, dict):
        for k, v in raw_scores.items():
            if isinstance(v, str) and "-" in v:
                p = v.split("-")
                norm_scores.append({"set": len(norm_scores) + 1, "t1": int(p[0].strip()), "t2": int(p[1].strip())})

    # Resolver winner_team_id
    win_val = payload.winner_team_id if payload.winner_team_id is not None else payload.winner
    winner_team_id = None
    if win_val is not None:
        win_str = str(win_val).strip()
        if win_str == "TEAM_A" and match.team1_id:
            winner_team_id = match.team1_id
        elif win_str == "TEAM_B" and match.team2_id:
            winner_team_id = match.team2_id
        elif win_str.isdigit():
            winner_team_id = int(win_str)
        elif match.team1 and win_str.lower() in match.team1.team_name.lower():
            winner_team_id = match.team1_id
        elif match.team2 and win_str.lower() in match.team2.team_name.lower():
            winner_team_id = match.team2_id

    # Si no se pasó ganador explícito pero hay sets anotados, inferir ganador
    if not winner_team_id and norm_scores and match.team1_id and match.team2_id:
        t1_w, t2_w = 0, 0
        for s in norm_scores:
            if s["t1"] > s["t2"]:
                t1_w += 1
            elif s["t2"] > s["t1"]:
                t2_w += 1
        if t1_w > t2_w:
            winner_team_id = match.team1_id
        elif t2_w > t1_w:
            winner_team_id = match.team2_id

    match.scores_json = norm_scores
    match.winner_team_id = winner_team_id
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
        for s in norm_scores:
            g1 = s.get("t1", 0)
            g2 = s.get("t2", 0)
            t1_games += g1
            t2_games += g2
            if g1 > g2:
                t1_sets += 1
            elif g2 > g1:
                t2_sets += 1

        t1_won = winner_team_id == match.team1_id
        t2_won = winner_team_id == match.team2_id

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
        "message": f"Marcador guardado exitosamente. Ganador: ID {winner_team_id}.",
        "match_id": match.id,
        "winner_team_id": match.winner_team_id,
        "scores": match.scores_json,
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
