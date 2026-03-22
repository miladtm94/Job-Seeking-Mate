import json
import logging
import re
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.ai_client import ai_complete
from app.db import jats_models  # noqa: F401 — registers ORM models
from app.db.jats_db import JATSBase, engine
from app.db.jats_models import (
    ApplicationEntry,
    ApplicationEvent,
    ApplicationMaterial,
    ApplicationSkill,
)
from app.schemas.jats import (
    AddEventRequest,
    ApplicationDetail,
    ApplicationListResponse,
    ApplicationSummary,
    EventResponse,
    ExtractedJobData,
    LogApplicationRequest,
    SkillResponse,
    UpdateApplicationRequest,
)

logger = logging.getLogger(__name__)

# Create tables on first import
JATSBase.metadata.create_all(bind=engine)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LOGS_DIR = _PROJECT_ROOT / "data" / "logs"

VALID_STATUSES = {"applied", "interview", "offer", "rejected", "withdrawn", "saved"}

_EXTRACT_SYSTEM = (
    "You are an expert HR analyst. Extract structured information from job descriptions. "
    "Return ONLY valid JSON with these exact keys (use null for missing values):\n"
    "role_title (string), company (string), location_city (string|null), "
    "location_country (string|null), remote_type (remote|hybrid|onsite|null), "
    "salary_min (integer|null, annual), salary_max (integer|null, annual), "
    "currency (e.g. USD/AUD/GBP|null), required_skills (array of strings), "
    "preferred_skills (array of strings), "
    "seniority (junior|mid|senior|staff|principal|null), "
    "employment_type (fulltime|parttime|contract|casual|null), "
    "industry (e.g. FinTech/Healthcare/AI-ML/E-commerce/Consulting/null)"
)


def extract_job_data(description: str) -> ExtractedJobData:
    """Run NLP extraction on a job description. Falls back to empty model on failure."""
    if not description.strip():
        return ExtractedJobData()

    raw = ai_complete(_EXTRACT_SYSTEM, description[:4000], max_tokens=1024)
    if not raw:
        logger.info("AI not available — returning empty extraction")
        return ExtractedJobData()

    try:
        text = raw.strip()
        # Strip markdown fences
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        else:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                text = text[start: end + 1]
        data = json.loads(text)
        return ExtractedJobData.model_validate(data)
    except Exception:
        logger.warning("Failed to parse AI extraction JSON, returning empty")
        return ExtractedJobData()


def log_application(db: Session, payload: LogApplicationRequest) -> ApplicationDetail:
    """Full pipeline: save application to DB + JSON backup."""
    app_id = f"jats_{uuid.uuid4().hex[:12]}"

    entry = ApplicationEntry(
        id=app_id,
        company=payload.company,
        role_title=payload.role_title,
        platform=payload.platform,
        date_applied=payload.date_applied or date.today().isoformat(),
        status=payload.status,
        location_city=payload.location_city,
        location_country=payload.location_country,
        remote_type=payload.remote_type,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        currency=payload.currency,
        industry=payload.industry,
        seniority=payload.seniority,
        employment_type=payload.employment_type,
        description_raw=payload.description_raw,
        notes=payload.notes,
    )
    db.add(entry)

    for skill in payload.required_skills:
        if skill.strip():
            db.add(ApplicationSkill(
                application_id=app_id,
                skill_name=skill.strip(),
                skill_type="required",
            ))
    for skill in payload.preferred_skills:
        if skill.strip():
            db.add(ApplicationSkill(
                application_id=app_id,
                skill_name=skill.strip(),
                skill_type="preferred",
            ))

    if payload.resume_used or payload.cover_letter or payload.answers_text:
        db.add(ApplicationMaterial(
            application_id=app_id,
            resume_used=payload.resume_used,
            cover_letter=payload.cover_letter,
            answers_text=payload.answers_text,
        ))

    # Auto-add an "applied" event
    db.add(ApplicationEvent(
        application_id=app_id,
        event_type="applied",
        event_date=payload.date_applied or date.today().isoformat(),
        notes="Application submitted",
    ))

    db.commit()
    db.refresh(entry)

    _write_json_backup(app_id, payload)

    logger.info("Logged application %s: %s at %s", app_id, payload.role_title, payload.company)
    return _to_detail(entry)


def list_applications(
    db: Session,
    status: str | None = None,
    platform: str | None = None,
    industry: str | None = None,
    search: str | None = None,
) -> ApplicationListResponse:
    q = db.query(ApplicationEntry)
    if status:
        q = q.filter(ApplicationEntry.status == status)
    if platform:
        q = q.filter(ApplicationEntry.platform == platform)
    if industry:
        q = q.filter(ApplicationEntry.industry == industry)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            ApplicationEntry.company.ilike(term)
            | ApplicationEntry.role_title.ilike(term)
        )
    entries = q.order_by(ApplicationEntry.date_applied.desc()).all()
    return ApplicationListResponse(
        applications=[_to_summary(e) for e in entries],
        total=len(entries),
    )


