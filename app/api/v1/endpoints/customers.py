import os
import shutil
import time
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.timezone import get_bogota_today
from app.models.customer import Customer
from app.models.membership import MembershipPlan
from app.models.slot import HoldStatus, SlotHold, SlotStatus, TimeSlot
from app.models.booking import Booking
from app.schemas.customers import (
    BotRegisterCustomerRequest,
    BotRegisterResponse,
    BotRegisterData,
)

router = APIRouter()


class CustomerResponse(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = "Jugador"
    phone: Optional[str] = ""
    avatar_url: Optional[str] = None
    category: Optional[str] = "4ta"
    client_type: Optional[str] = "Estándar"
    membership_tier: Optional[str] = "ESTANDAR"
    notes: Optional[str] = None
    gender: Optional[str] = None
    preferred_music: Optional[str] = None
    preferred_play_time: Optional[str] = None
    membership_plan_id: Optional[int] = None
    membership_start_date: Optional[str] = None
    membership_end_date: Optional[str] = None
    days_remaining: Optional[int] = 0
    academy_classes_used: Optional[int] = 0
    total_bookings_completed: Optional[int] = 0
    is_first_visit: Optional[bool] = True
    onboarding_status: Optional[str] = "PENDING"
    ranking_points: Optional[int] = 0
    titles_count: Optional[int] = 0
    category_wins: Optional[int] = 0
    consecutive_wins: Optional[int] = 0
    promotion_recommended: Optional[bool] = False
    recommended_category: Optional[str] = None
    is_minor: Optional[bool] = False
    birth_date: Optional[str] = None
    guardian_id: Optional[int] = None
    guardian_relationship: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None
    plan_name: Optional[str] = None
    americano_discount_pct: Optional[int] = 0
    includes_beverage_perk: Optional[bool] = False
    wallet_balance: Optional[float] = 0.0
    is_recent: Optional[bool] = False
    last_booking_date: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = "success"
    data: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True, extra="allow")


