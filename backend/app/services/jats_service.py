import json
import logging
import re
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text
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


def _migrate_columns() -> None:
    """Add new columns to existing DBs — idempotent (ignores already-exists errors)."""
    new_cols = [
        ("jats_applications", "fit_score", "INTEGER"),
        ("jats_applications", "job_url", "TEXT"),
        ("jats_applications", "contact_name", "VARCHAR(255)"),
        ("jats_applications", "contact_email", "VARCHAR(255)"),
        ("jats_applications", "contact_linkedin", "TEXT"),
        ("jats_applications", "follow_up_date", "VARCHAR(32)"),
    ]
    with engine.connect() as conn:
        for table, col, col_type in new_cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass  # Column already exists


_migrate_columns()

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LOGS_DIR = _PROJECT_ROOT / "data" / "logs"

VALID_STATUSES = {"applied", "interview", "offer", "rejected", "withdrawn", "saved"}
STATUS_EVENT_TO_STATUS = {
    "applied": "applied",
    "interview": "interview",
    "phone_screen": "interview",
    "interview_scheduled": "interview",
    "interview_completed": "interview",
    "offer": "offer",
    "rejected": "rejected",
    "rejection": "rejected",
    "withdrawn": "withdrawn",
}

_EXTRACT_SYSTEM = (
    "You are an expert HR analyst. Extract structured information from a job description.\n"
    "Respond with ONLY a single valid JSON object — no explanation, no markdown, no extra text.\n"
    "Use null (not \"N/A\", not \"\", not \"none\") for any field that is missing.\n"
    "The JSON must have exactly these keys:\n\n"
    "{\n"
    '  "role_title": "Senior Software Engineer",\n'
    '  "company": "Acme Corp",\n'
    '  "location_city": "Sydney",\n'
    '  "location_country": "Australia",\n'
    '  "remote_type": "hybrid",\n'
    '  "salary_min": 120000,\n'
    '  "salary_max": 160000,\n'
    '  "currency": "AUD",\n'
    '  "required_skills": ["Python", "AWS", "SQL"],\n'
    '  "preferred_skills": ["Kubernetes", "GraphQL"],\n'
    '  "seniority": "senior",\n'
    '  "employment_type": "fulltime",\n'
    '  "industry": "FinTech"\n'
    "}\n\n"
    "Allowed values — remote_type: remote|hybrid|onsite|null. "
    "seniority: junior|mid|senior|staff|principal|null. "
    "employment_type: fulltime|parttime|contract|casual|null. "
    "salary_min/salary_max must be annual integers or null."
)


# ── Structured tracking-form parser (no AI required) ─────────────────────────

# Patterns that only appear in a structured tracking form, not in raw JDs
_STRUCTURED_MARKERS = [
    re.compile(r"^\s*company\s*\*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*role\s+title\s*\*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*date\s+applied\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*salary\s+min\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*salary\s+max\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*fit\s+to\s+role\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*work\s+type\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*job\s+posting\s+url\b", re.IGNORECASE | re.MULTILINE),
]

# Ordered list: (label regex, field name)
_FIELD_MAP = [
    (re.compile(r"^company$", re.IGNORECASE), "company"),
    (re.compile(r"^role\s+title$", re.IGNORECASE), "role_title"),
    (re.compile(r"^platform$", re.IGNORECASE), "platform"),
    (re.compile(r"^date\s+applied$", re.IGNORECASE), "date_applied"),
    (re.compile(r"^city$", re.IGNORECASE), "location_city"),
    (re.compile(r"^country$", re.IGNORECASE), "location_country"),
    (re.compile(r"^work\s+type$", re.IGNORECASE), "remote_type"),
    (re.compile(r"^salary\s+min$", re.IGNORECASE), "salary_min"),
    (re.compile(r"^salary\s+max$", re.IGNORECASE), "salary_max"),
    (re.compile(r"^currency$", re.IGNORECASE), "currency"),
    (re.compile(r"^industry$", re.IGNORECASE), "industry"),
    (re.compile(r"^seniority$", re.IGNORECASE), "seniority"),
    (re.compile(r"^employment\s+type$", re.IGNORECASE), "employment_type"),
    (re.compile(r"^job\s+posting\s+url$", re.IGNORECASE), "job_url"),
    (re.compile(r"^(?:recruiter\s*/\s*)?contact\s+name$", re.IGNORECASE), "contact_name"),
    (re.compile(r"^contact\s+email$", re.IGNORECASE), "contact_email"),
    (re.compile(r"^fit\s+to\s+role$", re.IGNORECASE), "fit_score"),
    (re.compile(r"^required\s+skills$", re.IGNORECASE), "required_skills"),
    (re.compile(r"^preferred\s+skills$", re.IGNORECASE), "preferred_skills"),
    (re.compile(r"^resume\s+used$", re.IGNORECASE), "resume_used"),
    (re.compile(r"^notes$", re.IGNORECASE), "notes"),
]


