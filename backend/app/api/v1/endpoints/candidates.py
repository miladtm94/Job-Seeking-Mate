from fastapi import APIRouter, HTTPException

from app.schemas.candidate import (
    CandidateIngestRequest,
    CandidateIngestResponse,
    CandidateProfile,
)
from app.services.cv_parser import CVParserService

router = APIRouter()
cv_parser_service = CVParserService()

# In-memory profile store (production: use DB repository)
_profiles: dict[str, CandidateProfile] = {}


@router.post("/ingest", response_model=CandidateIngestResponse)
def ingest_candidate(payload: CandidateIngestRequest) -> CandidateIngestResponse:
    result = cv_parser_service.parse(payload)

    # Store the full profile
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

    return result


@router.get("/{candidate_id}", response_model=CandidateProfile)
def get_candidate(candidate_id: str) -> CandidateProfile:
    profile = _profiles.get(candidate_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return profile


@router.get("/", response_model=list[CandidateProfile])
def list_candidates() -> list[CandidateProfile]:
    return list(_profiles.values())
