import enum
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.core.database import Base

BOGOTA_TZ = ZoneInfo("America/Bogota")


class UserRole(str, enum.Enum):
    SUPERADMIN = "SUPERADMIN"
    ADMIN_CLUB = "ADMIN_CLUB"
    STAFF_RECEPCION = "STAFF_RECEPCION"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(30), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(30), default=UserRole.STAFF_RECEPCION.value, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(BOGOTA_TZ).replace(tzinfo=None), nullable=False)
