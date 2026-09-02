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


import os
from fastapi.responses import FileResponse, HTMLResponse

FRONTEND_DASHBOARD = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dashboard.html")
)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "YieldPadel Core"}


@app.get("/dashboard", response_class=HTMLResponse, tags=["frontend"])
@app.get("/", response_class=HTMLResponse, tags=["frontend"])
async def serve_dashboard():
    if os.path.exists(FRONTEND_DASHBOARD):
        return FileResponse(FRONTEND_DASHBOARD, media_type="text/html")
    return HTMLResponse("<h1>Dashboard de Recepción no encontrado</h1>", status_code=404)


from app.api.v1.endpoints import whatsapp_webhook

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(whatsapp_webhook.router, prefix="/api/v1/whatsapp", tags=["whatsapp"])