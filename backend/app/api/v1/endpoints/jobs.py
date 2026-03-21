from fastapi import APIRouter, Query

from app.schemas.job import JobSearchRequest, JobSearchResponse
from app.services.job_discovery import JobDiscoveryService

router = APIRouter()
job_discovery_service = JobDiscoveryService()


@router.post("/search", response_model=JobSearchResponse)
def search_jobs(payload: JobSearchRequest) -> JobSearchResponse:
    return job_discovery_service.search(payload)


@router.get("/search", response_model=JobSearchResponse)
def search_jobs_get(
    query: str = Query(..., min_length=1),
    location: str = Query(default=""),
    remote_only: bool = Query(default=False),
    salary_min: int | None = Query(default=None),
    max_results: int = Query(default=25, le=50),
) -> JobSearchResponse:
    payload = JobSearchRequest(
        query=query,
        locations=[location] if location else [],
        remote_only=remote_only,
        salary_min=salary_min,
        max_results=max_results,
    )
    return job_discovery_service.search(payload)