def get_application(db: Session, app_id: str) -> ApplicationDetail | None:
    entry = db.query(ApplicationEntry).filter(ApplicationEntry.id == app_id).first()
    if not entry:
        return None
    return _to_detail(entry)


def update_application(
    db: Session, app_id: str, payload: UpdateApplicationRequest
) -> ApplicationDetail | None:
    entry = db.query(ApplicationEntry).filter(ApplicationEntry.id == app_id).first()
    if not entry:
        return None

    update_data = payload.model_dump(exclude_none=True)
    old_status = entry.status
    for field, value in update_data.items():
        setattr(entry, field, value)

    # Auto-add event on status change
    new_status = update_data.get("status")
    if new_status and new_status != old_status:
        db.add(ApplicationEvent(
            application_id=app_id,
            event_type=new_status,
            event_date=date.today().isoformat(),
            notes=f"Status changed to {new_status}",
        ))

    db.commit()
    db.refresh(entry)
    return _to_detail(entry)


def add_event(db: Session, app_id: str, payload: AddEventRequest) -> EventResponse | None:
    entry = db.query(ApplicationEntry).filter(ApplicationEntry.id == app_id).first()
    if not entry:
        return None
    event = ApplicationEvent(
        application_id=app_id,
        event_type=payload.event_type,
        event_date=payload.event_date,
        notes=payload.notes,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_to_response(event)


def get_events(db: Session, app_id: str) -> list[EventResponse]:
    events = (
        db.query(ApplicationEvent)
        .filter(ApplicationEvent.application_id == app_id)
        .order_by(ApplicationEvent.event_date.asc())
        .all()
    )
    return [_event_to_response(e) for e in events]


def delete_application(db: Session, app_id: str) -> bool:
    entry = db.query(ApplicationEntry).filter(ApplicationEntry.id == app_id).first()
    if not entry:
        return False
    db.delete(entry)
    db.commit()
    return True


# ── Private helpers ──────────────────────────────────────────────────────────

def _to_summary(entry: ApplicationEntry) -> ApplicationSummary:
    required = [s.skill_name for s in entry.skills if s.skill_type == "required"]
    return ApplicationSummary(
        id=entry.id,
        company=entry.company,
        role_title=entry.role_title,
        platform=entry.platform,
        date_applied=entry.date_applied,
        status=entry.status,
        location_city=entry.location_city,
        location_country=entry.location_country,
        remote_type=entry.remote_type,
        salary_min=entry.salary_min,
        salary_max=entry.salary_max,
        currency=entry.currency,
        industry=entry.industry,
        seniority=entry.seniority,
        employment_type=entry.employment_type,
        created_at=entry.created_at.isoformat() if entry.created_at else "",
        required_skills=required,
    )


def _to_detail(entry: ApplicationEntry) -> ApplicationDetail:
    skills = [SkillResponse(skill_name=s.skill_name, skill_type=s.skill_type) for s in entry.skills]
    events = [_event_to_response(e) for e in sorted(entry.events, key=lambda x: x.event_date)]
    material = entry.materials[0] if entry.materials else None
    return ApplicationDetail(
        id=entry.id,
        company=entry.company,
        role_title=entry.role_title,
        platform=entry.platform,
        date_applied=entry.date_applied,
        status=entry.status,
        location_city=entry.location_city,
        location_country=entry.location_country,
        remote_type=entry.remote_type,
        salary_min=entry.salary_min,
        salary_max=entry.salary_max,
        currency=entry.currency,
        industry=entry.industry,
        seniority=entry.seniority,
        employment_type=entry.employment_type,
        description_raw=entry.description_raw,
        notes=entry.notes,
        created_at=entry.created_at.isoformat() if entry.created_at else "",
        required_skills=[s.skill_name for s in entry.skills if s.skill_type == "required"],
        skills=skills,
        events=events,
        resume_used=material.resume_used if material else "",
        cover_letter=material.cover_letter if material else "",
        answers_text=material.answers_text if material else "",
    )


def _event_to_response(event: ApplicationEvent) -> EventResponse:
    return EventResponse(
        id=event.id,
        application_id=event.application_id,
        event_type=event.event_type,
        event_date=event.event_date,
        notes=event.notes,
    )


def _write_json_backup(app_id: str, payload: LogApplicationRequest) -> None:
    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        path = _LOGS_DIR / f"{app_id}.json"
        path.write_text(
            json.dumps(payload.model_dump(), indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        logger.warning("Could not write JSON backup for %s", app_id)
