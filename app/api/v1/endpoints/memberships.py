from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.membership import MembershipPlan
from app.models.customer import Customer

router = APIRouter()


class MembershipPlanResponse(BaseModel):
    id: int
    name: str
    start_time: str
    end_time: str
    max_daily_hours: float
    includes_academy_classes: bool
    monthly_classes_count: int
    includes_beverage_perk: bool
    americano_discount_pct: int
    monthly_price_cop: int
    active_members_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class MembershipPlanCreateUpdateRequest(BaseModel):
    name: str
    start_time: str = "06:00:00"
    end_time: str = "23:59:00"
    max_daily_hours: float = 1.5
    includes_academy_classes: bool = False
    monthly_classes_count: int = 0
    includes_beverage_perk: bool = False
    americano_discount_pct: int = 0
    monthly_price_cop: int = 0


class AssignMembershipRequest(BaseModel):
    customer_id: int
    plan_id: Optional[int] = None
    membership_tier: Optional[str] = None
    validity_days: int = 30


DEFAULT_PLANS_DATA = [
    {
        "name": "Tapia",
        "start_time": time(6, 0),
        "end_time": time(23, 59),
        "max_daily_hours": 1.5,
        "includes_academy_classes": True,
        "monthly_classes_count": 4,
        "includes_beverage_perk": True,
        "americano_discount_pct": 40,
        "monthly_price_cop": 350000,
    },
    {
        "name": "Coello",
        "start_time": time(6, 0),
        "end_time": time(23, 59),
        "max_daily_hours": 1.5,
        "includes_academy_classes": True,
        "monthly_classes_count": 2,
        "includes_beverage_perk": True,
        "americano_discount_pct": 30,
        "monthly_price_cop": 280000,
    },
    {
        "name": "Galán",
        "start_time": time(6, 0),
        "end_time": time(23, 59),
        "max_daily_hours": 1.5,
        "includes_academy_classes": False,
        "monthly_classes_count": 0,
        "includes_beverage_perk": True,
        "americano_discount_pct": 20,
        "monthly_price_cop": 220000,
    },
    {
        "name": "Chingotto",
        "start_time": time(6, 0),
        "end_time": time(15, 0),
        "max_daily_hours": 1.5,
        "includes_academy_classes": False,
        "monthly_classes_count": 0,
        "includes_beverage_perk": False,
        "americano_discount_pct": 10,
        "monthly_price_cop": 150000,
    },
    {
        "name": "Lebrón",
        "start_time": time(6, 0),
        "end_time": time(18, 0),
        "max_daily_hours": 1.5,
        "includes_academy_classes": False,
        "monthly_classes_count": 0,
        "includes_beverage_perk": False,
        "americano_discount_pct": 20,
        "monthly_price_cop": 180000,
    },
]


async def ensure_default_membership_plans(db: AsyncSession):
    stmt = select(MembershipPlan)
    res = await db.execute(stmt)
    existing = res.scalars().all()
    if not existing:
        for p_data in DEFAULT_PLANS_DATA:
            plan = MembershipPlan(**p_data)
            db.add(plan)
        await db.commit()


@router.get("", response_model=List[MembershipPlanResponse])
@router.get("/", response_model=List[MembershipPlanResponse])
async def list_membership_plans(db: AsyncSession = Depends(get_db)):
    """Lista todos los planes de membresía configurados con su conteo de socios activos."""
    await ensure_default_membership_plans(db)

    stmt = select(MembershipPlan).order_by(MembershipPlan.monthly_price_cop.desc())
    res = await db.execute(stmt)
    plans = res.scalars().all()

    today = date.today()
    response_list = []
    for plan in plans:
        # Contar socios activos suscritos
        norm_name = plan.name.upper()
        count_stmt = select(func.count(Customer.id)).where(
            or_(
                Customer.membership_plan_id == plan.id,
                Customer.membership_tier == norm_name,
                Customer.membership_tier.ilike(f"%{norm_name}%"),
            )
        )
        count_res = await db.execute(count_stmt)
        active_count = count_res.scalar() or 0

        response_list.append(
            MembershipPlanResponse(
                id=plan.id,
                name=plan.name,
                start_time=plan.start_time.strftime("%H:%M:%S") if plan.start_time else "06:00:00",
                end_time=plan.end_time.strftime("%H:%M:%S") if plan.end_time else "23:59:00",
                max_daily_hours=plan.max_daily_hours,
                includes_academy_classes=plan.includes_academy_classes,
                monthly_classes_count=plan.monthly_classes_count,
                includes_beverage_perk=plan.includes_beverage_perk,
                americano_discount_pct=plan.americano_discount_pct,
                monthly_price_cop=plan.monthly_price_cop,
                active_members_count=active_count,
            )
        )

    return response_list


