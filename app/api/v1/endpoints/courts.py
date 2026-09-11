from typing import List, Optional
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.timezone import get_bogota_now
from app.models.court import Court
from app.models.slot import TimeSlot, SlotStatus
from app.schemas.slot import CourtResponse
from app.api.v1.endpoints.slots import ensure_five_courts, to_participants_list

try:
    from app.models.access import ClubPresence
except Exception:
    ClubPresence = None

router = APIRouter()


class CourtUpdateRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    sport_type: Optional[str] = None
    max_capacity: Optional[int] = None


@router.get("", response_model=List[CourtResponse], status_code=status.HTTP_200_OK)
@router.get("/", response_model=List[CourtResponse], status_code=status.HTTP_200_OK)
async def get_courts(
    sport: Optional[str] = Query(None, description="Filtrar por deporte (PADEL, PICKLEBALL, VOLLEYBALL, PILATES, CONSOLE)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna el listado completo de canchas y pistas multideporte del club:
    - Pádel 1 a 5
    - Pickleball 1 y 2
    - Arena Vóley
    - Estudio Pilates
    - Sala Gaming / Consola
    """
    courts = await ensure_five_courts(db)
    if sport and sport.upper() not in ["ALL", "TODAS", ""]:
        courts = [
            c for c in courts
            if (getattr(c, "sport_type", "PADEL") or "PADEL").upper() == sport.strip().upper()
        ]
    seen_ids = set()
    seen_keys = set()
    deduped = []
    for c in courts:
        cid = str(c.id)
        st = (getattr(c, "sport_type", None) or getattr(c, "sport", "PADEL") or "PADEL").upper()
        nm = (c.name or "").strip().lower()
        key = (nm, st)
        if cid not in seen_ids and key not in seen_keys:
            seen_ids.add(cid)
            seen_keys.add(key)
            deduped.append(c)
    return deduped


@router.put("/{court_id}", response_model=CourtResponse)
@router.post("/{court_id}", response_model=CourtResponse)
async def update_court(
    court_id: str,
    payload: CourtUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza la parametrización de una pista (nombre, capacidad, estado)."""
    try:
        c_uuid = uuid.UUID(court_id)
        stmt = select(Court).where(Court.id == c_uuid)
    except ValueError:
        stmt = select(Court).where(Court.name.ilike(f"%{court_id}%"))

    result = await db.execute(stmt)
    court = result.scalar_one_or_none()
    if not court:
        raise HTTPException(status_code=404, detail="Pista no encontrada.")

    if payload.name is not None:
        court.name = payload.name.strip()
    if payload.is_active is not None:
        court.is_active = payload.is_active
    if payload.sport_type is not None:
        court.sport_type = payload.sport_type.upper()
    if payload.max_capacity is not None:
        court.max_capacity = payload.max_capacity

    await db.commit()
    await db.refresh(court)
    return court


class CourtStatusUpdateRequest(BaseModel):
    court_id: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None


@router.post("/update-status", response_model=CourtResponse)
@router.put("/update-status", response_model=CourtResponse)
async def update_court_status(
    payload: CourtStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza el estado (Activa / Mantenimiento) y nombre de una pista."""
    target_id = payload.court_id or payload.id
    if not target_id and not payload.name:
        raise HTTPException(status_code=400, detail="Debe especificar court_id o name.")

    court = None
    if target_id:
        try:
            c_uuid = uuid.UUID(str(target_id))
            res = await db.execute(select(Court).where(Court.id == c_uuid))
            court = res.scalar_one_or_none()
        except ValueError:
            res = await db.execute(select(Court).where(Court.name.ilike(f"%{target_id}%")))
            court = res.scalars().first()

    if not court and payload.name:
        res = await db.execute(select(Court).where(Court.name.ilike(f"%{payload.name.strip()}%")))
        court = res.scalars().first()

    if not court:
        raise HTTPException(status_code=404, detail="Pista no encontrada.")

    if payload.name is not None and payload.name.strip():
        court.name = payload.name.strip()

    if payload.is_active is not None:
        court.is_active = payload.is_active
    elif payload.status is not None:
        s_clean = payload.status.lower().strip()
        if s_clean in ["active", "activa", "habilitada", "true", "1"]:
            court.is_active = True
        elif s_clean in ["maintenance", "mantenimiento", "inactiva", "disabled", "false", "0"]:
            court.is_active = False

    await db.commit()
    await db.refresh(court)
    return court


@router.get("/live-status")
async def get_courts_live_status(
    club_id: Optional[str] = Query(None, description="ID del club (opcional, default club único)"),
    db: AsyncSession = Depends(get_db),
):
    """Mapa esquemático 3x3 en tiempo real: estado actual de cada cancha y aforo en sede (America/Bogota)."""
    now_b = get_bogota_now()
    today_b = now_b.date()
    current_time_b = now_b.time()

    courts = await ensure_five_courts(db)
    # Solo canchas deportivas físicas del mapa 3x3 (excluye Pilates / Gaming)
    courts = [
        c for c in courts
        if (getattr(c, "sport_type", None) or getattr(c, "sport", None) or "PADEL").upper() in ("PADEL", "PICKLEBALL", "VOLLEYBALL")
    ]

    if club_id:
        filtered = [c for c in courts if str(getattr(c, "club_id", "") or "") == str(club_id)]
        if filtered:
            courts = filtered

    court_ids = [c.id for c in courts]
    slots_map = {}
    if court_ids:
        res = await db.execute(
            select(TimeSlot).where(
                TimeSlot.court_id.in_(court_ids),
                TimeSlot.date == today_b,
                TimeSlot.status != SlotStatus.CANCELLED,
            )
        )
        for slot in res.scalars().all():
            if slot.start_time <= current_time_b < slot.end_time:
                slots_map[slot.court_id] = slot

    courts_out = []
    for c in sorted(courts, key=lambda x: (getattr(x, "court_number", None) or 99, x.name)):
        sport_type = (getattr(c, "sport_type", None) or getattr(c, "sport", None) or "PADEL").upper()
        capacity = getattr(c, "max_capacity", None) or getattr(c, "capacity", None) or 4
        slot = slots_map.get(c.id)

        court_entry = {
            "court_id": str(c.id),
            "court_name": c.name,
            "sport_type": sport_type,
            "status": "AVAILABLE",
            "players_count": 0,
            "capacity": capacity,
            "players_names": [],
            "time_remaining_minutes": 0,
            "price": 0,
            "slot_id": None,
        }

        if slot is None:
            courts_out.append(court_entry)
            continue

        try:
            participants = to_participants_list(slot.players_names)
            players_names = [p.get("display_name") for p in participants if p.get("display_name")]
        except Exception:
            players_names = list(slot.players_names or [])

        slot_capacity = getattr(slot, "capacity", None) or capacity
        count = len(players_names) or int(getattr(slot, "booked_spots", 0) or 0)

        if slot.status == SlotStatus.BLOCKED or getattr(slot, "is_blocked", False):
            status_out = "MAINTENANCE"
        elif (getattr(slot, "slot_type", "") or "").upper() == "CLASS":
            status_out = "CLASS"
        elif count >= slot_capacity and count > 0:
            status_out = "FULL_MATCH"
        elif count >= 1:
            status_out = "OPEN_MATCH"
        else:
            status_out = "AVAILABLE"

        try:
            end_dt = datetime.combine(today_b, slot.end_time, tzinfo=now_b.tzinfo)
            time_remaining = max(0, int((end_dt - now_b).total_seconds() / 60))
        except Exception:
            time_remaining = 0

        court_entry.update({
            "status": status_out,
            "players_count": count,
            "capacity": slot_capacity,
            "players_names": players_names,
            "time_remaining_minutes": time_remaining,
            "price": float(slot.total_price or 0),
            "slot_id": slot.id,
        })
        courts_out.append(court_entry)

    occupancy_headcount = 0
    if ClubPresence is not None:
        try:
            res = await db.execute(select(ClubPresence).where(ClubPresence.is_inside == True))  # noqa: E712
            occupancy_headcount = len(list(res.scalars().all()))
        except Exception:
            occupancy_headcount = 0

    return {
        "status": "ok",
        "timestamp_bogota": now_b.strftime("%Y-%m-%d %H:%M:%S"),
        "current_occupancy_headcount": occupancy_headcount,
        "courts": courts_out,
    }

