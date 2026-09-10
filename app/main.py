import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.database import engine, Base
import app.models  # noqa: F401 - Register models with Base.metadata
from app.api.v1.api import api_router
from fastapi.staticfiles import StaticFiles

# Crear la carpeta de avatares si no existe
os.makedirs("app/static/uploads/avatars", exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crear tablas al iniciar la aplicación garantizando que todos los modelos existan
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            from sqlalchemy import text
            if "sqlite" in str(engine.url):
                sqlite_statements = [
                    "ALTER TABLE time_slots ADD COLUMN closed_at TIMESTAMP",
                    "ALTER TABLE time_slots ADD COLUMN slot_type VARCHAR(50) DEFAULT 'MATCH'",
                    "ALTER TABLE time_slots ADD COLUMN instructor_name VARCHAR(100)",
                    "ALTER TABLE time_slots ADD COLUMN is_promo BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE time_slots ADD COLUMN tournament_type VARCHAR(50)",
                    "ALTER TABLE time_slots ADD COLUMN prize_pool NUMERIC(10, 2)",
                    "ALTER TABLE time_slots ADD COLUMN tournament_name VARCHAR(150)",
                    "ALTER TABLE time_slots ADD COLUMN sport_type VARCHAR(50) DEFAULT 'PADEL'",
                    "ALTER TABLE time_slots ADD COLUMN winners_names VARCHAR(255)",
                    "ALTER TABLE time_slots ADD COLUMN runner_up_names VARCHAR(255)",
                    "ALTER TABLE time_slots ADD COLUMN is_finished BOOLEAN DEFAULT 0",
                    "ALTER TABLE time_slots ADD COLUMN club_id INTEGER DEFAULT 1",
                    "ALTER TABLE time_slots ADD COLUMN price_total_cop NUMERIC(10, 2)",
                    "ALTER TABLE time_slots ADD COLUMN price_per_player_cop NUMERIC(10, 2)",
                    "ALTER TABLE time_slots ADD COLUMN price NUMERIC(10, 2)",
                    "ALTER TABLE courts ADD COLUMN sport_type VARCHAR(50) DEFAULT 'PADEL'",
                    "ALTER TABLE courts ADD COLUMN max_capacity INTEGER DEFAULT 4",
                    "ALTER TABLE courts ADD COLUMN court_number INTEGER",
                    "ALTER TABLE courts ADD COLUMN club_id VARCHAR(36)",
                    "ALTER TABLE customers ADD COLUMN gender VARCHAR(20)",
                    "ALTER TABLE customers ADD COLUMN preferred_music VARCHAR(100)",
                    "ALTER TABLE customers ADD COLUMN preferred_play_time VARCHAR(100)",
                    "ALTER TABLE customers ADD COLUMN membership_plan_id INTEGER",
                    "ALTER TABLE customers ADD COLUMN membership_start_date DATE",
                    "ALTER TABLE customers ADD COLUMN membership_end_date DATE",
                    "ALTER TABLE customers ADD COLUMN academy_classes_used INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN is_minor BOOLEAN DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN birth_date DATE",
                    "ALTER TABLE customers ADD COLUMN guardian_id INTEGER",
                    "ALTER TABLE customers ADD COLUMN guardian_relationship VARCHAR(50)",
                    "ALTER TABLE customers ADD COLUMN ranking_points INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN titles_count INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN category_wins INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN consecutive_wins INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN promotion_recommended BOOLEAN DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN recommended_category VARCHAR(50)",
                    "ALTER TABLE customers ADD COLUMN total_bookings_completed INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN is_first_visit BOOLEAN DEFAULT 1",
                    "ALTER TABLE customers ADD COLUMN onboarding_status VARCHAR(50) DEFAULT 'PENDING'",
                    "ALTER TABLE academy_classes ADD COLUMN target_age VARCHAR(50) DEFAULT 'ADULTOS'",
                    "ALTER TABLE membership_plans ADD COLUMN badge_label VARCHAR(50) DEFAULT 'PLAN SOCIO'",
                    "ALTER TABLE membership_plans ADD COLUMN card_gradient VARCHAR(100) DEFAULT 'from-slate-800 to-indigo-900'",
                    "ALTER TABLE membership_plans ADD COLUMN is_active BOOLEAN DEFAULT 1",
                    "ALTER TABLE slot_holds ADD COLUMN client_tier VARCHAR(50) DEFAULT 'STANDARD'",
                    "ALTER TABLE slot_holds ADD COLUMN payment_status VARCHAR(50) DEFAULT 'PAID'",
                    "ALTER TABLE yield_bookings ADD COLUMN client_tier VARCHAR(50) DEFAULT 'STANDARD'",
                    "ALTER TABLE yield_bookings ADD COLUMN payment_status VARCHAR(50) DEFAULT 'PAID'",
                    "ALTER TABLE yield_bookings ADD COLUMN transaction_id VARCHAR(100)",
                    "ALTER TABLE users ADD COLUMN club_id VARCHAR(50) DEFAULT '2756f34a-7d24-4815-9f7e-6ed125ea5de7'",
                ]
                for stmt in sqlite_statements:
                    try:
                        await conn.execute(text(stmt))
                    except Exception:
                        pass
            else:
                pg_statements = [
                    # time_slots
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
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS winners_names VARCHAR(255)",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS runner_up_names VARCHAR(255)",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS is_finished BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS sport_type VARCHAR(50) DEFAULT 'PADEL'",
                    # courts
                    "ALTER TABLE courts ADD COLUMN IF NOT EXISTS sport_type VARCHAR(50) DEFAULT 'PADEL'",
                    "ALTER TABLE courts ADD COLUMN IF NOT EXISTS max_capacity INTEGER DEFAULT 4",
                    "ALTER TABLE courts ADD COLUMN IF NOT EXISTS court_number INTEGER",
                    "ALTER TABLE courts ADD COLUMN IF NOT EXISTS club_id UUID",
                    "ALTER TABLE courts ADD COLUMN IF NOT EXISTS is_indoor BOOLEAN DEFAULT FALSE",
                    # customers
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
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS ranking_points INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS titles_count INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS category_wins INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS consecutive_wins INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS promotion_recommended BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS recommended_category VARCHAR(50)",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS total_bookings_completed INTEGER DEFAULT 0",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_first_visit BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS onboarding_status VARCHAR(50) DEFAULT 'PENDING'",
                    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS notes VARCHAR(500)",
                    # academy_classes
                    "ALTER TABLE academy_classes ADD COLUMN IF NOT EXISTS target_age VARCHAR(50) DEFAULT 'ADULTOS'",
                    # membership_plans
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS badge_label VARCHAR(50) DEFAULT 'PLAN SOCIO'",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS card_gradient VARCHAR(100) DEFAULT 'from-slate-800 to-indigo-900'",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS start_time TIME WITHOUT TIME ZONE DEFAULT '06:00:00'",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS end_time TIME WITHOUT TIME ZONE DEFAULT '23:59:00'",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS max_daily_hours DOUBLE PRECISION DEFAULT 1.5",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS includes_academy_classes BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS monthly_classes_count INTEGER DEFAULT 0",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS includes_beverage_perk BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS americano_discount_pct INTEGER DEFAULT 0",
                    "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS monthly_price_cop INTEGER DEFAULT 0",
                    # slot_holds
                    "ALTER TABLE slot_holds ADD COLUMN IF NOT EXISTS client_tier VARCHAR(50) DEFAULT 'STANDARD'",
                    "ALTER TABLE slot_holds ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) DEFAULT 'PAID'",
                    # yield_bookings
                    "ALTER TABLE yield_bookings ADD COLUMN IF NOT EXISTS client_tier VARCHAR(50) DEFAULT 'STANDARD'",
                    "ALTER TABLE yield_bookings ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) DEFAULT 'PAID'",
                    "ALTER TABLE yield_bookings ADD COLUMN IF NOT EXISTS transaction_id VARCHAR(100)",
                    # club_presences
                    "ALTER TABLE club_presences ADD COLUMN IF NOT EXISTS membership_tier VARCHAR(50) DEFAULT 'ESTANDAR'",
                    "ALTER TABLE club_presences ADD COLUMN IF NOT EXISTS phone VARCHAR(50) DEFAULT ''",
                    # users
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS club_id VARCHAR(50) DEFAULT '2756f34a-7d24-4815-9f7e-6ed125ea5de7'",
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

# Montar carpeta static
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import logging
from pathlib import Path
from typing import Optional
from fastapi import Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.security import decode_access_token

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


def get_current_user_from_request(request: Request) -> Optional[dict]:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if token:
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            return payload
    return None


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "YieldPadel Core"}


@app.get("/")
async def serve_landing(request: Request):
    """Muestra la Landing Page comercial de YieldPadel"""
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/dashboard")
async def serve_dashboard(request: Request):
    """Acceso directo al panel operativo del club sin validación de usuario/clave"""
    response = templates.TemplateResponse("dashboard.html", {"request": request})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
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
