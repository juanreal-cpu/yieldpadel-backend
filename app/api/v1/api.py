from fastapi import APIRouter
from app.api.v1.endpoints import slots, holds, webhooks, customers, tournaments, auth, audit, courts, admin

api_router = APIRouter()
api_router.include_router(slots.router, prefix="/slots", tags=["slots"])
api_router.include_router(holds.router, prefix="/holds", tags=["holds"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(tournaments.router, prefix="/tournaments", tags=["tournaments"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(courts.router, prefix="/courts", tags=["courts"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