class CustomerCreateRequest(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    category: str = "4ta"
    client_type: Optional[str] = None
    membership_tier: str = "ESTANDAR"
    gender: Optional[str] = "MASCULINO"
    preferred_music: Optional[str] = None
    preferred_play_time: Optional[str] = None
    notes: Optional[str] = None
    membership_plan_id: Optional[int] = None
    is_minor: bool = False
    birth_date: Optional[str] = None
    guardian_id: Optional[int] = None
    guardian_relationship: Optional[str] = None

    model_config = ConfigDict(extra="ignore", from_attributes=True)


class CustomerUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    category: Optional[str] = None
    client_type: Optional[str] = None
    membership_tier: Optional[str] = None
    gender: Optional[str] = None
    preferred_music: Optional[str] = None
    preferred_play_time: Optional[str] = None
    notes: Optional[str] = None
    membership_plan_id: Optional[int] = None
    membership_start_date: Optional[str] = None
    membership_end_date: Optional[str] = None
    academy_classes_used: Optional[int] = None
    is_minor: Optional[bool] = None
    birth_date: Optional[str] = None
    guardian_id: Optional[int] = None
    guardian_relationship: Optional[str] = None

    model_config = ConfigDict(extra="ignore", from_attributes=True)


class CustomerOnboardingRequest(BaseModel):
    onboarding_status: str = "WELCOMED"  # PENDING, WELCOMED, MEMBER_OFFERED
    notes: Optional[str] = None


class LeadRegisterRequest(BaseModel):
    name: str
    phone: str
    category: Optional[str] = "4ta"
    club_name: Optional[str] = None
    notes: Optional[str] = None


def format_customer_response(c: Customer) -> CustomerResponse:
    today = date.today()
    days_rem = 0
    if c.membership_end_date:
        days_rem = (c.membership_end_date - today).days

    guardian_name = c.guardian.name if (c.guardian is not None) else None
    guardian_phone = c.guardian.phone if (c.guardian is not None) else None

    plan_name = None
    americano_discount_pct = 0
    includes_beverage_perk = False

    tier_upper = (c.membership_tier or "ESTANDAR").upper()

    if getattr(c, "membership_plan", None) is not None:
        plan_name = c.membership_plan.name
        americano_discount_pct = c.membership_plan.americano_discount_pct or 0
        includes_beverage_perk = bool(c.membership_plan.includes_beverage_perk)
    elif tier_upper != "ESTANDAR":
        plan_name = tier_upper
        tier_discounts = {
            "TAPIA": 40,
            "COELLO": 30,
            "GALAN": 20,
            "CHINGOTTO": 10,
            "LEBRON": 20,
            "ORO": 40,
            "PLATA": 30,
            "BRONCE": 20,
        }
        americano_discount_pct = tier_discounts.get(tier_upper, 0)
        includes_beverage_perk = tier_upper in ["TAPIA", "COELLO", "GALAN", "CHINGOTTO", "LEBRON", "ORO", "PLATA"]

    today = date.today()
    is_recent = False
    lb_date = getattr(c, "last_booking_date", None)
    if lb_date:
        diff_days = (today - lb_date).days
        is_recent = 0 <= diff_days <= 7

    return CustomerResponse(
        id=c.id,
        name=c.name,
        phone=c.phone,
        avatar_url=c.avatar_url,
        category=c.category or "4ta",
        client_type=c.client_type or "Estándar",
        membership_tier=c.membership_tier or "ESTANDAR",
        notes=c.notes,
        gender=c.gender,
        preferred_music=c.preferred_music,
        preferred_play_time=c.preferred_play_time,
        membership_plan_id=c.membership_plan_id,
        membership_start_date=c.membership_start_date.isoformat() if c.membership_start_date else None,
        membership_end_date=c.membership_end_date.isoformat() if c.membership_end_date else None,
        days_remaining=days_rem,
        academy_classes_used=c.academy_classes_used or 0,
        total_bookings_completed=c.total_bookings_completed or 0,
        is_first_visit=c.is_first_visit,
        onboarding_status=c.onboarding_status or "PENDING",
        ranking_points=c.ranking_points or 0,
        titles_count=c.titles_count or 0,
        category_wins=c.category_wins or 0,
        consecutive_wins=c.consecutive_wins or 0,
        promotion_recommended=c.promotion_recommended or False,
        recommended_category=c.recommended_category,
        is_minor=c.is_minor or False,
        birth_date=c.birth_date.isoformat() if c.birth_date else None,
        guardian_id=c.guardian_id,
        guardian_relationship=c.guardian_relationship,
        guardian_name=guardian_name,
        guardian_phone=guardian_phone,
        plan_name=plan_name,
        americano_discount_pct=americano_discount_pct,
        includes_beverage_perk=includes_beverage_perk,
        wallet_balance=float(c.wallet_balance if hasattr(c, 'wallet_balance') and c.wallet_balance is not None else 0.0),
        is_recent=is_recent,
        last_booking_date=lb_date.isoformat() if lb_date else None,
        email=getattr(c, "email", None) or (
            c.notes.split("Email:")[1].split("|")[0].strip()
            if c.notes and "Email:" in c.notes
            else None
        ),
        status="success",
    )


INITIAL_CUSTOMERS_SEED = [
    {
        "name": "Juan Real Florez",
        "phone": "+573132058547",
        "category": "4ta",
        "client_type": "Socio VIP (Tapia)",
        "membership_tier": "TAPIA",
        "gender": "MASCULINO",
        "preferred_music": "Reggaetón Clásico / Urbano",
        "preferred_play_time": "Noches (7pm-10pm)",
        "membership_start_date": date.today() - timedelta(days=10),
        "membership_end_date": date.today() + timedelta(days=20),
        "academy_classes_used": 1,
        "is_minor": False,
        "notes": "Acceso 6:00 AM - 11:59 PM | 40% descuento en torneos americanos | 4 clases academia",
    },
    {
        "name": "Camilo Real",
        "phone": "+573001234567",
        "category": "4ta",
        "client_type": "Socio VIP (Coello)",
        "membership_tier": "COELLO",
        "gender": "MASCULINO",
        "preferred_music": "Rock en Español / 80s",
        "preferred_play_time": "Noches (7pm-10pm)",
        "membership_start_date": date.today() - timedelta(days=5),
        "membership_end_date": date.today() + timedelta(days=25),
        "academy_classes_used": 0,
        "is_minor": False,
        "notes": "Acceso 6:00 AM - 11:59 PM | 30% descuento en torneos americanos | 2 clases academia",
    },
    {
        "name": "David P",
        "phone": "+573109876543",
        "category": "3ra",
        "client_type": "Socio VIP (Galán)",
        "membership_tier": "GALAN",
        "gender": "MASCULINO",
        "preferred_music": "Electrónica / House",
        "preferred_play_time": "Tardes (4pm-7pm)",
        "membership_start_date": date.today() - timedelta(days=27),
        "membership_end_date": date.today() + timedelta(days=3),
        "academy_classes_used": 0,
        "is_minor": False,
        "notes": "Acceso 6:00 AM - 11:59 PM | 20% descuento en torneos americanos",
    },
    {
        "name": "Andrés Gómez",
        "phone": "+573155551122",
        "category": "4ta",
        "client_type": "Socio Matutino (Chingotto)",
        "membership_tier": "CHINGOTTO",
        "gender": "MASCULINO",
        "preferred_music": "Pop / Indie",
        "preferred_play_time": "Mañanas (6am-9am)",
        "membership_start_date": date.today() - timedelta(days=12),
        "membership_end_date": date.today() + timedelta(days=18),
        "academy_classes_used": 0,
        "is_minor": False,
        "notes": "Acceso 6:00 AM - 3:00 PM | 10% descuento en torneos americanos",
    },
    {
        "name": "Mateo Ruiz",
        "phone": "+573174443322",
        "category": "5ta",
        "client_type": "Socio Diurno (Lebrón)",
        "membership_tier": "LEBRON",
        "gender": "MASCULINO",
        "preferred_music": "Hip Hop / Trap",
        "preferred_play_time": "Mediodía (12pm-3pm)",
        "membership_start_date": date.today() - timedelta(days=32),
        "membership_end_date": date.today() - timedelta(days=2),
        "academy_classes_used": 0,
        "is_minor": False,
        "notes": "Acceso 6:00 AM - 6:00 PM | 20% descuento en torneos americanos (Vencida)",
    },
    {
        "name": "Sofía Martínez",
        "phone": "+573187778899",
        "category": "6ta",
        "client_type": "Estándar",
        "membership_tier": "ESTANDAR",
        "gender": "FEMENINO",
        "preferred_music": "Pop Latino",
        "preferred_play_time": "Fines de semana",
        "membership_start_date": None,
        "membership_end_date": None,
        "academy_classes_used": 0,
        "is_minor": False,
        "notes": "Cliente nueva, primera visita",
    },
    {
        "name": "Lucas Real (Kid)",
        "phone": "+573132058548",
        "category": "6ta",
        "client_type": "Semillero Kids",
        "membership_tier": "ESTANDAR",
        "gender": "MASCULINO",
        "is_minor": True,
        "birth_date": date(2016, 5, 14),
        "guardian_relationship": "HIJO",
        "notes": "Kid Sub-10 apadrinado por Juan Real Florez (Plan Tapia)",
    },
]


async def ensure_initial_customers(db: AsyncSession):
    for c_data in INITIAL_CUSTOMERS_SEED:
        try:
            stmt = select(Customer).where(
                or_(
                    Customer.name == c_data["name"],
                    Customer.phone == c_data["phone"]
                )
            )
            res = await db.execute(stmt)
            existing = res.scalars().first()
            if not existing:
                new_cust = Customer(**c_data)
                db.add(new_cust)
                await db.commit()
            else:
                for k, v in c_data.items():
                    if getattr(existing, k, None) is None and v is not None:
                        setattr(existing, k, v)
                await db.commit()
        except IntegrityError:
            await db.rollback()
        except Exception:
            await db.rollback()

    # Vincular Lucas Real con Juan Real Florez si no tiene guardian_id
    kid_stmt = select(Customer).where(Customer.name.ilike("%Lucas Real%"))
    kid_res = await db.execute(kid_stmt)
    kid = kid_res.scalars().first()
    if kid and not kid.guardian_id:
        guardian_stmt = select(Customer).where(Customer.name.ilike("%Juan Real Florez%"))
        g_res = await db.execute(guardian_stmt)
        guardian = g_res.scalars().first()
        if guardian:
            kid.guardian_id = guardian.id
            kid.guardian_relationship = "HIJO"
            await db.commit()

    # Vincular clientes con sus planes de membresía según membership_tier si membership_plan_id es None
    unlinked_stmt = select(Customer).where(
        Customer.membership_plan_id.is_(None),
        Customer.membership_tier.isnot(None),
        Customer.membership_tier != "ESTANDAR"
    )
    unlinked_res = await db.execute(unlinked_stmt)
    unlinked_custs = unlinked_res.scalars().all()
    if unlinked_custs:
        plans_res = await db.execute(select(MembershipPlan))
        all_plans = plans_res.scalars().all()
        plan_map = {p.name.upper(): p.id for p in all_plans}
        for uc in unlinked_custs:
            tier_key = uc.membership_tier.upper()
            if tier_key in plan_map:
                uc.membership_plan_id = plan_map[tier_key]
        await db.commit()

@router.get("/stats")
async def get_customer_stats(phone: str, db: AsyncSession = Depends(get_db)):
    clean_phone = phone.strip().replace("+", "").replace(" ", "")
    
    query = select(Customer).where(
        or_(
            Customer.phone.ilike(f"%{clean_phone[-10:]}%"),
            Customer.phone.ilike(f"%{clean_phone}%")
        )
    )
    result = await db.execute(query)
    customer = result.scalars().first()

    if not customer:
        return {
            "status": "not_found",
            "name": "Jugador",
            "phone": clean_phone,
            "category": "4ta Categoría",
            "ranking_points": 0,
            "wallet_balance": 0,
            "membership_tier": "ESTANDAR",
            "membership_name": "Estándar (Sin Membresía)",
            "days_left": 0
        }

    days_left = 0
    if customer.membership_end_date:
        today = datetime.utcnow().date()
        end_date = customer.membership_end_date if isinstance(customer.membership_end_date, date) else customer.membership_end_date.date()
        days_left = max(0, (end_date - today).days)

    return {
        "status": "ok",
        "name": customer.name,
        "phone": customer.phone,
        "category": customer.category or "4ta Categoría",
        "ranking_points": customer.ranking_points or 0,
        "wallet_balance": customer.wallet_balance or 0,
        "membership_tier": customer.membership_tier or "ESTANDAR",
        "membership_name": customer.membership_tier or "Estándar (Sin Membresía)",
        "days_left": days_left
    }


def _phone_match_keys(phone: str) -> set:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    keys = {digits, (phone or "").strip()}
    if len(digits) >= 10:
        last10 = digits[-10:]
        keys.update({last10, "57" + last10, "+57" + last10})
    return {k for k in keys if k}


def _slot_includes_phone(players, keys: set) -> bool:
    if not players:
        return False
    items = players if isinstance(players, list) else [players]
    for item in items:
        raw = item.get("phone") if isinstance(item, dict) else item
        raw_str = str(raw or "")
        digits = "".join(c for c in raw_str if c.isdigit())
        if raw_str in keys or digits in keys or (len(digits) >= 10 and digits[-10:] in keys):
            return True
    return False


@router.get("/bookings")
async def get_customer_bookings(phone: str, db: AsyncSession = Depends(get_db)):
    """Lista las reservas activas/futuras del jugador por teléfono (JSON plano)."""
    keys = _phone_match_keys(phone)
    last10 = "".join(c for c in (phone or "") if c.isdigit())[-10:] if phone else ""
    today = get_bogota_today()

    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court))
        .where(
            TimeSlot.date >= today,
            TimeSlot.status.notin_([SlotStatus.CANCELLED, SlotStatus.BLOCKED]),
        )
        .order_by(TimeSlot.date.asc(), TimeSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    slots = list(res.scalars().all())

    bookings = []
    seen_slot_ids = set()
    for slot in slots:
        if not _slot_includes_phone(slot.players_names, keys):
            continue
        seen_slot_ids.add(slot.id)
        court_name = slot.court.name if slot.court else "Cancha"
        participants = slot.players_names if isinstance(slot.players_names, list) else []
        bookings.append({
            "slot_id": slot.id,
            "date": slot.date.isoformat() if slot.date else None,
            "start_time": slot.start_time.strftime("%H:%M") if slot.start_time else None,
            "end_time": slot.end_time.strftime("%H:%M") if slot.end_time else None,
            "court": court_name,
            "sport": (slot.sport_type or "PADEL").upper(),
            "status": str(getattr(slot.status, "value", slot.status) or ""),
            "price_cop": int(slot.total_price or 0),
            "players": len(participants),
            "capacity": slot.capacity or 4,
            "source": "time_slot",
        })

    if last10:
        booking_stmt = (
            select(Booking)
            .options(selectinload(Booking.slot).selectinload(TimeSlot.court))
            .where(
                or_(
                    Booking.customer_phone.ilike(f"%{last10}%"),
                    Booking.customer_phone.ilike(f"%{phone.strip()}%"),
                )
            )
        )
        booking_res = await db.execute(booking_stmt)
        for row in booking_res.scalars().all():
            slot = row.slot
            if not slot or slot.id in seen_slot_ids:
                continue
            if slot.date and slot.date < today:
                continue
            seen_slot_ids.add(slot.id)
            court_name = slot.court.name if slot.court else "Cancha"
            bookings.append({
                "slot_id": slot.id,
                "date": slot.date.isoformat() if slot.date else None,
                "start_time": slot.start_time.strftime("%H:%M") if slot.start_time else None,
                "end_time": slot.end_time.strftime("%H:%M") if slot.end_time else None,
                "court": court_name,
                "sport": (slot.sport_type or "PADEL").upper(),
                "status": str(getattr(slot.status, "value", slot.status) or ""),
                "price_cop": int(row.amount_paid or slot.total_price or 0),
                "players": row.spots_booked or 1,
                "capacity": slot.capacity or 4,
                "source": "booking",
            })

        hold_stmt = (
            select(SlotHold)
            .options(selectinload(SlotHold.slot).selectinload(TimeSlot.court))
            .where(
                SlotHold.status == HoldStatus.ACTIVE,
                or_(
                    SlotHold.customer_phone.ilike(f"%{last10}%"),
                    SlotHold.customer_phone.ilike(f"%{phone.strip()}%"),
                ),
            )
        )
        hold_res = await db.execute(hold_stmt)
        for hold in hold_res.scalars().all():
            slot = hold.slot
            if not slot or slot.id in seen_slot_ids:
                continue
            if slot.date and slot.date < today:
                continue
            seen_slot_ids.add(slot.id)
            court_name = slot.court.name if slot.court else "Cancha"
            bookings.append({
                "slot_id": slot.id,
                "date": slot.date.isoformat() if slot.date else None,
                "start_time": slot.start_time.strftime("%H:%M") if slot.start_time else None,
                "end_time": slot.end_time.strftime("%H:%M") if slot.end_time else None,
                "court": court_name,
                "sport": (slot.sport_type or "PADEL").upper(),
                "status": "HOLD",
                "price_cop": int(hold.amount_to_pay or slot.total_price or 0),
                "players": hold.spots_held or 1,
                "capacity": slot.capacity or 4,
                "source": "hold",
            })

    bookings.sort(key=lambda b: (b.get("date") or "", b.get("start_time") or ""))
    return bookings


@router.get("/search", response_model=List[CustomerResponse])
async def search_customers(
    q: Optional[str] = Query("", description="Texto para buscar por nombre, teléfono o categoría"),
    db: AsyncSession = Depends(get_db),
):
    """Busca clientes para autocompletado en modales de reserva, academia y CRM."""
    await ensure_initial_customers(db)

    term = (q or "").strip().lower()
    if not term:
        stmt = (
            select(Customer)
            .options(selectinload(Customer.guardian), selectinload(Customer.membership_plan))
            .order_by(Customer.name.asc())
            .limit(20)
        )
        res = await db.execute(stmt)
        return [format_customer_response(c) for c in res.scalars().all()]

    pattern = f"%{term}%"
    stmt = (
        select(Customer)
        .options(selectinload(Customer.guardian), selectinload(Customer.membership_plan))
        .where(
            or_(
                Customer.name.ilike(pattern),
                Customer.phone.ilike(pattern),
                Customer.category.ilike(pattern),
                Customer.client_type.ilike(pattern),
                Customer.membership_tier.ilike(pattern),
            )
        )
        .order_by(Customer.name.asc())
        .limit(20)
    )
    res = await db.execute(stmt)
    results = res.scalars().all()
    return [format_customer_response(c) for c in results]


@router.get("", response_model=List[CustomerResponse])
@router.get("/", response_model=List[CustomerResponse])
async def list_all_customers(
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    segment: Optional[str] = Query(None, description="Filtrar por segmento"),
    query: Optional[str] = Query(None, description="Búsqueda libre"),
    db: AsyncSession = Depends(get_db),
):
    """Retorna el listado completo de clientes del club con perfiles enriquecidos y soporte Kids."""
    await ensure_initial_customers(db)
    # Selecciona explícitamente la entidad Customer incluyendo COALESCE(wallet_balance, 0.0) AS wallet_balance
    stmt = select(Customer).options(selectinload(Customer.guardian), selectinload(Customer.membership_plan))

    if category and category.upper() not in ["TODAS", "ALL", ""]:
        stmt = stmt.where(Customer.category.ilike(f"%{category.strip()}%"))

    if segment:
        seg_upper = segment.upper()
        if seg_upper in ["FIRST_VISIT", "NEW"]:
            stmt = stmt.where(Customer.is_first_visit == True)
        elif seg_upper == "HABITUAL":
            stmt = stmt.where(Customer.total_bookings_completed > 0, Customer.is_first_visit == False)
        elif seg_upper in ["KIDS", "MENORES"]:
            stmt = stmt.where(Customer.is_minor == True)
        elif seg_upper in ["RECENT", "RECIENTES"]:
            stmt = stmt.where(Customer.last_booking_date.isnot(None), Customer.last_booking_date >= (date.today() - timedelta(days=7)))
        elif seg_upper in ["VIP", "MEMBER"]:
            stmt = stmt.where(
                or_(
                    Customer.client_type.ilike("%vip%"),
                    Customer.client_type.ilike("%socio%"),
                    Customer.membership_tier.in_(["TAPIA", "COELLO", "GALAN", "CHINGOTTO", "LEBRON"]),
                )
            )

    if query and query.strip():
        term = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(term),
                Customer.phone.ilike(term),
                Customer.category.ilike(term),
                Customer.membership_tier.ilike(term),
                Customer.client_type.ilike(term),
                Customer.preferred_music.ilike(term),
                Customer.preferred_play_time.ilike(term),
            )
        )

    stmt = stmt.order_by(Customer.ranking_points.desc(), Customer.name.asc())
    res = await db.execute(stmt)
    customers = res.scalars().all()
    return [format_customer_response(c) for c in customers]


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
@router.post("/register", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def register_customer(
    payload: CustomerCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Registra un nuevo socio o menor de edad (Kid) en el CRM con su perfil enriquecido."""
    name = payload.name.strip()
    phone = payload.phone.strip() if payload.phone else ""

    # Si es menor de edad y no tiene teléfono, heredar del acudiente si se especificó
    if payload.is_minor and not phone and payload.guardian_id:
        g_stmt = select(Customer).where(Customer.id == payload.guardian_id)
        g_res = await db.execute(g_stmt)
        guardian = g_res.scalar_one_or_none()
        if guardian:
            phone = guardian.phone

    if not name or not phone:
        raise HTTPException(status_code=400, detail="Nombre y teléfono son requeridos.")

    tier = payload.membership_tier.upper() if payload.membership_tier else "ESTANDAR"
    client_type = payload.client_type or ("Semillero Kids" if payload.is_minor else ("Socio VIP" if tier != "ESTANDAR" else "Estándar"))

    # Validar si ya existe un cliente con este teléfono en el club
    phone_stmt = select(Customer).where(Customer.phone == phone)
    phone_res = await db.execute(phone_stmt)
    existing_phone_customer = phone_res.scalars().first()

    stmt = (
        select(Customer)
        .options(selectinload(Customer.guardian))
        .where(Customer.name.ilike(name), Customer.phone == phone)
    )
    res = await db.execute(stmt)
    customer = res.scalar_one_or_none()

    # Si existe el teléfono pero pertenece a otro registro con nombre diferente, bloquear duplicado
    if existing_phone_customer and not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El jugador con este teléfono ya está registrado en el club."
        )

    today = date.today()
    start_date = today if tier != "ESTANDAR" else None
    end_date = today + timedelta(days=30) if tier != "ESTANDAR" else None

    # Buscar plan vinculado si aplica
    plan_id = payload.membership_plan_id
    if not plan_id and tier != "ESTANDAR":
        p_stmt = select(MembershipPlan.id).where(MembershipPlan.name.ilike(tier))
        p_res = await db.execute(p_stmt)
        plan_id = p_res.scalar()

    birth_d = None
    if payload.birth_date:
        try:
            birth_d = datetime.strptime(payload.birth_date.strip(), "%Y-%m-%d").date()
        except Exception:
            pass

    notes = payload.notes.strip() if payload.notes else ""
    if payload.email and payload.email.strip():
        clean_email = payload.email.strip()
        if "Email:" not in notes:
            notes = f"{notes} | Email: {clean_email}".strip(" |")

    try:
        if customer:
            customer.name = name
            customer.category = payload.category or customer.category
            customer.membership_tier = tier
            customer.client_type = client_type
            customer.gender = payload.gender or customer.gender
            customer.preferred_music = payload.preferred_music or customer.preferred_music
            customer.preferred_play_time = payload.preferred_play_time or customer.preferred_play_time
            customer.is_minor = bool(payload.is_minor)
            if birth_d:
                customer.birth_date = birth_d
            if payload.guardian_id is not None:
                customer.guardian_id = payload.guardian_id
            if payload.guardian_relationship is not None:
                customer.guardian_relationship = payload.guardian_relationship.strip()
            if plan_id:
                customer.membership_plan_id = plan_id
            if tier != "ESTANDAR" and not customer.membership_end_date:
                customer.membership_start_date = start_date
                customer.membership_end_date = end_date
            if notes:
                customer.notes = notes
        else:
            customer = Customer(
                name=name,
                phone=phone,
                category=payload.category or "4ta",
                client_type=client_type,
                membership_tier=tier,
                gender=payload.gender or "MASCULINO",
                preferred_music=payload.preferred_music,
                preferred_play_time=payload.preferred_play_time,
                membership_plan_id=plan_id,
                membership_start_date=start_date,
                membership_end_date=end_date,
                academy_classes_used=0,
                is_minor=bool(payload.is_minor),
                birth_date=birth_d,
                guardian_id=payload.guardian_id,
                guardian_relationship=payload.guardian_relationship.strip() if payload.guardian_relationship else None,
                notes=notes if notes else None,
                is_first_visit=True,
                onboarding_status="PENDING",
            )
            db.add(customer)

        await db.commit()
    except IntegrityError as ie:
        await db.rollback()
        err_msg = str(ie).lower()
        if "idx_customers_club_phone" in err_msg or "phone" in err_msg or "unique" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El jugador con este teléfono ya está registrado en el club."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El jugador con este teléfono ya está registrado en el club."
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error guardando jugador en base de datos: {str(e)}"
        )

    # Reconsultar con guardian y membership_plan cargados
    re_stmt = select(Customer).options(selectinload(Customer.guardian), selectinload(Customer.membership_plan)).where(Customer.id == customer.id)
    re_res = await db.execute(re_stmt)
    customer = re_res.scalar_one()

    return format_customer_response(customer)


@router.post("/register-lead", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def register_lead(
    payload: LeadRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Registra un prospecto/lead rápido desde la Landing para autollenado e inscripción en CRM."""
    name = payload.name.strip()
    raw_phone = payload.phone.strip() if payload.phone else ""
    if not name or not raw_phone:
        raise HTTPException(status_code=400, detail="Nombre y teléfono son requeridos.")

    phone = raw_phone
    if phone.isdigit() and len(phone) == 10:
        phone = f"+57{phone}"

    club_info = f"Prospecto Lead ({payload.club_name or 'Web Landing'})"

    stmt = select(Customer).options(selectinload(Customer.guardian), selectinload(Customer.membership_plan)).where(
        or_(Customer.phone == phone, Customer.phone == raw_phone)
    )
    res = await db.execute(stmt)
    existing = res.scalars().first()

    if existing:
        existing.name = name
        existing.category = payload.category or existing.category
        if existing.notes:
            existing.notes = f"{existing.notes} | {club_info}"
        else:
            existing.notes = club_info
        await db.commit()
        re_stmt = select(Customer).options(selectinload(Customer.guardian), selectinload(Customer.membership_plan)).where(Customer.id == existing.id)
        re_res = await db.execute(re_stmt)
        return format_customer_response(re_res.scalar_one())

    new_customer = Customer(
        name=name,
        phone=phone,
        category=payload.category or "4ta",
        client_type="Prospecto Lead",
        membership_tier="ESTANDAR",
        notes=club_info,
        is_first_visit=True,
        onboarding_status="PENDING",
    )
    db.add(new_customer)
    await db.commit()

    re_stmt = select(Customer).options(selectinload(Customer.guardian), selectinload(Customer.membership_plan)).where(Customer.id == new_customer.id)
    re_res = await db.execute(re_stmt)
    return format_customer_response(re_res.scalar_one())


@router.post("/bot-register", response_model=BotRegisterResponse, status_code=status.HTTP_200_OK)
async def bot_register_customer(
    payload: BotRegisterCustomerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint para bots conversacionales (Voiceflow/WhatsApp) para registrar jugadores en el CRM.
    - Si el jugador ya existe por teléfono, devuelve HTTP 200 con mensaje informativo para no romper el flujo conversacional.
    - Si no existe, lo inserta en Supabase con valores por defecto seguros ('Estándar', '4ta' o category_level provisto).
    """
    raw_phone = (payload.phone or "").strip()
    name = (payload.name or "").strip()

    if not name or not raw_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nombre y teléfono son obligatorios para el registro."
        )

    # Limpieza y normalización básica de teléfono
    phone = raw_phone
    clean_digits = "".join(filter(str.isdigit, phone))
    if len(clean_digits) == 10 and not phone.startswith("+"):
        phone = f"+57{clean_digits}"

    # 1. Buscar si ya existe el jugador por teléfono
    check_stmt = select(Customer).where(
        or_(
            Customer.phone == phone,
            Customer.phone == raw_phone,
            Customer.phone.endswith(clean_digits[-10:]) if len(clean_digits) >= 10 else False
        )
    )
    res = await db.execute(check_stmt)
    existing_customer = res.scalars().first()

    if existing_customer:
        # Actualizar opcionalmente email si no lo tenía y vino en el payload
        if payload.email and payload.email.strip():
            em = payload.email.strip()
            current_notes = existing_customer.notes or ""
            if "Email:" not in current_notes:
                existing_customer.notes = f"{current_notes} | Email: {em}".strip(" |")
                await db.commit()

        return BotRegisterResponse(
            status="success",
            message="El usuario ya existe",
            data={
                "id": existing_customer.id,
                "name": existing_customer.name,
                "phone": existing_customer.phone,
                "category": existing_customer.category,
                "client_type": existing_customer.client_type,
                "membership_tier": existing_customer.membership_tier,
                "email": getattr(existing_customer, "email", None) or (
                    existing_customer.notes.split("Email:")[1].split("|")[0].strip()
                    if existing_customer.notes and "Email:" in existing_customer.notes
                    else payload.email
                ),
            }
        )

    # 2. Si no existe, crear nuevo jugador con valores por defecto
    category = (payload.category_level or "4ta").strip()
    notes_list = ["Registrado vía Bot Onboarding (Voiceflow)"]
    if payload.email and payload.email.strip():
        notes_list.append(f"Email: {payload.email.strip()}")
    notes = " | ".join(notes_list)

    new_cust = Customer(
        name=name,
        phone=phone,
        category=category,
        client_type="Estándar",
        membership_tier="ESTANDAR",
        notes=notes,
        is_first_visit=True,
        onboarding_status="WELCOMED",
        wallet_balance=0.0,
        total_bookings_completed=0,
    )

    try:
        db.add(new_cust)
        await db.commit()
        await db.refresh(new_cust)
    except IntegrityError:
        await db.rollback()
        # En caso de concurrencia donde se insertó justo antes
        stmt_retry = select(Customer).where(Customer.phone == phone)
        res_retry = await db.execute(stmt_retry)
        found = res_retry.scalars().first()
        if found:
            return BotRegisterResponse(
                status="success",
                message="El usuario ya existe",
                data={
                    "id": found.id,
                    "name": found.name,
                    "phone": found.phone,
                    "category": found.category,
                    "client_type": found.client_type,
                    "membership_tier": found.membership_tier,
                    "email": payload.email,
                }
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error de integridad al registrar el cliente."
        )

    return BotRegisterResponse(
        status="success",
        message="Jugador registrado",
        data={
            "id": new_cust.id,
            "name": new_cust.name,
            "phone": new_cust.phone,
            "category": new_cust.category,
            "client_type": new_cust.client_type,
            "membership_tier": new_cust.membership_tier,
            "email": payload.email,
        }
    )


@router.put("/{player_id}", response_model=CustomerResponse)
async def update_customer_profile(
    player_id: int,
    payload: CustomerUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza la información y perfil de cualquier socio o menor en el CRM."""
    stmt = select(Customer).options(selectinload(Customer.guardian), selectinload(Customer.membership_plan)).where(Customer.id == player_id)
    res = await db.execute(stmt)
    customer = res.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Socio no encontrado")

    if payload.name is not None:
        customer.name = payload.name.strip()
    if payload.phone is not None:
        new_phone = payload.phone.strip()
        if new_phone != customer.phone:
            chk_phone_stmt = select(Customer).where(Customer.phone == new_phone, Customer.id != player_id)
            chk_res = await db.execute(chk_phone_stmt)
            if chk_res.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El jugador con este teléfono ya está registrado en el club."
                )
        customer.phone = new_phone
    if payload.category is not None:
        customer.category = payload.category.strip()
    if payload.client_type is not None:
        customer.client_type = payload.client_type.strip()
    if payload.membership_tier is not None:
        customer.membership_tier = payload.membership_tier.strip().upper()
    if payload.gender is not None:
        customer.gender = payload.gender.strip()
    if payload.preferred_music is not None:
        customer.preferred_music = payload.preferred_music.strip()
    if payload.preferred_play_time is not None:
        customer.preferred_play_time = payload.preferred_play_time.strip()
    if payload.notes is not None:
        customer.notes = payload.notes.strip()
    if payload.email is not None and payload.email.strip():
        clean_email = payload.email.strip()
        curr_notes = customer.notes or ""
        if "Email:" not in curr_notes:
            customer.notes = f"{curr_notes} | Email: {clean_email}".strip(" |")

    if payload.membership_plan_id is not None:
        customer.membership_plan_id = payload.membership_plan_id
    if payload.academy_classes_used is not None:
        customer.academy_classes_used = payload.academy_classes_used
    if payload.is_minor is not None:
        customer.is_minor = bool(payload.is_minor)
    if payload.birth_date is not None:
        try:
            customer.birth_date = datetime.strptime(payload.birth_date.strip(), "%Y-%m-%d").date()
        except Exception:
            pass
    if payload.guardian_id is not None:
        customer.guardian_id = payload.guardian_id
    if payload.guardian_relationship is not None:
        customer.guardian_relationship = payload.guardian_relationship.strip()

    if payload.membership_start_date:
        try:
            customer.membership_start_date = datetime.strptime(payload.membership_start_date.strip(), "%Y-%m-%d").date()
        except Exception:
            pass

    if payload.membership_end_date:
        try:
            customer.membership_end_date = datetime.strptime(payload.membership_end_date.strip(), "%Y-%m-%d").date()
        except Exception:
            pass

    try:
        await db.commit()
    except IntegrityError as ie:
        await db.rollback()
        err_msg = str(ie).lower()
        if "idx_customers_club_phone" in err_msg or "phone" in err_msg or "unique" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El jugador con este teléfono ya está registrado en el club."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El jugador con este teléfono ya está registrado en el club."
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error actualizando jugador en base de datos: {str(e)}"
        )

    re_stmt = select(Customer).options(selectinload(Customer.guardian), selectinload(Customer.membership_plan)).where(Customer.id == customer.id)
    re_res = await db.execute(re_stmt)
    customer = re_res.scalar_one()

    return format_customer_response(customer)


@router.post("/{customer_id}/onboarding", response_model=CustomerResponse)
async def update_customer_onboarding(
    customer_id: int,
    payload: CustomerOnboardingRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Customer).options(selectinload(Customer.guardian)).where(Customer.id == customer_id)
    res = await db.execute(stmt)
    customer = res.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    customer.onboarding_status = payload.onboarding_status.upper()
    if payload.notes:
        if customer.notes:
            customer.notes = f"{customer.notes} | {payload.notes.strip()}"
        else:
            customer.notes = payload.notes.strip()

    await db.commit()
    await db.refresh(customer)
    return format_customer_response(customer)


@router.post("/{customer_id}/promote", response_model=CustomerResponse)
async def promote_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
):
    from app.services.ranking_engine import promote_customer_category
    try:
        updated = await promote_customer_category(db, customer_id)
        return format_customer_response(updated)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))





