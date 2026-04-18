from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    analytics,
    applications,
    auth,
    candidates,
    credentials,
    health,
    jats,
    jobs,
    matching,
    orchestrator,
    settings,
    tailor,
)
from app.core.security import require_auth

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(matching.router, prefix="/matching", tags=["matching"])
api_router.include_router(
    applications.router, prefix="/applications", tags=["applications"]
)
api_router.include_router(orchestrator.router, prefix="/orchestrator", tags=["orchestrator"])
api_router.include_router(credentials.router)   # prefix set on the router itself
api_router.include_router(
    jats.router,
    prefix="/jats",
    tags=["jats"],
    dependencies=[Depends(require_auth)],
)
api_router.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_auth)],
)
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(tailor.router, prefix="/tailor", tags=["tailor"])
