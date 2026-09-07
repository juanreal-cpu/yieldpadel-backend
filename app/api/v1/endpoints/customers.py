from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.customer import Customer

router = APIRouter()


class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    category: str
    client_type: str
    notes: Optional[str] = None
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


class CustomerOnboardingRequest(BaseModel):
    onboarding_status: str = "WELCOMED"  # PENDING, WELCOMED, MEMBER_OFFERED
    notes: Optional[str] = None


INITIAL_CUSTOMERS_SEED = [
    {
        "name": "Juan Real Florez",
        "phone": "+573132058547",
        "category": "4ta",
        "client_type": "Socio VIP",
        "notes": "Cliente fundador, exento de hold",
    },
    {
        "name": "Camilo Real",
        "phone": "+573001234567",
        "category": "4ta",
        "client_type": "Estándar",
        "notes": "Jugador habitual de semana",
    },
    {
        "name": "David P",
        "phone": "+573109876543",
        "category": "3ra",
        "client_type": "Estándar",
        "notes": "Categoría 3ra avanzada",
    },
]


async def ensure_initial_customers(db: AsyncSession):
    """Garantiza la existencia de la base de clientes inicial en la base de datos."""
    for c_data in INITIAL_CUSTOMERS_SEED:
        stmt = select(Customer).where(Customer.phone == c_data["phone"])
        res = await db.execute(stmt)
        existing = res.scalars().first()
        if not existing:
            new_cust = Customer(**c_data)
            db.add(new_cust)
    await db.commit()


@router.get("/search", response_model=List[CustomerResponse])
async def search_customers(
    q: Optional[str] = Query("", description="Texto para buscar por nombre, teléfono o categoría"),
    db: AsyncSession = Depends(get_db),
):
    """
    Busca clientes para autocompletado en modales de reserva y CRM.
    Si la tabla está vacía, asegura el seed inicial.
    """
    await ensure_initial_customers(db)

    term = (q or "").strip().lower()
    if not term:
        stmt = select(Customer).order_by(Customer.name.asc()).limit(20)
        res = await db.execute(stmt)
        return res.scalars().all()

    pattern = f"%{term}%"
    stmt = (
        select(Customer)
        .where(
            or_(
                Customer.name.ilike(pattern),
                Customer.phone.ilike(pattern),
                Customer.category.ilike(pattern),
                Customer.client_type.ilike(pattern),
            )
        )
        .order_by(Customer.name.asc())
        .limit(20)
    )
    res = await db.execute(stmt)
    results = res.scalars().all()

    # Si por alguna razón la BD falló, hacer fallback al seed en memoria
    if not results:
        fallback_matches = []
        for c in INITIAL_CUSTOMERS_SEED:
            if (
                term in c["name"].lower()
                or term in c["phone"].lower()
                or term in c["category"].lower()
                or term in c["client_type"].lower()
            ):
                fallback_matches.append(CustomerResponse(id=len(fallback_matches) + 1, **c))
        return fallback_matches

    return results


@router.get("/", response_model=List[CustomerResponse])
async def list_all_customers(
    category: Optional[str] = Query(None, description="Filtrar por categoría (ej: '4ta', '3ra')"),
    segment: Optional[str] = Query(None, description="Filtrar por segmento ('ALL', 'FIRST_VISIT', 'HABITUAL', 'VIP')"),
    db: AsyncSession = Depends(get_db),
):
    """Retorna el listado completo de clientes del club, con soporte de filtro por categoría y segmento."""
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
                )
            )

    stmt = stmt.order_by(Customer.ranking_points.desc(), Customer.name.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/{customer_id}/onboarding", response_model=CustomerResponse)
async def update_customer_onboarding(
    customer_id: int,
    payload: CustomerOnboardingRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Actualiza el estado de onboarding y bienvenida de un cliente en recepción.
    Opciones: 'WELCOMED', 'MEMBER_OFFERED', 'PENDING'.
    """
    stmt = select(Customer).where(Customer.id == customer_id)
    res = await db.execute(stmt)
    customer = res.scalar_one_or_none()
    if not customer:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    customer.onboarding_status = payload.onboarding_status.upper()
    if payload.notes:
        if customer.notes:
            customer.notes = f"{customer.notes} | {payload.notes.strip()}"
        else:
            customer.notes = payload.notes.strip()

    await db.commit()
    await db.refresh(customer)
    return customer


@router.post("/{customer_id}/promote", response_model=CustomerResponse)
async def promote_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Aprueba la recomendación de ascenso de un jugador a la siguiente categoría.
    Actualiza la categoría formal y resetea las victorias consecutivas.
    """
    from app.services.ranking_engine import promote_customer_category
    try:
        updated = await promote_customer_category(db, customer_id)
        return updated
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(e))

