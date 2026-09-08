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
                for cust_col in [
                    "gender VARCHAR(20)",
                    "preferred_music VARCHAR(100)",
                    "preferred_play_time VARCHAR(100)",
                    "membership_plan_id INTEGER",
                    "membership_start_date DATE",
                    "membership_end_date DATE",
                    "academy_classes_used INTEGER DEFAULT 0",
                    "is_minor BOOLEAN DEFAULT 0",
                    "birth_date DATE",
                    "guardian_id INTEGER",
                    "guardian_relationship VARCHAR(50)",
                ]:
                    try:
                        await conn.execute(text(f"ALTER TABLE customers ADD COLUMN {cust_col}"))
                    except Exception:
                        pass
                for acad_col in [
                    "target_age VARCHAR(50) DEFAULT 'ADULTOS'",
                ]:
                    try:
                        await conn.execute(text(f"ALTER TABLE academy_classes ADD COLUMN {acad_col}"))
                    except Exception:
                        pass
                for slot_col in [
                    "club_id INTEGER DEFAULT 1",
                    "price_total_cop NUMERIC(10, 2)",
                    "price_per_player_cop NUMERIC(10, 2)",
                    "price NUMERIC(10, 2)",
                ]:
                    try:
                        await conn.execute(text(f"ALTER TABLE time_slots ADD COLUMN {slot_col}"))
                    except Exception:
                        pass
                for plan_col in [
                    "badge_label VARCHAR(50) DEFAULT 'PLAN SOCIO'",
                    "card_gradient VARCHAR(100) DEFAULT 'from-slate-800 to-indigo-900'",
                    "is_active BOOLEAN DEFAULT 1",
                ]:
                    try:
                        await conn.execute(text(f"ALTER TABLE membership_plans ADD COLUMN {plan_col}"))
                    except Exception:
                        pass
            else:
                pg_statements = [
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS club_id INTEGER DEFAULT 1",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS price_total_cop NUMERIC(10, 2)",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS price_per_player_cop NUMERIC(10, 2)",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2)",
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
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS membership_tier VARCHAR(50) DEFAULT 'ESTANDAR'",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS gender VARCHAR(20)",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS preferred_music VARCHAR(100)",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS preferred_play_time VARCHAR(100)",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS membership_plan_id INTEGER",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS membership_start_date DATE",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS membership_end_date DATE",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS academy_classes_used INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_minor BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS birth_date DATE",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS guardian_id INTEGER",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS guardian_relationship VARCHAR(50)",
                    "ALTER TABLE academy_classes ADD COLUMN IF NOT EXISTS target_age VARCHAR(50) DEFAULT 'ADULTOS'",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS badge_label VARCHAR(50) DEFAULT 'PLAN SOCIO'",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS card_gradient VARCHAR(100) DEFAULT 'from-slate-800 to-indigo-900'",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
                ]
                for stmt in pg_statements:
                    try:
                        await conn.execute(text(stmt))
                    except Exception:
                        pass
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

logger = logging.getLogger("yieldpadel.dashboard")

class SafeJinja2Templates(Jinja2Templates):
    def TemplateResponse(self, *args, **kwargs):
        if args and isinstance(args[0], str):
            name = args[0]
            context = args[1] if len(args) > 1 else kwargs.pop("context", {})
            req = context.get("request") if isinstance(context, dict) else kwargs.pop("request", None)
            return super().TemplateResponse(request=req, name=name, context=context, **kwargs)
        return super().TemplateResponse(*args, **kwargs)

templates = SafeJinja2Templates(directory="app/templates")


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "YieldPadel Core"}


@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    response = templates.TemplateResponse("dashboard.html", {"request": request})
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
