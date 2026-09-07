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

    model_config = ConfigDict(from_attributes=True)


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
    db: AsyncSession = Depends(get_db),
):
    """Retorna el listado completo de clientes del club."""
    await ensure_initial_customers(db)
    stmt = select(Customer).order_by(Customer.name.asc())
    res = await db.execute(stmt)
    return res.scalars().all()
