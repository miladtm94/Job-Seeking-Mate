import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.jats_db import get_jats_db
from app.schemas.jats import (
    AddEventRequest,
    ApplicationDetail,
    ApplicationListResponse,
    DocumentResponse,
    EventResponse,
    ExtractedJobData,
    ExtractRequest,
    LogApplicationRequest,
    UpdateApplicationRequest,
    UpdateEventRequest,
)
from app.services import jats_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/extract", response_model=ExtractedJobData)
def extract_job_description(payload: ExtractRequest) -> ExtractedJobData:
    """NLP-extract structured fields from a raw job description."""
    return jats_service.extract_job_data(payload.job_description)


@router.post("/applications", response_model=ApplicationDetail)
def log_application(
    payload: LogApplicationRequest,
    db: Session = Depends(get_jats_db),
) -> ApplicationDetail:
    """Log a new job application with full metadata."""
    return jats_service.log_application(db, payload)


@router.get("/applications", response_model=ApplicationListResponse)
def list_applications(
    status: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_jats_db),
) -> ApplicationListResponse:
    return jats_service.list_applications(
        db, status=status, platform=platform, industry=industry, search=search
    )


@router.get("/applications/{app_id}", response_model=ApplicationDetail)
def get_application(
    app_id: str,
    db: Session = Depends(get_jats_db),
) -> ApplicationDetail:
    result = jats_service.get_application(db, app_id)
    if not result:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.post("/applications/{app_id}/documents", response_model=DocumentResponse)
async def upload_document(
    app_id: str,
    category: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_jats_db),
) -> DocumentResponse:
    result = await jats_service.upload_document(db, app_id, category, file)
    if not result:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.get("/applications/{app_id}/documents/{document_id}/download")
def download_document(
    app_id: str,
    document_id: int,
    db: Session = Depends(get_jats_db),
) -> FileResponse:
    result = jats_service.get_document_download(db, app_id, document_id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    path, filename, media_type = result
    return FileResponse(path=path, filename=filename, media_type=media_type)


@router.delete("/applications/{app_id}/documents/{document_id}")
def delete_document(
    app_id: str,
    document_id: int,
    db: Session = Depends(get_jats_db),
) -> dict:
    if not jats_service.delete_document(db, app_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": document_id}


@router.patch("/applications/{app_id}", response_model=ApplicationDetail)
def update_application(
    app_id: str,
    payload: UpdateApplicationRequest,
    db: Session = Depends(get_jats_db),
) -> ApplicationDetail:
    result = jats_service.update_application(db, app_id, payload)
    if not result:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.delete("/applications/{app_id}")
def delete_application(
    app_id: str,
    db: Session = Depends(get_jats_db),
) -> dict:
    if not jats_service.delete_application(db, app_id):
        raise HTTPException(status_code=404, detail="Application not found")
    return {"deleted": app_id}


@router.post("/applications/{app_id}/events", response_model=EventResponse)
def add_event(
    app_id: str,
    payload: AddEventRequest,
    db: Session = Depends(get_jats_db),
) -> EventResponse:
    result = jats_service.add_event(db, app_id, payload)
    if not result:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.patch("/applications/{app_id}/events/{event_id}", response_model=EventResponse)
def update_event(
    app_id: str,
    event_id: int,
    payload: UpdateEventRequest,
    db: Session = Depends(get_jats_db),
) -> EventResponse:
    result = jats_service.update_event(db, app_id, event_id, payload)
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    return result


@router.delete("/applications/{app_id}/events/{event_id}")
def delete_event(
    app_id: str,
    event_id: int,
    db: Session = Depends(get_jats_db),
) -> dict:
    if not jats_service.delete_event(db, app_id, event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    return {"deleted": event_id}


@router.get("/check-duplicate")
def check_duplicate(
    company: str = Query(...),
    role: str = Query(...),
    db: Session = Depends(get_jats_db),
) -> dict:
    """Return whether an application for this company+role already exists."""
    return jats_service.check_duplicate(db, company, role)


@router.get("/applications/{app_id}/events", response_model=list[EventResponse])
def get_events(
    app_id: str,
    db: Session = Depends(get_jats_db),
) -> list[EventResponse]:
    return jats_service.get_events(db, app_id)
