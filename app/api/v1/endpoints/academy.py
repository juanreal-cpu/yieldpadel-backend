import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.academy import AcademyClass, AcademyEnrollment
from app.models.customer import Customer
from app.models.membership import MembershipPlan
from app.models.court import Court
from app.models.slot import TimeSlot, SlotMode, SlotStatus

router = APIRouter()


class EnrollmentDetail(BaseModel):
    id: int
    player_id: int
    player_name: str
    phone: str
    payment_status: str
    amount_charged: int
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class AcademyClassResponse(BaseModel):
    id: int
    title: str
    level: str
    date: str
    start_time: str
    end_time: str
    court_id: str
    court_name: str
    coach_name: str
    max_students: int
    price_per_student: int
    enrolled_count: int
    available_spots: int
    enrollments: List[EnrollmentDetail] = []

    model_config = ConfigDict(from_attributes=True)


class CreateAcademyClassRequest(BaseModel):
    title: str
    level: str  # INICIACION_6_7, MEDIO_4_5, AVANZADO
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM or HH:MM:SS
    end_time: str  # HH:MM or HH:MM:SS
    court_id: str
    coach_name: str
    max_students: int = 4
    price_per_student: int = 35000


class EnrollStudentRequest(BaseModel):
    academy_class_id: int
    player_id: int


def parse_time(t_str: str) -> time:
    try:
        parts = t_str.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return time(8, 0)


@router.get("/classes", response_model=List[AcademyClassResponse])
async def list_academy_classes(
    date_query: Optional[str] = Query(None, alias="date", description="Filtrar por fecha YYYY-MM-DD"),
    level: Optional[str] = Query(None, description="Filtrar por nivel"),
    db: AsyncSession = Depends(get_db),
):
    """Lista las clases de academia con sus alumnos inscritos y cupos disponibles."""
    stmt = select(AcademyClass).order_by(AcademyClass.date.asc(), AcademyClass.start_time.asc())

    if date_query:
        try:
            target_date = datetime.strptime(date_query.strip(), "%Y-%m-%d").date()
            stmt = stmt.where(AcademyClass.date == target_date)
        except Exception:
            pass

    if level and level.upper() not in ["ALL", "TODAS", ""]:
        stmt = stmt.where(AcademyClass.level == level)

    res = await db.execute(stmt)
    classes = res.scalars().all()

    # Si no hay clases creadas, proveer clases demo para que la UI muestre contenido de inmediato
    if not classes:
        # Buscar una cancha de pádel
        court_stmt = select(Court).where(Court.sport_type == "PADEL").limit(1)
        court_res = await db.execute(court_stmt)
        c = court_res.scalar_one_or_none()
        if c:
            today = date.today()
            demo_classes = [
                AcademyClass(
                    title="Clase Media - Estrategia & Paredes",
                    level="MEDIO_4_5",
                    date=today,
                    start_time=time(8, 0),
                    end_time=time(9, 30),
                    court_id=c.id,
                    coach_name="Coach Mateo Rivas",
                    max_students=4,
                    price_per_student=35000,
                ),
                AcademyClass(
                    title="Iniciación Técnica y Empuñaduras",
                    level="INICIACION_6_7",
                    date=today,
                    start_time=time(10, 0),
                    end_time=time(11, 30),
                    court_id=c.id,
                    coach_name="Coach Marcos Valdés",
                    max_students=4,
                    price_per_student=35000,
                ),
                AcademyClass(
                    title="Entrenamiento Táctico Avanzado",
                    level="AVANZADO",
                    date=today + timedelta(days=1),
                    start_time=time(18, 0),
                    end_time=time(19, 30),
                    court_id=c.id,
                    coach_name="Coach Mateo Rivas",
                    max_students=4,
                    price_per_student=45000,
                ),
            ]
            for demo in demo_classes:
                db.add(demo)
            await db.commit()

            # Re-consultar
            res = await db.execute(stmt)
            classes = res.scalars().all()

    result = []
    for cls in classes:
        court_name = cls.court.name if cls.court else "Cancha Principal"
        enrollments_data = []
        for enr in cls.enrollments:
            p_name = enr.customer.name if enr.customer else (enr.player.name if enr.player else f"Alumno #{enr.player_id}")
            p_phone = enr.customer.phone if enr.customer else ""
            enrollments_data.append(
                EnrollmentDetail(
                    id=enr.id,
                    player_id=enr.player_id,
                    player_name=p_name,
                    phone=p_phone,
                    payment_status=enr.payment_status,
                    amount_charged=enr.amount_charged,
                    created_at=enr.created_at.strftime("%Y-%m-%d %H:%M") if enr.created_at else "",
                )
            )

        enrolled_count = len(enrollments_data)
        available_spots = max(0, cls.max_students - enrolled_count)

        result.append(
            AcademyClassResponse(
                id=cls.id,
                title=cls.title,
                level=cls.level,
                date=cls.date.strftime("%Y-%m-%d"),
                start_time=cls.start_time.strftime("%H:%M"),
                end_time=cls.end_time.strftime("%H:%M"),
                court_id=str(cls.court_id),
                court_name=court_name,
                coach_name=cls.coach_name,
                max_students=cls.max_students,
                price_per_student=cls.price_per_student,
                enrolled_count=enrolled_count,
                available_spots=available_spots,
                enrollments=enrollments_data,
            )
        )

    return result


