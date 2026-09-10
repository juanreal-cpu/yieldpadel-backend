from fastapi import APIRouter
from app.api.v1.endpoints import slots, holds, webhooks, customers, tournaments, auth, audit, courts, admin, analytics, pos, access, memberships, academy

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
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(pos.router, prefix="/pos", tags=["pos"])
api_router.include_router(access.router, prefix="/access", tags=["access"])

api_router.include_router(memberships.router, prefix="/memberships", tags=["memberships"])
api_router.include_router(academy.router, prefix="/academy", tags=["academy"])

# Ruta pública de clubes y sedes para selector multi-tenant
api_router.add_api_route("/clubs/public", auth.get_public_clubs, methods=["GET"], tags=["clubs"], response_model=auth.List[auth.ClubPublicResponse])
