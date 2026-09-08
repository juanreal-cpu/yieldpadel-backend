from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import membership as membership_service

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
    badge_label: str = "PLAN SOCIO"
    card_gradient: str = "from-slate-800 to-indigo-900"
    is_active: bool = True
    active_members_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class MembershipPlanCreateRequest(BaseModel):
    name: str
    start_time: str = "06:00:00"
    end_time: str = "23:59:00"
    max_daily_hours: float = 1.5
    includes_academy_classes: bool = False
    monthly_classes_count: int = 0
    includes_beverage_perk: bool = False
    americano_discount_pct: int = 0
    monthly_price_cop: int = 0
    badge_label: Optional[str] = "PLAN SOCIO"
    card_gradient: Optional[str] = "from-slate-800 to-indigo-900"
    is_active: bool = True


class MembershipPlanUpdateRequest(BaseModel):
    name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    max_daily_hours: Optional[float] = None
    includes_academy_classes: Optional[bool] = None
    monthly_classes_count: Optional[int] = None
    includes_beverage_perk: Optional[bool] = None
    americano_discount_pct: Optional[int] = None
    monthly_price_cop: Optional[int] = None
    badge_label: Optional[str] = None
    card_gradient: Optional[str] = None
    is_active: Optional[bool] = None


class AssignMembershipRequest(BaseModel):
    customer_id: int
    plan_id: Optional[int] = None
    membership_tier: Optional[str] = None
    validity_days: int = 30


@router.get("", response_model=List[MembershipPlanResponse])
@router.get("/", response_model=List[MembershipPlanResponse])
async def list_membership_plans(
    active_only: bool = Query(False, description="Filtrar solo planes activos"),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos los planes de membresía configurados con su conteo de socios activos."""
    plans = await membership_service.list_plans(db, active_only=active_only)
    return [MembershipPlanResponse(**p) for p in plans]


@router.post("", response_model=MembershipPlanResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=MembershipPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_membership_plan(
    payload: MembershipPlanCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo tipo o categoría de plan de membresía."""
    try:
        plan = await membership_service.create_plan(db, payload.model_dump())
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
            badge_label=plan.badge_label or "PLAN SOCIO",
            card_gradient=plan.card_gradient or "from-slate-800 to-indigo-900",
            is_active=plan.is_active,
            active_members_count=0,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{plan_id}", response_model=MembershipPlanResponse)
async def update_membership_plan(
    plan_id: int,
    payload: MembershipPlanUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Modifica los parámetros de un plan de membresía existente."""
    try:
        plan = await membership_service.update_plan(
            db, plan_id, {k: v for k, v in payload.model_dump().items() if v is not None}
        )
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
            badge_label=plan.badge_label or "PLAN SOCIO",
            card_gradient=plan.card_gradient or "from-slate-800 to-indigo-900",
            is_active=plan.is_active,
            active_members_count=0,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{plan_id}")
async def delete_or_deactivate_membership_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Elimina o desactiva un plan de membresía.
    Si tiene socios asociados, lo desactiva (is_active=False) para no romper históricos ni perfiles.
    """
    try:
        res = await membership_service.delete_or_deactivate_plan(db, plan_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/assign")
async def assign_membership_to_customer(
    payload: AssignMembershipRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Asigna un plan de membresía a un cliente fijando 30 días de vigencia (membership_end_date = hoy + 30 días).
    """
    try:
        res = await membership_service.assign_membership(
            db,
            customer_id=payload.customer_id,
            plan_id=payload.plan_id,
            tier_name=payload.membership_tier,
            validity_days=payload.validity_days,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
