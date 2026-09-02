from fastapi import APIRouter
from app.api.v1.endpoints import slots, holds, webhooks

api_router = APIRouter()
api_router.include_router(slots.router, prefix="/slots", tags=["slots"])
api_router.include_router(holds.router, prefix="/holds", tags=["holds"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])