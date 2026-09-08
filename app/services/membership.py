from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import MembershipPlan
from app.models.customer import Customer


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
        "badge_label": "VIP PLATINUM",
        "card_gradient": "from-amber-600 to-yellow-700",
        "is_active": True,
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
        "badge_label": "ALL ACCESS",
        "card_gradient": "from-indigo-600 to-purple-700",
        "is_active": True,
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
        "badge_label": "PRIME PLAY",
        "card_gradient": "from-blue-600 to-indigo-600",
        "is_active": True,
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
        "badge_label": "OFF-PEAK MORNING",
        "card_gradient": "from-emerald-600 to-teal-700",
        "is_active": True,
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
        "badge_label": "DAYTIME PRO",
        "card_gradient": "from-slate-700 to-slate-900",
        "is_active": True,
    },
]


def parse_time_str(t_str: str) -> time:
    if isinstance(t_str, time):
        return t_str
    try:
        parts = str(t_str).strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return time(6, 0)


async def ensure_default_membership_plans(db: AsyncSession):
    stmt = select(MembershipPlan)
    res = await db.execute(stmt)
    existing = res.scalars().all()
    if not existing:
        for p_data in DEFAULT_PLANS_DATA:
            plan = MembershipPlan(**p_data)
            db.add(plan)
        await db.commit()
    else:
        # Enriquecer badges y degradados si están vacíos
        palette = {
            "TAPIA": ("VIP PLATINUM", "from-amber-600 to-yellow-700"),
            "COELLO": ("ALL ACCESS", "from-indigo-600 to-purple-700"),
            "GALÁN": ("PRIME PLAY", "from-blue-600 to-indigo-600"),
            "GALAN": ("PRIME PLAY", "from-blue-600 to-indigo-600"),
            "CHINGOTTO": ("OFF-PEAK MORNING", "from-emerald-600 to-teal-700"),
            "LEBRÓN": ("DAYTIME PRO", "from-slate-700 to-slate-900"),
            "LEBRON": ("DAYTIME PRO", "from-slate-700 to-slate-900"),
        }
        updated = False
        for p in existing:
            key = p.name.upper()
            for k in palette:
                if k in key:
                    b, g = palette[k]
                    if not p.badge_label or p.badge_label == "PLAN SOCIO":
                        p.badge_label = b
                        updated = True
                    if not p.card_gradient or p.card_gradient == "from-slate-800 to-indigo-900":
                        p.card_gradient = g
                        updated = True
                    break
        if updated:
            await db.commit()


async def list_plans(db: AsyncSession, active_only: bool = False) -> List[Dict[str, Any]]:
    await ensure_default_membership_plans(db)
    stmt = select(MembershipPlan)
    if active_only:
        stmt = stmt.where(MembershipPlan.is_active == True)
    stmt = stmt.order_by(MembershipPlan.monthly_price_cop.desc())
    res = await db.execute(stmt)
    plans = res.scalars().all()

    result = []
    for plan in plans:
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

        palette = {
            "TAPIA": ("VIP PLATINUM", "from-amber-600 to-yellow-700"),
            "COELLO": ("ALL ACCESS", "from-indigo-600 to-purple-700"),
            "GALÁN": ("PRIME PLAY", "from-blue-600 to-indigo-600"),
            "GALAN": ("PRIME PLAY", "from-blue-600 to-indigo-600"),
            "CHINGOTTO": ("OFF-PEAK MORNING", "from-emerald-600 to-teal-700"),
            "LEBRÓN": ("DAYTIME PRO", "from-slate-700 to-slate-900"),
            "LEBRON": ("DAYTIME PRO", "from-slate-700 to-slate-900"),
        }
        resolved_badge = plan.badge_label
        resolved_grad = plan.card_gradient
        for k, (def_b, def_g) in palette.items():
            if k in norm_name:
                if not resolved_badge or resolved_badge == "PLAN SOCIO":
                    resolved_badge = def_b
                if not resolved_grad or resolved_grad == "from-slate-800 to-indigo-900":
                    resolved_grad = def_g
                break

        result.append({
            "id": plan.id,
            "name": plan.name,
            "start_time": plan.start_time.strftime("%H:%M:%S") if plan.start_time else "06:00:00",
            "end_time": plan.end_time.strftime("%H:%M:%S") if plan.end_time else "23:59:00",
            "max_daily_hours": plan.max_daily_hours,
            "includes_academy_classes": plan.includes_academy_classes,
            "monthly_classes_count": plan.monthly_classes_count,
            "includes_beverage_perk": plan.includes_beverage_perk,
            "americano_discount_pct": plan.americano_discount_pct,
            "monthly_price_cop": plan.monthly_price_cop,
            "badge_label": resolved_badge or "PLAN SOCIO",
            "card_gradient": resolved_grad or "from-slate-800 to-indigo-900",
            "is_active": plan.is_active,
            "active_members_count": active_count,
        })
    return result