@router.post("/classes", response_model=AcademyClassResponse, status_code=status.HTTP_201_CREATED)
async def create_academy_class(
    payload: CreateAcademyClassRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Crea una clase en la academia y bloquea/asigna automáticamente la cancha en la Matriz Calendario (slot_type='CLASS').
    """
    try:
        class_date = datetime.strptime(payload.date.strip(), "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (debe ser YYYY-MM-DD)")

    start_t = parse_time(payload.start_time)
    end_t = parse_time(payload.end_time)

    # Validar que court_id sea UUID válido
    try:
        target_court_id = uuid.UUID(payload.court_id.strip())
    except Exception:
        # Fallback a buscar por nombre o primera cancha
        c_stmt = select(Court).where(Court.id == payload.court_id).limit(1)
        c_res = await db.execute(c_stmt)
        court_obj = c_res.scalar_one_or_none()
        if not court_obj:
            c_first = await db.execute(select(Court).limit(1))
            court_obj = c_first.scalar_one_or_none()
        if not court_obj:
            raise HTTPException(status_code=404, detail="Cancha no encontrada")
        target_court_id = court_obj.id

    new_class = AcademyClass(
        title=payload.title.strip(),
        level=payload.level.strip(),
        date=class_date,
        start_time=start_t,
        end_time=end_t,
        court_id=target_court_id,
        coach_name=payload.coach_name.strip(),
        max_students=payload.max_students,
        price_per_student=payload.price_per_student,
    )
    db.add(new_class)
    await db.flush()

    # Generar / Sincronizar TimeSlot en la cancha para reflejar en el Calendario
    slot_stmt = select(TimeSlot).where(
        TimeSlot.court_id == target_court_id,
        TimeSlot.date == class_date,
        TimeSlot.start_time == start_t,
    )
    slot_res = await db.execute(slot_stmt)
    slot = slot_res.scalar_one_or_none()

    if slot:
        slot.slot_type = "CLASS"
        slot.instructor_name = payload.coach_name.strip()
        slot.capacity = payload.max_students
        slot.status = SlotStatus.BLOCKED
        slot.category = payload.level.strip()
    else:
        new_slot = TimeSlot(
            court_id=target_court_id,
            date=class_date,
            start_time=start_t,
            end_time=end_t,
            total_price=Decimal(str(payload.price_per_student * payload.max_students)),
            mode=SlotMode.SPLIT_MATCH,
            capacity=payload.max_students,
            booked_spots=0,
            status=SlotStatus.BLOCKED,
            players_names=[],
            category=payload.level.strip(),
            slot_type="CLASS",
            instructor_name=payload.coach_name.strip(),
            sport_type="PADEL",
        )
        db.add(new_slot)

    await db.commit()
    await db.refresh(new_class)

    court_name_stmt = select(Court.name).where(Court.id == target_court_id)
    c_name_res = await db.execute(court_name_stmt)
    court_name = c_name_res.scalar() or "Cancha"

    return AcademyClassResponse(
        id=new_class.id,
        title=new_class.title,
        level=new_class.level,
        date=new_class.date.strftime("%Y-%m-%d"),
        start_time=new_class.start_time.strftime("%H:%M"),
        end_time=new_class.end_time.strftime("%H:%M"),
        court_id=str(new_class.court_id),
        court_name=court_name,
        coach_name=new_class.coach_name,
        max_students=new_class.max_students,
        price_per_student=new_class.price_per_student,
        enrolled_count=0,
        available_spots=new_class.max_students,
        enrollments=[],
    )


@router.post("/enroll")
async def enroll_student_in_class(
    payload: EnrollStudentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Inscribe a un socio a una clase de academia, validando aforo y si su membresía cubre la sesión ($0 COP) o genera pago pendiente.
    """
    cls_stmt = select(AcademyClass).where(AcademyClass.id == payload.academy_class_id)
    cls_res = await db.execute(cls_stmt)
    cls = cls_res.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Clase de academia no encontrada")

    cust_stmt = select(Customer).where(Customer.id == payload.player_id)
    cust_res = await db.execute(cust_stmt)
    customer = cust_res.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Jugador no encontrado en CRM")

    # Validar aforo
    enr_count = len(cls.enrollments)
    if enr_count >= cls.max_students:
        raise HTTPException(status_code=400, detail="Aforo completo: la clase ya alcanzó el límite máximo de alumnos")

    # Validar si ya está inscrito
    if any(e.player_id == customer.id for e in cls.enrollments):
        raise HTTPException(status_code=400, detail="El jugador ya está inscrito en esta clase")

    # Validar membresía para cortesía de clase
    today = date.today()
    is_covered = False
    perk_message = ""

    # Comprobar si tiene plan activo
    has_active_membership = customer.membership_end_date and customer.membership_end_date >= today
    tier_upper = (customer.membership_tier or "").upper()

    plan = customer.membership_plan
    if not plan and tier_upper:
        plan_stmt = select(MembershipPlan).where(MembershipPlan.name.ilike(tier_upper))
        plan_res = await db.execute(plan_stmt)
        plan = plan_res.scalar_one_or_none()

    if has_active_membership and plan and plan.includes_academy_classes:
        allowed_classes = plan.monthly_classes_count or 0
        used_classes = customer.academy_classes_used or 0
        if used_classes < allowed_classes:
            is_covered = True
            customer.academy_classes_used = used_classes + 1
            perk_message = f"Clase incluida en Membresía {plan.name} ({customer.academy_classes_used}/{allowed_classes} usadas)"
        else:
            perk_message = f"Cupo de clases del mes completado ({used_classes}/{allowed_classes}). Tarifa regular."
    elif tier_upper in ["TAPIA", "COELLO"]:
        # Fallback de membresías VIP
        used_classes = customer.academy_classes_used or 0
        max_allowed = 4 if tier_upper == "TAPIA" else 2
        if used_classes < max_allowed:
            is_covered = True
            customer.academy_classes_used = used_classes + 1
            perk_message = f"Clase incluida en Membresía VIP ({customer.academy_classes_used}/{max_allowed} usadas)"

    payment_status = "INCLUDED_IN_MEMBERSHIP" if is_covered else "PENDING"
    amount_charged = 0 if is_covered else cls.price_per_student

    enrollment = AcademyEnrollment(
        academy_class_id=cls.id,
        player_id=customer.id,
        payment_status=payment_status,
        amount_charged=amount_charged,
    )
    db.add(enrollment)

    # Actualizar TimeSlot vinculado
    slot_stmt = select(TimeSlot).where(
        TimeSlot.court_id == cls.court_id,
        TimeSlot.date == cls.date,
        TimeSlot.start_time == cls.start_time,
    )
    slot_res = await db.execute(slot_stmt)
    slot = slot_res.scalar_one_or_none()
    if slot:
        slot.booked_spots = enr_count + 1
        current_names = list(slot.players_names or [])
        if customer.name not in current_names:
            current_names.append(customer.name)
        slot.players_names = current_names

    await db.commit()
    await db.refresh(enrollment)

    return {
        "status": "success",
        "message": f"Inscripción exitosa: {customer.name} a '{cls.title}'",
        "enrollment_id": enrollment.id,
        "is_covered_by_membership": is_covered,
        "amount_charged": amount_charged,
        "payment_status": payment_status,
        "perk_message": perk_message,
        "available_spots_left": cls.max_students - (enr_count + 1),
    }
