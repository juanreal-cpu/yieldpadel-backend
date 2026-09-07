from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
import app.models  # noqa: F401 - Register models with Base.metadata
from app.api.v1.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crear tablas al iniciar la aplicación
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            from sqlalchemy import text
            if "sqlite" in str(engine.url):
                for col_def in [
                    "closed_at TIMESTAMP",
                    "slot_type VARCHAR(50) DEFAULT 'MATCH'",
                    "instructor_name VARCHAR(100)",
                    "is_promo BOOLEAN DEFAULT FALSE",
                    "tournament_type VARCHAR(50)",
                    "prize_pool NUMERIC(10, 2)",
                    "tournament_name VARCHAR(150)",
                    "sport_type VARCHAR(50) DEFAULT 'PADEL'",
                ]:
                    try:
                        await conn.execute(text(f"ALTER TABLE time_slots ADD COLUMN {col_def}"))
                    except Exception:
                        pass
                for court_col in [
                    "sport_type VARCHAR(50) DEFAULT 'PADEL'",
                    "max_capacity INTEGER DEFAULT 4",
                    "court_number INTEGER",
                    "club_id VARCHAR(36)",
                ]:
                    try:
                        await conn.execute(text(f"ALTER TABLE courts ADD COLUMN {court_col}"))
                    except Exception:
                        pass
            else:
                pg_statements = [
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP WITH TIME ZONE",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS slot_type VARCHAR(50) DEFAULT 'MATCH'",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS instructor_name VARCHAR(100)",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS is_promo BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS tournament_type VARCHAR(50)",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS prize_pool NUMERIC(10, 2)",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS tournament_name VARCHAR(150)",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS sport_type VARCHAR(50) DEFAULT 'PADEL'",
                    "ALTER TABLE courts ADD COLUMN IF NOT EXISTS sport_type VARCHAR(50) DEFAULT 'PADEL'",
                    "ALTER TABLE courts ADD COLUMN IF NOT EXISTS max_capacity INTEGER DEFAULT 4",
                    "ALTER TABLE courts ADD COLUMN IF NOT EXISTS court_number INTEGER",
                ]
                for stmt in pg_statements:
                    try:
                        await conn.execute(text(stmt))
                        await conn.commit()
                    except Exception:
                        await conn.rollback()
        except Exception:
            pass
    yield
    # Limpieza al apagar la aplicación
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import logging
from pathlib import Path
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.templates.dashboard_html import DASHBOARD_HTML, RECEPTION_DASHBOARD_HTML

logger = logging.getLogger("yieldpadel.dashboard")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def load_dashboard_html() -> str:
    """
    Resolve and return dashboard HTML directly from template file with fallback.
    """
    dashboard_path = TEMPLATES_DIR / "dashboard.html"
    if dashboard_path.is_file():
        try:
            return dashboard_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read dashboard template from {dashboard_path}: {e}")
    return RECEPTION_DASHBOARD_HTML


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "YieldPadel Core"}


@app.get("/dashboard", response_class=HTMLResponse, tags=["frontend"])
@app.get("/", response_class=HTMLResponse, tags=["frontend"])
async def serve_dashboard(request: Request):
    try:
        try:
            response = templates.TemplateResponse(request=request, name="dashboard.html")
        except TypeError:
            response = templates.TemplateResponse("dashboard.html", {"request": request})
    except Exception as e:
        logger.warning(f"Jinja template error, fallback to direct file read: {e}")
        response = HTMLResponse(content=load_dashboard_html(), status_code=200, media_type="text/html")

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


from app.api.v1.endpoints import whatsapp, radar
from app.core.database import get_db
from app.schemas.slot import ClubConfigRequest
from app.api.v1.endpoints.slots import update_club_configuration, get_club_configuration
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(whatsapp.router, prefix="/api/v1/whatsapp", tags=["whatsapp"])
app.include_router(radar.router, prefix="/api/v1/radar", tags=["Radar & Market Analytics"])


@app.post("/api/v1/admin/club-settings", tags=["admin"])
async def admin_update_club_settings(
    payload: ClubConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    return await update_club_configuration(payload, db)


@app.get("/api/v1/admin/club-settings", tags=["admin"])
async def admin_get_club_settings(
    db: AsyncSession = Depends(get_db),
):
    return await get_club_configuration(db)