@router.post("", response_model=MembershipPlanResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=MembershipPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_membership_plan(
    payload: MembershipPlanCreateUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Crea o actualiza los parámetros de un plan de membresía."""
    stmt = select(MembershipPlan).where(MembershipPlan.name.ilike(payload.name.strip()))
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    def parse_time(t_str: str) -> time:
        try:
            parts = t_str.split(":")
            return time(int(parts[0]), int(parts[1]))
        except Exception:
            return time(6, 0)

    start_t = parse_time(payload.start_time)
    end_t = parse_time(payload.end_time)

    if plan:
        plan.start_time = start_t
        plan.end_time = end_t
        plan.max_daily_hours = payload.max_daily_hours
        plan.includes_academy_classes = payload.includes_academy_classes
        plan.monthly_classes_count = payload.monthly_classes_count
        plan.includes_beverage_perk = payload.includes_beverage_perk
        plan.americano_discount_pct = payload.americano_discount_pct
        plan.monthly_price_cop = payload.monthly_price_cop
    else:
        plan = MembershipPlan(
            name=payload.name.strip(),
            start_time=start_t,
            end_time=end_t,
            max_daily_hours=payload.max_daily_hours,
            includes_academy_classes=payload.includes_academy_classes,
            monthly_classes_count=payload.monthly_classes_count,
            includes_beverage_perk=payload.includes_beverage_perk,
            americano_discount_pct=payload.americano_discount_pct,
            monthly_price_cop=payload.monthly_price_cop,
        )
        db.add(plan)

    await db.commit()
    await db.refresh(plan)

    return MembershipPlanResponse(
        id=plan.id,
        name=plan.name,
        start_time=plan.start_time.strftime("%H:%M:%S"),
        end_time=plan.end_time.strftime("%H:%M:%S"),
        max_daily_hours=plan.max_daily_hours,
        includes_academy_classes=plan.includes_academy_classes,
        monthly_classes_count=plan.monthly_classes_count,
        includes_beverage_perk=plan.includes_beverage_perk,
        americano_discount_pct=plan.americano_discount_pct,
        monthly_price_cop=plan.monthly_price_cop,
        active_members_count=0,
    )


@router.post("/assign")
async def assign_membership_to_customer(
    payload: AssignMembershipRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Asigna un plan de membresía a un cliente fijando 30 días de vigencia (membership_end_date = hoy + 30 días).
    """
    await ensure_default_membership_plans(db)

    cust_stmt = select(Customer).where(Customer.id == payload.customer_id)
    cust_res = await db.execute(cust_stmt)
    customer = cust_res.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    plan = None
    if payload.plan_id:
        plan_stmt = select(MembershipPlan).where(MembershipPlan.id == payload.plan_id)
        plan_res = await db.execute(plan_stmt)
        plan = plan_res.scalar_one_or_none()

    if not plan and payload.membership_tier:
        tier_clean = payload.membership_tier.strip().upper()
        plan_stmt = select(MembershipPlan).where(MembershipPlan.name.ilike(tier_clean))
        plan_res = await db.execute(plan_stmt)
        plan = plan_res.scalar_one_or_none()

    if not plan:
        # Fallback a Tapia si no se especificó o no se encontró
        plan_stmt = select(MembershipPlan).order_by(MembershipPlan.id.asc()).limit(1)
        plan_res = await db.execute(plan_stmt)
        plan = plan_res.scalar_one_or_none()

    today = date.today()
    validity_days = payload.validity_days if payload.validity_days > 0 else 30

    customer.membership_plan_id = plan.id if plan else None
    customer.membership_tier = plan.name.upper() if plan else "ESTANDAR"
    customer.client_type = f"Socio VIP ({plan.name})" if plan else "Estándar"
    customer.membership_start_date = today
    customer.membership_end_date = today + timedelta(days=validity_days)
    customer.academy_classes_used = 0

    await db.commit()
    await db.refresh(customer)

    return {
        "status": "success",
        "message": f"Membresía {customer.membership_tier} asignada con éxito a {customer.name}",
        "customer_id": customer.id,
        "customer_name": customer.name,
        "membership_tier": customer.membership_tier,
        "start_date": customer.membership_start_date.isoformat(),
        "end_date": customer.membership_end_date.isoformat(),
        "days_remaining": validity_days,
        "plan_id": plan.id if plan else None,
    }
