import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.academy import AcademyClass, AcademyEnrollment
from app.models.customer import Customer
from app.models.membership import MembershipPlan
from app.models.court import Court
from app.models.slot import TimeSlot, SlotMode, SlotStatus


def parse_time_str(t_str: str) -> time:
    if isinstance(t_str, time):
        return t_str
    try:
        parts = str(t_str).strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return time(8, 0)


async def create_class(db: AsyncSession, data: Dict[str, Any]) -> AcademyClass:
    title = data.get("title", "").strip()
    if not title:
        raise ValueError("El título de la clase es obligatorio")

    date_val = data.get("date")
    if isinstance(date_val, str):
        class_date = datetime.strptime(date_val.strip(), "%Y-%m-%d").date()
    elif isinstance(date_val, date):
        class_date = date_val
    else:
        class_date = date.today()

    start_t = parse_time_str(data.get("start_time", "08:00"))
    end_t = parse_time_str(data.get("end_time", "09:30"))
    coach_name = data.get("coach_name", "").strip() or "Coach Principal"
    level = data.get("level", "INICIACION_6_7").strip()
    target_age = data.get("target_age", "ADULTOS").strip()
    max_students = int(data.get("max_students", 4))
    price_per_student = int(data.get("price_per_student", 35000))

    court_id_raw = data.get("court_id")
    target_court_id = None
    if court_id_raw:
        try:
            target_court_id = uuid.UUID(str(court_id_raw).strip())
        except Exception:
            c_stmt = select(Court).where(Court.id == court_id_raw).limit(1)
            c_res = await db.execute(c_stmt)
            c_obj = c_res.scalar_one_or_none()
            if c_obj:
                target_court_id = c_obj.id

    if not target_court_id:
        c_first = await db.execute(select(Court).limit(1))
        c_obj = c_first.scalar_one_or_none()
        if not c_obj:
            raise ValueError("No hay canchas registradas en el sistema para programar la clase")
        target_court_id = c_obj.id

    new_class = AcademyClass(
        title=title,
        level=level,
        target_age=target_age,
        date=class_date,
        start_time=start_t,
        end_time=end_t,
        court_id=target_court_id,
        coach_name=coach_name,
        max_students=max_students,
        price_per_student=price_per_student,
    )
    db.add(new_class)
    await db.flush()

    # Sincronizar TimeSlot en el calendario de canchas
    slot_stmt = select(TimeSlot).where(
        TimeSlot.court_id == target_court_id,
        TimeSlot.date == class_date,
        TimeSlot.start_time == start_t,
    )
    slot_res = await db.execute(slot_stmt)
    slot = slot_res.scalar_one_or_none()

    if slot:
        slot.slot_type = "CLASS"
        slot.instructor_name = coach_name
        slot.capacity = max_students
        slot.status = SlotStatus.BLOCKED
        slot.category = level
    else:
        new_slot = TimeSlot(
            court_id=target_court_id,
            date=class_date,
            start_time=start_t,
            end_time=end_t,
            total_price=Decimal(str(price_per_student * max_students)),
            mode=SlotMode.SPLIT_MATCH,
            capacity=max_students,
            booked_spots=0,
            status=SlotStatus.BLOCKED,
            players_names=[],
            category=level,
            slot_type="CLASS",
            instructor_name=coach_name,
            sport_type="PADEL",
        )
        db.add(new_slot)

    await db.commit()
    await db.refresh(new_class)
    return new_class


