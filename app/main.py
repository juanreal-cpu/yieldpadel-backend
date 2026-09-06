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
                await conn.execute(text("ALTER TABLE time_slots ADD COLUMN closed_at TIMESTAMP"))
            else:
                await conn.execute(text("ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP WITH TIME ZONE"))
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
from fastapi.responses import HTMLResponse
from app.templates.dashboard_html import DASHBOARD_HTML, RECEPTION_DASHBOARD_HTML

logger = logging.getLogger("yieldpadel.dashboard")

BASE_DIR = Path(__file__).resolve().parent

# Candidate paths for the reception dashboard HTML template
DASHBOARD_CANDIDATE_PATHS = [
    BASE_DIR / "templates" / "dashboard.html",
    BASE_DIR.parent / "frontend" / "dashboard.html",
    Path("frontend/dashboard.html").resolve(),
]


def load_dashboard_html() -> str:
    """
    Resolve and return dashboard HTML with fallback to embedded RECEPTION_DASHBOARD_HTML.
    Guarantees that Render / Cloud deployments always serve the complete dark mode view.
    """
    for path in DASHBOARD_CANDIDATE_PATHS:
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read dashboard template from {path}: {e}")
    return RECEPTION_DASHBOARD_HTML


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "YieldPadel Core"}


@app.get("/dashboard", response_class=HTMLResponse, tags=["frontend"])
@app.get("/", response_class=HTMLResponse, tags=["frontend"])
async def serve_dashboard():
    html_content = load_dashboard_html()
    return HTMLResponse(content=html_content, status_code=200, media_type="text/html")


from app.api.v1.endpoints import whatsapp, radar

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(whatsapp.router, prefix="/api/v1/whatsapp", tags=["whatsapp"])
app.include_router(radar.router, prefix="/api/v1/radar", tags=["Radar & Market Analytics"])