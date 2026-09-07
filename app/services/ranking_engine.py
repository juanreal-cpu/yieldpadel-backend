import logging
from typing import List, Optional, Tuple
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer

logger = logging.getLogger("yieldpadel.ranking")

CATEGORIES_ORDER = ["6ta", "5ta", "4ta", "3ra", "2da", "1ra"]


def get_next_category(current_cat: Optional[str]) -> str:
    """Calcula la categoría superior inmediata según la escala canónica."""
    if not current_cat:
        return "5ta"
    c_norm = current_cat.strip().lower()
    for idx, cat in enumerate(CATEGORIES_ORDER):
        if cat in c_norm:
            if idx + 1 < len(CATEGORIES_ORDER):
                return CATEGORIES_ORDER[idx + 1]
            return CATEGORIES_ORDER[-1]
    return "3ra"


async def find_or_create_player_by_name_or_phone(
    db: AsyncSession, name: str, phone: Optional[str] = None
) -> Customer:
    """Encuentra un jugador existente o crea uno nuevo en la base de datos."""
    clean_name = name.strip()
    stmt = select(Customer).where(Customer.name.ilike(f"%{clean_name}%"))
    if phone:
        clean_phone = phone.strip()
        stmt = select(Customer).where(
            or_(Customer.phone == clean_phone, Customer.name.ilike(f"%{clean_name}%"))
        )

    res = await db.execute(stmt)
    customer = res.scalars().first()

    if not customer:
        cust_phone = phone.strip() if phone else f"+57-WA-{clean_name.lower().replace(' ', '')}"
        customer = Customer(
            name=clean_name,
            phone=cust_phone,
            category="4ta",
            client_type="Estándar",
            ranking_points=0,
            titles_count=0,
            category_wins=0,
            consecutive_wins=0,
            promotion_recommended=False,
        )
        db.add(customer)
        await db.flush()

    return customer


async def award_tournament_points(
    db: AsyncSession,
    winner_names: List[str],
    winner_phones: Optional[List[str]] = None,
    runner_up_names: Optional[List[str]] = None,
    runner_up_phones: Optional[List[str]] = None,
) -> Tuple[List[Customer], List[Customer]]:
    """
    Otorga puntos de ranking, actualiza títulos y evalúa la regla de ascenso automático.
    - Campeones: +100 puntos, titles_count += 1, category_wins += 1, consecutive_wins += 1.
      Si consecutive_wins >= 2 -> promotion_recommended = True, recommended_category = next_cat.
    - Subcampeones: +50 puntos.
    """
    champions: List[Customer] = []
    runners_up: List[Customer] = []

    # 1. Procesar Campeones
    for idx, name in enumerate(winner_names):
        if not name or not name.strip():
            continue
        phone = winner_phones[idx] if winner_phones and idx < len(winner_phones) else None
        player = await find_or_create_player_by_name_or_phone(db, name, phone)

        player.ranking_points += 100
        player.titles_count += 1
        player.category_wins += 1
        player.consecutive_wins += 1

        if player.consecutive_wins >= 2:
            player.promotion_recommended = True
            player.recommended_category = get_next_category(player.category)

        champions.append(player)

    # 2. Procesar Subcampeones
    if runner_up_names:
        for idx, name in enumerate(runner_up_names):
            if not name or not name.strip():
                continue
            phone = runner_up_phones[idx] if runner_up_phones and idx < len(runner_up_phones) else None
            player = await find_or_create_player_by_name_or_phone(db, name, phone)

            player.ranking_points += 50
            runners_up.append(player)

    await db.commit()
    for p in champions + runners_up:
        await db.refresh(p)

    return champions, runners_up


async def promote_customer_category(db: AsyncSession, customer_id: int) -> Customer:
    """Ejecuta y aprueba el ascenso formal de un jugador a la siguiente categoría."""
    stmt = select(Customer).where(Customer.id == customer_id)
    res = await db.execute(stmt)
    customer = res.scalar_one_or_none()

    if not customer:
        raise ValueError(f"Jugador con id {customer_id} no encontrado")

    if not customer.recommended_category:
        customer.recommended_category = get_next_category(customer.category)

    customer.category = customer.recommended_category
    customer.consecutive_wins = 0
    customer.category_wins = 0
    customer.promotion_recommended = False
    customer.recommended_category = None

    await db.commit()
    await db.refresh(customer)
    return customer
