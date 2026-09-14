from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.core.database import Base

BOGOTA_TZ = ZoneInfo("America/Bogota")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, nullable=True, default=1)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    operator_user = Column(String(100), nullable=True, default="RECEPCION")
    username_snapshot = Column(String(100), nullable=False, default="SISTEMA")
    action = Column(String(60), nullable=False, index=True)
    entity = Column(String(100), nullable=True, index=True)
    entity_name = Column(String(60), nullable=False, index=True, default="SYSTEM")
    entity_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(BOGOTA_TZ).replace(tzinfo=None), nullable=True, index=True)