async def get_plan_by_id(db: AsyncSession, plan_id: int) -> Optional[MembershipPlan]:
    stmt = select(MembershipPlan).where(MembershipPlan.id == plan_id)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def create_plan(db: AsyncSession, data: Dict[str, Any]) -> MembershipPlan:
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("El nombre del plan de membresía es obligatorio")

    # Validar unicidad
    stmt = select(MembershipPlan).where(MembershipPlan.name.ilike(name))
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()
    if existing:
        raise ValueError(f"Ya existe un plan con el nombre '{name}'")

    start_t = parse_time_str(data.get("start_time", "06:00:00"))
    end_t = parse_time_str(data.get("end_time", "23:59:00"))

    plan = MembershipPlan(
        name=name,
        start_time=start_t,
        end_time=end_t,
        max_daily_hours=float(data.get("max_daily_hours", 1.5)),
        includes_academy_classes=bool(data.get("includes_academy_classes", False)),
        monthly_classes_count=int(data.get("monthly_classes_count", 0)),
        includes_beverage_perk=bool(data.get("includes_beverage_perk", False)),
        americano_discount_pct=int(data.get("americano_discount_pct", 0)),
        monthly_price_cop=int(data.get("monthly_price_cop", 0)),
        badge_label=data.get("badge_label") or "PLAN SOCIO",
        card_gradient=data.get("card_gradient") or "from-slate-800 to-indigo-900",
        is_active=bool(data.get("is_active", True)),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def update_plan(db: AsyncSession, plan_id: int, data: Dict[str, Any]) -> MembershipPlan:
    plan = await get_plan_by_id(db, plan_id)
    if not plan:
        raise ValueError("Plan de membresía no encontrado")

    if "name" in data and data["name"]:
        new_name = data["name"].strip()
        # Verificar que no colisione con otro
        stmt = select(MembershipPlan).where(MembershipPlan.name.ilike(new_name), MembershipPlan.id != plan_id)
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise ValueError(f"Ya existe otro plan con el nombre '{new_name}'")
        plan.name = new_name

    if "start_time" in data:
        plan.start_time = parse_time_str(data["start_time"])
    if "end_time" in data:
        plan.end_time = parse_time_str(data["end_time"])
    if "max_daily_hours" in data:
        plan.max_daily_hours = float(data["max_daily_hours"])
    if "includes_academy_classes" in data:
        plan.includes_academy_classes = bool(data["includes_academy_classes"])
    if "monthly_classes_count" in data:
        plan.monthly_classes_count = int(data["monthly_classes_count"])
    if "includes_beverage_perk" in data:
        plan.includes_beverage_perk = bool(data["includes_beverage_perk"])
    if "americano_discount_pct" in data:
        plan.americano_discount_pct = int(data["americano_discount_pct"])
    if "monthly_price_cop" in data:
        plan.monthly_price_cop = int(data["monthly_price_cop"])
    if "badge_label" in data and data["badge_label"]:
        plan.badge_label = data["badge_label"].strip()
    if "card_gradient" in data and data["card_gradient"]:
        plan.card_gradient = data["card_gradient"].strip()
    if "is_active" in data:
        plan.is_active = bool(data["is_active"])

    await db.commit()
    await db.refresh(plan)
    return plan


async def delete_or_deactivate_plan(db: AsyncSession, plan_id: int) -> Dict[str, Any]:
    plan = await get_plan_by_id(db, plan_id)
    if not plan:
        raise ValueError("Plan de membresía no encontrado")

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

    if active_count > 0:
        # No eliminar en cascada, desactivar para proteger historial de socios
        plan.is_active = False
        await db.commit()
        return {
            "status": "deactivated",
            "message": f"El plan '{plan.name}' tiene {active_count} socios asociados. Se desactivó correctamente para preservar los perfiles.",
            "plan_id": plan.id,
            "active_members_count": active_count,
            "is_active": False,
        }
    else:
        # Se puede eliminar físicamente
        await db.delete(plan)
        await db.commit()
        return {
            "status": "deleted",
            "message": f"El plan '{plan.name}' fue eliminado exitosamente.",
            "plan_id": plan_id,
            "active_members_count": 0,
            "is_active": False,
        }


async def assign_membership(
    db: AsyncSession, customer_id: int, plan_id: Optional[int] = None, tier_name: Optional[str] = None, validity_days: int = 30
) -> Dict[str, Any]:
    await ensure_default_membership_plans(db)

    cust_stmt = select(Customer).where(Customer.id == customer_id)
    cust_res = await db.execute(cust_stmt)
    customer = cust_res.scalar_one_or_none()
    if not customer:
        raise ValueError("Cliente no encontrado")

    plan = None
    if plan_id:
        plan = await get_plan_by_id(db, plan_id)

    if not plan and tier_name:
        tier_clean = tier_name.strip().upper()
        plan_stmt = select(MembershipPlan).where(MembershipPlan.name.ilike(tier_clean))
        plan_res = await db.execute(plan_stmt)
        plan = plan_res.scalar_one_or_none()

    if not plan:
        plan_stmt = select(MembershipPlan).order_by(MembershipPlan.id.asc()).limit(1)
        plan_res = await db.execute(plan_stmt)
        plan = plan_res.scalar_one_or_none()

    today = date.today()
    val_days = validity_days if validity_days > 0 else 30

    customer.membership_plan_id = plan.id if plan else None
    customer.membership_tier = plan.name.upper() if plan else "ESTANDAR"
    customer.client_type = f"Socio VIP ({plan.name})" if plan else "Estándar"
    customer.membership_start_date = today
    customer.membership_end_date = today + timedelta(days=val_days)
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
        "days_remaining": val_days,
        "plan_id": plan.id if plan else None,
    }