async def enroll_student(db: AsyncSession, academy_class_id: int, player_id: int) -> Dict[str, Any]:
    cls_stmt = (
        select(AcademyClass)
        .options(selectinload(AcademyClass.enrollments))
        .where(AcademyClass.id == academy_class_id)
    )
    cls_res = await db.execute(cls_stmt)
    cls = cls_res.scalar_one_or_none()
    if not cls:
        raise ValueError("Clase de academia no encontrada")

    cust_stmt = (
        select(Customer)
        .options(
            selectinload(Customer.guardian).selectinload(Customer.membership_plan),
            selectinload(Customer.membership_plan),
        )
        .where(Customer.id == player_id)
    )
    cust_res = await db.execute(cust_stmt)
    student = cust_res.scalar_one_or_none()
    if not student:
        raise ValueError("Jugador / Alumno no encontrado en el CRM")

    # Validar aforo
    enr_count = len(cls.enrollments)
    if enr_count >= cls.max_students:
        raise ValueError("Aforo completo: la clase ya alcanzó el límite máximo de alumnos")

    # Validar si ya está inscrito
    if any(e.player_id == student.id for e in cls.enrollments):
        raise ValueError("El jugador ya se encuentra inscrito en esta clase")

    today = date.today()
    is_covered = False
    perk_message = ""
    payment_status = "PENDING"
    amount_charged = cls.price_per_student
    guardian_info = None

    # Caso 1: Estudiante es menor de edad (Kid) con acudiente
    if student.is_minor:
        guardian = student.guardian
        if not guardian and student.guardian_id:
            g_res = await db.execute(
                select(Customer)
                .options(selectinload(Customer.membership_plan))
                .where(Customer.id == student.guardian_id)
            )
            guardian = g_res.scalar_one_or_none()

        if guardian:
            guardian_info = {
                "id": guardian.id,
                "name": guardian.name,
                "phone": guardian.phone,
                "relationship": student.guardian_relationship or "ACUDIENTE",
            }
            # Verificar si el acudiente tiene membresía activa con beneficio de academia
            has_active_membership = (
                guardian.membership_end_date and guardian.membership_end_date >= today
            )
            g_plan = guardian.membership_plan
            if not g_plan and guardian.membership_tier:
                g_tier_upper = guardian.membership_tier.upper()
                p_res = await db.execute(
                    select(MembershipPlan).where(MembershipPlan.name.ilike(g_tier_upper))
                )
                g_plan = p_res.scalar_one_or_none()

            if has_active_membership and g_plan and g_plan.includes_academy_classes:
                allowed_classes = g_plan.monthly_classes_count or 0
                used_classes = guardian.academy_classes_used or 0
                if used_classes < allowed_classes:
                    is_covered = True
                    payment_status = "INCLUDED_IN_GUARDIAN_MEMBERSHIP"
                    amount_charged = 0
                    guardian.academy_classes_used = used_classes + 1
                    perk_message = (
                        f"Clase cubierta por Membresía {g_plan.name} del acudiente {guardian.name} "
                        f"({guardian.academy_classes_used}/{allowed_classes} usadas)"
                    )
                else:
                    payment_status = "PENDING"
                    amount_charged = cls.price_per_student
                    perk_message = (
                        f"Menor apadrinado por {guardian.name}. Cupo mensual de clases del acudiente "
                        f"completado ({used_classes}/{allowed_classes}). Tarifa regular pendiente."
                    )
            elif (
                has_active_membership
                and guardian.membership_tier
                and guardian.membership_tier.upper() in ["TAPIA", "COELLO"]
            ):
                used_classes = guardian.academy_classes_used or 0
                max_allowed = 4 if guardian.membership_tier.upper() == "TAPIA" else 2
                if used_classes < max_allowed:
                    is_covered = True
                    payment_status = "INCLUDED_IN_GUARDIAN_MEMBERSHIP"
                    amount_charged = 0
                    guardian.academy_classes_used = used_classes + 1
                    perk_message = (
                        f"Clase cubierta por Membresía VIP {guardian.membership_tier} del acudiente {guardian.name} "
                        f"({guardian.academy_classes_used}/{max_allowed} usadas)"
                    )
                else:
                    payment_status = "PENDING"
                    amount_charged = cls.price_per_student
                    perk_message = (
                        f"Menor apadrinado por {guardian.name}. Cupo VIP agotado ({used_classes}/{max_allowed}). Tarifa regular pendiente."
                    )
            else:
                payment_status = "PENDING"
                amount_charged = cls.price_per_student
                perk_message = (
                    f"Menor apadrinado por {guardian.name} (sin membresía de academia activa). "
                    f"Cobro pendiente ($ {amount_charged:,} COP) registrado al acudiente."
                )
        else:
            payment_status = "PENDING"
            amount_charged = cls.price_per_student
            perk_message = "Alumno menor de edad sin acudiente vinculado. Tarifa regular pendiente."

    # Caso 2: Estudiante adulto
    else:
        has_active_membership = (
            student.membership_end_date and student.membership_end_date >= today
        )
        plan = student.membership_plan
        if not plan and student.membership_tier:
            s_tier_upper = student.membership_tier.upper()
            p_res = await db.execute(
                select(MembershipPlan).where(MembershipPlan.name.ilike(s_tier_upper))
            )
            plan = p_res.scalar_one_or_none()

        if has_active_membership and plan and plan.includes_academy_classes:
            allowed_classes = plan.monthly_classes_count or 0
            used_classes = student.academy_classes_used or 0
            if used_classes < allowed_classes:
                is_covered = True
                payment_status = "INCLUDED_IN_MEMBERSHIP"
                amount_charged = 0
                student.academy_classes_used = used_classes + 1
                perk_message = (
                    f"Clase incluida en Membresía {plan.name} "
                    f"({student.academy_classes_used}/{allowed_classes} usadas)"
                )
            else:
                payment_status = "PENDING"
                amount_charged = cls.price_per_student
                perk_message = f"Cupo de clases del mes completado ({used_classes}/{allowed_classes}). Tarifa regular."
        elif (
            has_active_membership
            and student.membership_tier
            and student.membership_tier.upper() in ["TAPIA", "COELLO"]
        ):
            used_classes = student.academy_classes_used or 0
            max_allowed = 4 if student.membership_tier.upper() == "TAPIA" else 2
            if used_classes < max_allowed:
                is_covered = True
                payment_status = "INCLUDED_IN_MEMBERSHIP"
                amount_charged = 0
                student.academy_classes_used = used_classes + 1
                perk_message = f"Clase incluida en Membresía VIP ({student.academy_classes_used}/{max_allowed} usadas)"
            else:
                payment_status = "PENDING"
                amount_charged = cls.price_per_student
                perk_message = f"Cupo VIP agotado ({used_classes}/{max_allowed}). Tarifa regular."
        else:
            payment_status = "PENDING"
            amount_charged = cls.price_per_student
            perk_message = "Sin membresía de clases activa. Tarifa regular."

    enrollment = AcademyEnrollment(
        academy_class_id=cls.id,
        player_id=student.id,
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
        display_name = (
            f"{student.name} (Kid)" if student.is_minor else student.name
        )
        if display_name not in current_names:
            current_names.append(display_name)
        slot.players_names = current_names

    await db.commit()
    await db.refresh(enrollment)

    return {
        "status": "success",
        "message": f"Inscripción exitosa: {student.name} a '{cls.title}'",
        "enrollment_id": enrollment.id,
        "is_minor": student.is_minor,
        "guardian": guardian_info,
        "is_covered_by_membership": is_covered,
        "amount_charged": amount_charged,
        "payment_status": payment_status,
        "perk_message": perk_message,
        "available_spots_left": cls.max_students - (enr_count + 1),
    }
