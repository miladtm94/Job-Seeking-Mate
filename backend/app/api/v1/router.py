from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    applications,
    candidates,
    health,
    jats,
    jobs,
    matching,
    orchestrator,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(matching.router, prefix="/matching", tags=["matching"])
api_router.include_router(applications.router, prefix="/applications", tags=["applications"])
api_router.include_router(orchestrator.router, prefix="/orchestrator", tags=["orchestrator"])
api_router.include_router(jats.router, prefix="/jats", tags=["jats"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
