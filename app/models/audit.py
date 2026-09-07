from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.core.database import Base

BOGOTA_TZ = ZoneInfo("America/Bogota")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username_snapshot = Column(String(100), nullable=False, default="SISTEMA")
    action = Column(String(60), nullable=False, index=True)
    entity_name = Column(String(60), nullable=False, index=True)
    entity_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(BOGOTA_TZ).replace(tzinfo=None), nullable=False, index=True)