def _detect_structured_form(text: str) -> bool:
    """Return True if text looks like a structured application tracking form."""
    return sum(1 for p in _STRUCTURED_MARKERS if p.search(text)) >= 3


def _norm_label(raw: str) -> str:
    """Strip trailing *, optional parentheticals, and whitespace from a field label."""
    s = re.sub(r"\s*\*\s*$", "", raw)
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
    return s.strip()


def _parse_structured_form(text: str) -> ExtractedJobData:
    """Parse a structured 'Label    Value' tracking form into ExtractedJobData."""
    collected: dict[str, list[str]] = {}
    current: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip pure separator lines (═══, ----, ====, etc.)
        if not any(c.isalnum() for c in stripped):
            continue

        # Split on first run of 2+ spaces: 'Label Name    Value here'
        m = re.match(r"^(.+?)\s{2,}(.*)$", stripped)
        raw_label = m.group(1).strip() if m else stripped
        value_part = m.group(2).strip() if m else ""

        label_norm = _norm_label(raw_label)

        # Check if this line starts a known field
        matched: str | None = None
        for pat, fname in _FIELD_MAP:
            if pat.match(label_norm):
                matched = fname
                break

        if matched:
            current = matched
            collected[current] = [value_part] if value_part else []
        elif current:
            collected[current].append(stripped)

    # ── Helpers ──
    def get(f: str) -> str:
        return " ".join(collected.get(f, [])).strip()

    def clean(v: str) -> str | None:
        v = v.strip()
        return None if (not v or re.match(r"^\[.*\]$", v)) else v

    def extract_int(s: str) -> int | None:
        m2 = re.search(r"[\d,]+", s)
        if m2:
            try:
                return int(m2.group().replace(",", ""))
            except ValueError:
                return None
        return None

    def extract_fit(s: str) -> int | None:
        hits = re.findall(r"(\d+)\s*/\s*100", s)
        if hits:
            try:
                return min(100, max(0, int(hits[-1])))
            except ValueError:
                return None
        return None

    def parse_date(s: str) -> str | None:
        s = re.sub(r"\s*\([^)]*\)", "", s).strip()
        for fmt in ("%B %d, %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None

    def norm_remote(s: str) -> str | None:
        sl = s.lower()
        if "hybrid" in sl:
            return "hybrid"
        if "remote" in sl and not any(x in sl for x in ("onsite", "on-site", "office")):
            return "remote"
        if any(x in sl for x in ("onsite", "on-site", "on site", "office", "in-person")):
            return "onsite"
        return None

    def norm_seniority(s: str) -> str | None:
        sl = s.lower()
        if "principal" in sl:
            return "principal"
        if "staff" in sl:
            return "staff"
        if "senior" in sl:
            return "senior"
        if "mid" in sl:
            return "mid"
        if any(x in sl for x in ("junior", "entry", "graduate", "intern")):
            return "junior"
        return None

    def norm_employment(s: str) -> str | None:
        sl = s.lower()
        if "full" in sl:
            return "fulltime"
        if "part" in sl:
            return "parttime"
        if "contract" in sl:
            return "contract"
        if "casual" in sl:
            return "casual"
        return None

    def norm_platform(s: str) -> str | None:
        sl = s.lower()
        for p in ("linkedin", "seek", "indeed", "glassdoor"):
            if p in sl:
                return p.capitalize()
        if any(x in sl for x in ("referral", "referred")):
            return "Referral"
        if any(x in sl for x in ("direct", "company", "career")):
            return "Direct"
        first = s.split("/")[0].strip()
        return first or None

    def split_skills(s: str) -> list[str]:
        return [sk.strip() for sk in s.split(",") if sk.strip()]

    return ExtractedJobData(
        company=clean(get("company")) or "",
        role_title=clean(get("role_title")) or "",
        location_city=clean(get("location_city")),
        location_country=clean(get("location_country")),
        remote_type=norm_remote(get("remote_type")),  # type: ignore[arg-type]
        salary_min=extract_int(get("salary_min")),
        salary_max=extract_int(get("salary_max")),
        currency=clean(get("currency")),
        seniority=norm_seniority(get("seniority")),  # type: ignore[arg-type]
        employment_type=norm_employment(get("employment_type")),  # type: ignore[arg-type]
        industry=clean(get("industry")),
        required_skills=split_skills(get("required_skills")),
        preferred_skills=split_skills(get("preferred_skills")),
        platform=norm_platform(get("platform")),
        date_applied=parse_date(get("date_applied")),
        contact_name=clean(get("contact_name")),
        contact_email=clean(get("contact_email")),
        job_url=clean(get("job_url")),
        notes=clean(get("notes")),
        fit_score=extract_fit(get("fit_score")),
    )


def extract_job_data(description: str) -> ExtractedJobData:
    """Run NLP extraction on a job description. Falls back to empty model on failure."""
    if not description.strip():
        return ExtractedJobData()

    # Structured tracking-form paste: parse with regex, no AI needed
    if _detect_structured_form(description):
        logger.info("Detected structured tracking form — using regex parser")
        return _parse_structured_form(description)

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
        logger.warning("Failed to parse AI extraction JSON. Raw response was: %r", raw[:500])
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
        job_url=payload.job_url,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_linkedin=payload.contact_linkedin,
        follow_up_date=payload.follow_up_date,
        fit_score=payload.fit_score,
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

    # exclude_unset=True: status-only calls leave other fields untouched;
    # full-edit calls explicitly include None to clear optional fields.
    update_data = payload.model_dump(exclude_unset=True)

    # Pull skills out before applying scalar fields
    required_skills: list[str] | None = update_data.pop("required_skills", None)
    preferred_skills: list[str] | None = update_data.pop("preferred_skills", None)

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

    # Update skills when explicitly provided (delete all, then re-insert)
    if required_skills is not None or preferred_skills is not None:
        db.query(ApplicationSkill).filter(ApplicationSkill.application_id == app_id).delete()
        for skill in (required_skills or []):
            if skill.strip():
                db.add(ApplicationSkill(
                    application_id=app_id, skill_name=skill.strip(), skill_type="required"
                ))
        for skill in (preferred_skills or []):
            if skill.strip():
                db.add(ApplicationSkill(
                    application_id=app_id, skill_name=skill.strip(), skill_type="preferred"
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
    next_status = _status_for_event_type(payload.event_type)
    if next_status:
        entry.status = next_status
    db.commit()
    db.refresh(event)
    return _event_to_response(event)


def update_event(
    db: Session,
    app_id: str,
    event_id: int,
    payload: AddEventRequest,
) -> EventResponse | None:
    event = (
        db.query(ApplicationEvent)
        .filter(
            ApplicationEvent.id == event_id,
            ApplicationEvent.application_id == app_id,
        )
        .first()
    )
    if not event:
        return None

    event.event_type = payload.event_type
    event.event_date = payload.event_date
    event.notes = payload.notes

    entry = db.query(ApplicationEntry).filter(ApplicationEntry.id == app_id).first()
    if not entry:
        return None

    _sync_status_from_events(db, entry)
    db.commit()
    db.refresh(event)
    return _event_to_response(event)


def delete_event(db: Session, app_id: str, event_id: int) -> bool:
    event = (
        db.query(ApplicationEvent)
        .filter(
            ApplicationEvent.id == event_id,
            ApplicationEvent.application_id == app_id,
        )
        .first()
    )
    if not event:
        return False

    entry = db.query(ApplicationEntry).filter(ApplicationEntry.id == app_id).first()
    if not entry:
        return False

    db.delete(event)
    db.flush()
    _sync_status_from_events(db, entry)
    db.commit()
    return True


def get_events(db: Session, app_id: str) -> list[EventResponse]:
    events = (
        db.query(ApplicationEvent)
        .filter(ApplicationEvent.application_id == app_id)
        .order_by(ApplicationEvent.event_date.asc(), ApplicationEvent.id.asc())
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


def check_duplicate(db: Session, company: str, role: str) -> dict:
    """Return whether an application for the same company+role already exists."""
    existing = (
        db.query(ApplicationEntry)
        .filter(
            ApplicationEntry.company.ilike(company.strip()),
            ApplicationEntry.role_title.ilike(role.strip()),
        )
        .first()
    )
    if existing:
        return {
            "exists": True,
            "id": existing.id,
            "status": existing.status,
            "date_applied": existing.date_applied,
        }
    return {"exists": False}


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
        job_url=entry.job_url,
        contact_name=entry.contact_name,
        follow_up_date=entry.follow_up_date,
        fit_score=entry.fit_score,
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
        job_url=entry.job_url,
        contact_name=entry.contact_name,
        contact_email=entry.contact_email,
        contact_linkedin=entry.contact_linkedin,
        follow_up_date=entry.follow_up_date,
        fit_score=entry.fit_score,
    )


def _event_to_response(event: ApplicationEvent) -> EventResponse:
    return EventResponse(
        id=event.id,
        application_id=event.application_id,
        event_type=event.event_type,
        event_date=event.event_date,
        notes=event.notes,
    )


def _status_for_event_type(event_type: str) -> str | None:
    return STATUS_EVENT_TO_STATUS.get(event_type.strip().lower())


def _sync_status_from_events(db: Session, entry: ApplicationEntry) -> None:
    latest_status_event = (
        db.query(ApplicationEvent)
        .filter(ApplicationEvent.application_id == entry.id)
        .order_by(ApplicationEvent.event_date.desc(), ApplicationEvent.id.desc())
        .all()
    )
    for event in latest_status_event:
        synced_status = _status_for_event_type(event.event_type)
        if synced_status:
            entry.status = synced_status
            return


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
