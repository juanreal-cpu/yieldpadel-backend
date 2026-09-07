from sqlalchemy import Boolean, Column, Float, Integer, Numeric, String
from app.core.database import Base


class CompetitorClub(Base):
    __tablename__ = "competitor_clubs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    city = Column(String(100), nullable=False, index=True)
    zone = Column(String(100), nullable=True)
    address = Column(String(250), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    courts_count = Column(Integer, default=4)
    rating = Column(Float, nullable=True, default=4.5)
    phone = Column(String(50), nullable=True)
    website = Column(String(250), nullable=True)
    price_valle = Column(Numeric(10, 2), default=80000.0)
    price_pico = Column(Numeric(10, 2), default=120000.0)
    is_target_partner = Column(Boolean, default=False, index=True)
