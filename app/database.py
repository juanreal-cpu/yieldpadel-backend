"""
Database module interface for YieldPadel backend.
Exposes engine, Base, AsyncSessionLocal, and get_db.
Automatically ensures all models are imported so Base.metadata is fully populated.
"""
from app.core.database import Base, engine, AsyncSessionLocal, get_db, clean_db_url

# Import all models to ensure Base.metadata contains every table definition
import app.models  # noqa: F401

__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_db",
    "clean_db_url",
]
