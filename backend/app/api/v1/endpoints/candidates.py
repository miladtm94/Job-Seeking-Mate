import io
import json
import logging
from pathlib import Path

import pdfplumber
from fastapi import APIRouter, HTTPException, UploadFile

from app.schemas.candidate import (
    CandidateIngestRequest,
    CandidateIngestResponse,
    CandidateProfile,
)
from app.services.cv_parser import CVParserService

logger = logging.getLogger(__name__)

router = APIRouter()
cv_parser_service = CVParserService()

# JSON-backed profile store — survives backend restarts
_STORE_PATH = Path(__file__).resolve().parents[5] / "data" / "profiles.json"


def _load_profiles() -> dict[str, CandidateProfile]:
    try:
        if _STORE_PATH.exists():
            raw = json.loads(_STORE_PATH.read_text())
            return {k: CandidateProfile.model_validate(v) for k, v in raw.items()}
    except Exception:
        logger.warning("Could not load profiles from %s", _STORE_PATH)
    return {}


def _save_profiles(profiles: dict[str, CandidateProfile]) -> None:
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(
            json.dumps({k: v.model_dump() for k, v in profiles.items()}, indent=2)
        )
    except Exception:
        logger.warning("Could not save profiles to %s", _STORE_PATH)


_profiles: dict[str, CandidateProfile] = _load_profiles()


def _seed_default_pdf() -> None:
    """Auto-ingest a default PDF resume if set via DEFAULT_RESUME_PDF env var."""
    from app.core.config import get_settings
    settings = get_settings()
    pdf_path_str = getattr(settings, "default_resume_pdf", "")
    if not pdf_path_str or _profiles:
        return
    pdf_path = Path(pdf_path_str).expanduser()
    if not pdf_path.exists():
        logger.warning("DEFAULT_RESUME_PDF path not found: %s", pdf_path)
        return
    try:
        raw = pdf_path.read_bytes()
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            cv_text = "\n\n".join(p.extract_text() or "" for p in pdf.pages).strip()
        if len(cv_text) < 50:
            logger.warning("Default PDF has too little text")
            return
        payload = CandidateIngestRequest(
            name=pdf_path.stem.replace("_", " ").title(),
            email="me@example.com",
            raw_cv_text=cv_text,
            preferred_roles=[],
            locations=[],
            work_type="any",
        )
        result = cv_parser_service.parse(payload)
        _profiles[result.candidate_id] = CandidateProfile(
            candidate_id=result.candidate_id,
            name=payload.name,
            email=payload.email,
            skills=result.skills,
            domains=result.domains,
            seniority=result.seniority,
            years_experience=result.years_experience,
            preferred_roles=payload.preferred_roles,
            locations=payload.locations,
            strengths=result.strengths,
            skill_gaps=result.skill_gaps,
            raw_cv_text=cv_text,
            summary=result.summary,
        )
        _save_profiles(_profiles)
        logger.info("Auto-ingested default resume: %s", pdf_path.name)
    except Exception:
        logger.exception("Failed to auto-ingest default PDF")


_seed_default_pdf()


@router.post("/ingest", response_model=CandidateIngestResponse)
def ingest_candidate(payload: CandidateIngestRequest) -> CandidateIngestResponse:
    result = cv_parser_service.parse(payload)

    # Single-user tool — replace any previous profile with the new one
    _profiles.clear()
    _profiles[result.candidate_id] = CandidateProfile(
        candidate_id=result.candidate_id,
        name=payload.name,
        email=payload.email,
        skills=result.skills,
        domains=result.domains,
        seniority=result.seniority,
        years_experience=result.years_experience,
        preferred_roles=payload.preferred_roles,
        locations=payload.locations,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        work_type=payload.work_type,
        visa_status=payload.visa_status,
        strengths=result.strengths,
        skill_gaps=result.skill_gaps,
        raw_cv_text=payload.raw_cv_text,
        summary=result.summary,
    )
    _save_profiles(_profiles)
    return result


@router.post("/ingest-pdf", response_model=CandidateIngestResponse)
async def ingest_candidate_pdf(
    file: UploadFile,
    name: str = "",
    email: str = "",
    preferred_roles: str = "",
    locations: str = "",
    salary_min: int | None = None,
    work_type: str = "any",
) -> CandidateIngestResponse:
    """Upload a PDF resume and parse it into a candidate profile."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    raw = await file.read()
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
        cv_text = "\n\n".join(pages_text).strip()
    except Exception as exc:
        logger.exception("PDF extraction failed")
        raise HTTPException(
            status_code=422, detail=f"Could not extract text from PDF: {exc}"
        ) from exc

    if len(cv_text) < 50:
        raise HTTPException(status_code=422, detail="Could not extract enough text from the PDF")

    payload = CandidateIngestRequest(
        name=name or file.filename.replace(".pdf", "").replace("_", " ").title(),
        email=email or "unknown@example.com",
        raw_cv_text=cv_text,
        preferred_roles=[r.strip() for r in preferred_roles.split(",") if r.strip()],
        locations=[loc.strip() for loc in locations.split(",") if loc.strip()],
        salary_min=salary_min,
        work_type=work_type,
    )

    result = cv_parser_service.parse(payload)
    # Single-user tool — replace any previous profile with the new one
    _profiles.clear()
    _profiles[result.candidate_id] = CandidateProfile(
        candidate_id=result.candidate_id,
        name=payload.name,
        email=payload.email,
        skills=result.skills,
        domains=result.domains,
        seniority=result.seniority,
        years_experience=result.years_experience,
        preferred_roles=payload.preferred_roles,
        locations=payload.locations,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        work_type=payload.work_type,
        strengths=result.strengths,
        skill_gaps=result.skill_gaps,
        raw_cv_text=cv_text,
        summary=result.summary,
    )
    _save_profiles(_profiles)
    return result


def get_profile(candidate_id: str) -> CandidateProfile | None:
    """Public accessor for other endpoints to look up a profile."""
    return _profiles.get(candidate_id)


@router.get("/{candidate_id}", response_model=CandidateProfile)
def get_candidate(candidate_id: str) -> CandidateProfile:
    profile = _profiles.get(candidate_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return profile


@router.get("/", response_model=list[CandidateProfile])
def list_candidates() -> list[CandidateProfile]:
    return list(_profiles.values())
