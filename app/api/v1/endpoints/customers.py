from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.customer import Customer
from app.models.membership import MembershipPlan

router = APIRouter()


class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    category: str
    client_type: str
    membership_tier: str = "ESTANDAR"
    notes: Optional[str] = None
    gender: Optional[str] = None
    preferred_music: Optional[str] = None
    preferred_play_time: Optional[str] = None
    membership_plan_id: Optional[int] = None
    membership_start_date: Optional[str] = None
    membership_end_date: Optional[str] = None
    days_remaining: int = 0
    academy_classes_used: int = 0
    total_bookings_completed: int = 0
    is_first_visit: bool = True
    onboarding_status: str = "PENDING"
    ranking_points: int = 0
    titles_count: int = 0
    category_wins: int = 0
    consecutive_wins: int = 0
    promotion_recommended: bool = False
    recommended_category: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CustomerCreateRequest(BaseModel):
    name: str
    phone: str
    category: str = "4ta"
    client_type: Optional[str] = None
    membership_tier: str = "ESTANDAR"
    gender: Optional[str] = "MASCULINO"
    preferred_music: Optional[str] = None
    preferred_play_time: Optional[str] = None
    notes: Optional[str] = None
    membership_plan_id: Optional[int] = None


class CustomerUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
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


class CustomerOnboardingRequest(BaseModel):
    onboarding_status: str = "WELCOMED"  # PENDING, WELCOMED, MEMBER_OFFERED
    notes: Optional[str] = None


def format_customer_response(c: Customer) -> CustomerResponse:
    today = date.today()
    days_rem = 0
    if c.membership_end_date:
        days_rem = (c.membership_end_date - today).days

    return CustomerResponse(
        id=c.id,
        name=c.name,
        phone=c.phone,
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
        "notes": "Cliente nueva, primera visita",
    },
]


async def ensure_initial_customers(db: AsyncSession):
    for c_data in INITIAL_CUSTOMERS_SEED:
        stmt = select(Customer).where(Customer.phone == c_data["phone"])
        res = await db.execute(stmt)
        existing = res.scalars().first()
        if not existing:
            new_cust = Customer(**c_data)
            db.add(new_cust)
        else:
            # Enriquecer datos existentes si faltan campos
            for k, v in c_data.items():
                if getattr(existing, k, None) is None and v is not None:
                    setattr(existing, k, v)
    await db.commit()


@router.get("/search", response_model=List[CustomerResponse])
async def search_customers(
    q: Optional[str] = Query("", description="Texto para buscar por nombre, teléfono o categoría"),
    db: AsyncSession = Depends(get_db),
):
    """Busca clientes para autocompletado en modales de reserva, academia y CRM."""
    await ensure_initial_customers(db)

    term = (q or "").strip().lower()
    if not term:
        stmt = select(Customer).order_by(Customer.name.asc()).limit(20)
        res = await db.execute(stmt)
        return [format_customer_response(c) for c in res.scalars().all()]

    pattern = f"%{term}%"
    stmt = (
        select(Customer)
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
    """Retorna el listado completo de clientes del club con perfiles enriquecidos."""
    await ensure_initial_customers(db)
    stmt = select(Customer)

    if category and category.upper() not in ["TODAS", "ALL", ""]:
        stmt = stmt.where(Customer.category.ilike(f"%{category.strip()}%"))

    if segment:
        seg_upper = segment.upper()
        if seg_upper in ["FIRST_VISIT", "NEW"]:
            stmt = stmt.where(Customer.is_first_visit == True)
        elif seg_upper == "HABITUAL":
            stmt = stmt.where(Customer.total_bookings_completed > 0, Customer.is_first_visit == False)
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
    """Registra un nuevo socio/jugador en el CRM con su perfil integral enriquecido."""
    phone = payload.phone.strip()
    name = payload.name.strip()
    if not name or not phone:
        raise HTTPException(status_code=400, detail="Nombre y teléfono son requeridos.")

    tier = payload.membership_tier.upper() if payload.membership_tier else "ESTANDAR"
    client_type = payload.client_type or ("Socio VIP" if tier != "ESTANDAR" else "Estándar")

    stmt = select(Customer).where(Customer.phone == phone)
    res = await db.execute(stmt)
    customer = res.scalar_one_or_none()

    today = date.today()
    start_date = today if tier != "ESTANDAR" else None
    end_date = today + timedelta(days=30) if tier != "ESTANDAR" else None

    # Buscar plan vinculado si aplica
    plan_id = payload.membership_plan_id
    if not plan_id and tier != "ESTANDAR":
        p_stmt = select(MembershipPlan.id).where(MembershipPlan.name.ilike(tier))
        p_res = await db.execute(p_stmt)
        plan_id = p_res.scalar()

    if customer:
        customer.name = name
        customer.category = payload.category or customer.category
        customer.membership_tier = tier
        customer.client_type = client_type
        customer.gender = payload.gender or customer.gender
        customer.preferred_music = payload.preferred_music or customer.preferred_music
        customer.preferred_play_time = payload.preferred_play_time or customer.preferred_play_time
        if plan_id:
            customer.membership_plan_id = plan_id
        if tier != "ESTANDAR" and not customer.membership_end_date:
            customer.membership_start_date = start_date
            customer.membership_end_date = end_date
        if payload.notes:
            customer.notes = payload.notes.strip()
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
            notes=payload.notes.strip() if payload.notes else None,
            is_first_visit=True,
            onboarding_status="PENDING",
        )
        db.add(customer)

    await db.commit()
    await db.refresh(customer)
    return format_customer_response(customer)


@router.put("/{player_id}", response_model=CustomerResponse)
async def update_customer_profile(
    player_id: int,
    payload: CustomerUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza la información y perfil de cualquier socio existente en el CRM."""
    stmt = select(Customer).where(Customer.id == player_id)
    res = await db.execute(stmt)
    customer = res.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Socio no encontrado")

    if payload.name is not None:
        customer.name = payload.name.strip()
    if payload.phone is not None:
        customer.phone = payload.phone.strip()
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
    if payload.membership_plan_id is not None:
        customer.membership_plan_id = payload.membership_plan_id
    if payload.academy_classes_used is not None:
        customer.academy_classes_used = payload.academy_classes_used

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

    await db.commit()
    await db.refresh(customer)
    return format_customer_response(customer)


@router.post("/{customer_id}/onboarding", response_model=CustomerResponse)
async def update_customer_onboarding(
    customer_id: int,
    payload: CustomerOnboardingRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Customer).where(Customer.id == customer_id)
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