@router.post("/{customer_id}/upload-avatar")
async def upload_customer_avatar(
    customer_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Sube y almacena la foto de perfil del jugador en Supabase Storage Bucket o carpeta estática local."""
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de imagen inválido. Solo se admiten JPG, PNG o WebP.",
        )

    ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    ext = ext_map.get(content_type, "jpg")
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe adjuntar un archivo de imagen válido.",
        )

    res = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = res.scalars().first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente con ID {customer_id} no encontrado.",
        )

    file_bytes = await file.read()
    filename = f"avatar_{customer_id}_{int(time.time())}.{ext}"

    # 1. Intentar subir a Supabase Storage Bucket si hay credenciales configuradas
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

    avatar_url = None
    if supabase_url and supabase_key:
        try:
            import httpx
            storage_url = f"{supabase_url.rstrip('/')}/storage/v1/object/avatars/{filename}"
            headers = {
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key,
                "Content-Type": content_type or "image/jpeg",
                "x-upsert": "true"
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                supa_res = await client.post(storage_url, content=file_bytes, headers=headers)
                if supa_res.status_code in [200, 201]:
                    avatar_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/avatars/{filename}"
        except Exception:
            avatar_url = None

    # 2. Fallback persistente a almacenamiento estático local
    if not avatar_url:
        target_dir = os.path.join("app", "static", "uploads", "avatars")
        os.makedirs(target_dir, exist_ok=True)
        file_path = os.path.normpath(os.path.join(target_dir, filename))
        with open(file_path, "wb") as buffer:
            buffer.write(file_bytes)
        avatar_url = f"/static/uploads/avatars/{filename}"

    customer.avatar_url = avatar_url
    await db.commit()
    await db.refresh(customer)

    return {
        "status": "ok",
        "avatar_url": avatar_url,
        "message": "Foto actualizada correctamente",
    }


