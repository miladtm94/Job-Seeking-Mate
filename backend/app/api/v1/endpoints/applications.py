from fastapi import APIRouter, HTTPException, Query

from app.schemas.application import (
    ApplicationGenerateRequest,
    ApplicationGenerateResponse,
    ApplicationListResponse,
    ApplicationRecord,
    ApplicationStatusUpdate,
)
from app.services.application_automation import ApplicationAutomationService
from app.services.tracker import tracker

router = APIRouter()
application_automation_service = ApplicationAutomationService()


@router.post("/generate", response_model=ApplicationGenerateResponse)
def generate_application(payload: ApplicationGenerateRequest) -> ApplicationGenerateResponse:
    return application_automation_service.generate(payload)


@router.get("/", response_model=ApplicationListResponse)
def list_applications(
    candidate_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> ApplicationListResponse:
    return tracker.list_all(candidate_id=candidate_id, status=status)


@router.get("/stats")
def application_stats(candidate_id: str | None = Query(default=None)) -> dict:
    return tracker.get_stats(candidate_id=candidate_id)


@router.get("/{application_id}", response_model=ApplicationRecord)
def get_application(application_id: str) -> ApplicationRecord:
    record = tracker.get(application_id)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")
    return record


@router.patch("/{application_id}/status", response_model=ApplicationRecord)
def update_application_status(
    application_id: str, update: ApplicationStatusUpdate
) -> ApplicationRecord:
    try:
        record = tracker.update_status(application_id, update.status, update.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")
    return record
