import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.academy import AcademyClass, AcademyEnrollment
from app.models.customer import Customer
from app.models.court import Court
from app.services import academy as academy_service

router = APIRouter()


class EnrollmentDetail(BaseModel):
    id: int
    player_id: int
    player_name: str
    phone: str
    is_minor: bool = False
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None
    payment_status: str
    amount_charged: int
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class AcademyClassResponse(BaseModel):
    id: int
    title: str
    level: str
    target_age: str = "ADULTOS"
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
    level: str  # KIDS_INICIACION, KIDS_INTERMEDIO, INICIACION_6_7, MEDIO_4_5, AVANZADO
    target_age: str = "ADULTOS"  # ADULTOS, KIDS_SUB10, KIDS_SUB14, JUNIOR
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


@router.get("/classes", response_model=List[AcademyClassResponse])
async def list_academy_classes(
    date_query: Optional[str] = Query(None, alias="date", description="Filtrar por fecha YYYY-MM-DD"),
    level: Optional[str] = Query(None, description="Filtrar por nivel"),
    target_age: Optional[str] = Query(None, description="Filtrar por edad o categoría (ADULTOS, KIDS_SUB10, KIDS_SUB14, JUNIOR)"),
    db: AsyncSession = Depends(get_db),
):
    """Lista las clases de academia con sus alumnos inscritos, cupos disponibles y soporte de categorías Kids."""
    stmt = (
        select(AcademyClass)
        .options(
            selectinload(AcademyClass.court),
            selectinload(AcademyClass.enrollments).selectinload(AcademyEnrollment.customer).selectinload(Customer.guardian),
        )
        .order_by(AcademyClass.date.asc(), AcademyClass.start_time.asc())
    )

    if date_query:
        try:
            target_date = datetime.strptime(date_query.strip(), "%Y-%m-%d").date()
            stmt = stmt.where(AcademyClass.date == target_date)
        except Exception:
            pass

    if level and level.upper() not in ["ALL", "TODAS", ""]:
        stmt = stmt.where(AcademyClass.level == level)

    if target_age and target_age.upper() not in ["ALL", "TODAS", ""]:
        stmt = stmt.where(AcademyClass.target_age == target_age.upper())

    res = await db.execute(stmt)
    classes = res.scalars().all()

    # Si no hay clases creadas, sembrar clases iniciales (incluyendo categoría Kids)
    if not classes:
        court_stmt = select(Court).where(Court.sport_type == "PADEL").limit(1)
        court_res = await db.execute(court_stmt)
        c = court_res.scalar_one_or_none()
        if c:
            today = date.today()
            demo_classes = [
                AcademyClass(
                    title="Kids Semillero Sub-10 - Fundamentos & Psicomotricidad",
                    level="KIDS_INICIACION",
                    target_age="KIDS_SUB10",
                    date=today,
                    start_time=time(15, 30),
                    end_time=time(17, 0),
                    court_id=c.id,
                    coach_name="Coach Mateo Rivas",
                    max_students=4,
                    price_per_student=35000,
                ),
                AcademyClass(
                    title="Junior Sub-14 - Transición y Voleas de Ataque",
                    level="KIDS_INTERMEDIO",
                    target_age="KIDS_SUB14",
                    date=today,
                    start_time=time(17, 0),
                    end_time=time(18, 30),
                    court_id=c.id,
                    coach_name="Coach Marcos Valdés",
                    max_students=4,
                    price_per_student=35000,
                ),
                AcademyClass(
                    title="Iniciación Adultos - Técnica y Empuñaduras",
                    level="INICIACION_6_7",
                    target_age="ADULTOS",
                    date=today,
                    start_time=time(18, 30),
                    end_time=time(20, 0),
                    court_id=c.id,
                    coach_name="Coach Mateo Rivas",
                    max_students=4,
                    price_per_student=35000,
                ),
            ]
            for demo in demo_classes:
                db.add(demo)
            await db.commit()

            res = await db.execute(stmt)
            classes = res.scalars().all()

    result = []
    for cls in classes:
        court_name = cls.court.name if cls.court else "Cancha Principal"
        enrollments_data = []
        for enr in cls.enrollments:
            student = enr.customer
            p_name = student.name if student else f"Alumno #{enr.player_id}"
            p_phone = student.phone if student else ""
            is_minor = student.is_minor if student else False
            g_name = student.guardian.name if (student and student.guardian) else None
            g_phone = student.guardian.phone if (student and student.guardian) else None

            enrollments_data.append(
                EnrollmentDetail(
                    id=enr.id,
                    player_id=enr.player_id,
                    player_name=p_name,
                    phone=p_phone,
                    is_minor=is_minor,
                    guardian_name=g_name,
                    guardian_phone=g_phone,
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
                target_age=cls.target_age or "ADULTOS",
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
    Crea una clase en la academia (adultos o kids) y bloquea automáticamente la cancha en el Calendario.
    """
    try:
        new_class = await academy_service.create_class(db, payload.model_dump())
        court_stmt = select(Court.name).where(Court.id == new_class.court_id)
        c_res = await db.execute(court_stmt)
        c_name = c_res.scalar() or "Cancha"

        return AcademyClassResponse(
            id=new_class.id,
            title=new_class.title,
            level=new_class.level,
            target_age=new_class.target_age or "ADULTOS",
            date=new_class.date.strftime("%Y-%m-%d"),
            start_time=new_class.start_time.strftime("%H:%M"),
            end_time=new_class.end_time.strftime("%H:%M"),
            court_id=str(new_class.court_id),
            court_name=c_name,
            coach_name=new_class.coach_name,
            max_students=new_class.max_students,
            price_per_student=new_class.price_per_student,
            enrolled_count=0,
            available_spots=new_class.max_students,
            enrollments=[],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/enroll")
async def enroll_student_in_class(
    payload: EnrollStudentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Inscribe a un socio o kid apadrinado en una clase de academia.
    Si el alumno es menor de edad apadrinado por un acudiente con membresía activa que incluye clases,
    aplica el cupo del acudiente ($0 COP). Si no, genera cobro pendiente.
    """
    try:
        res = await academy_service.enroll_student(db, payload.academy_class_id, payload.player_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
