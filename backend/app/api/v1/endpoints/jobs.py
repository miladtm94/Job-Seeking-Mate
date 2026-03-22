import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas.job import (
    JobSearchRequest,
    JobSearchResponse,
    ScoredJob,
    SmartSearchRequest,
    SmartSearchResponse,
)
from app.schemas.matching import CandidateForMatch, JobForMatch, MatchScoreRequest
from app.services.job_discovery import JobDiscoveryService
from app.services.matcher import MatchingService

logger = logging.getLogger(__name__)
router = APIRouter()
job_discovery_service = JobDiscoveryService()
matching_service = MatchingService()

# Maps domain keywords → plausible job title fragments
_DOMAIN_TITLE_MAP = [
    ({"machine learning", "deep learning", "ai", "neural"},
     ["Machine Learning Engineer", "AI Engineer"]),
    ({"data", "analytics", "data science"},
     ["Data Scientist", "Data Analyst"]),
    ({"signal processing", "wireless", "rf", "radar", "communications"},
     ["Signal Processing Engineer", "RF Engineer"]),
    ({"computer vision", "image"},
     ["Computer Vision Engineer"]),
    ({"nlp", "natural language"},
     ["NLP Engineer", "ML Engineer"]),
    ({"optimization", "operations research"},
     ["Optimization Engineer", "Research Scientist"]),
    ({"software", "backend", "systems"},
     ["Software Engineer"]),
    ({"research"},
     ["Research Scientist", "Research Engineer"]),
]

_SENIORITY_PREFIX = {
    "junior": "Junior ", "mid": "", "senior": "Senior ",
    "staff": "Staff ", "principal": "Principal ",
}


def _infer_queries(seniority: str, domains: list[str], skills: list[str]) -> list[str]:
    """Generate meaningful job title queries from a profile when preferred_roles is empty."""
    domains_text = " ".join(d.lower() for d in domains)
    prefix = _SENIORITY_PREFIX.get(seniority, "")
    titles: list[str] = []
    for keywords, candidates in _DOMAIN_TITLE_MAP:
        if any(kw in domains_text for kw in keywords):
            titles.extend(f"{prefix}{t}" for t in candidates)
        if len(titles) >= 3:
            break
    if not titles:
        top = skills[0] if skills else "Software"
        titles = [f"{prefix}{top} Engineer"]
    return titles[:3]


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


@router.post("/smart-search", response_model=SmartSearchResponse)
def smart_search(payload: SmartSearchRequest) -> SmartSearchResponse:
    """Profile-driven job search: auto-queries from preferred roles, scores every result."""
    from app.api.v1.endpoints.candidates import get_profile

    profile = get_profile(payload.candidate_id)
    if not profile:
        raise HTTPException(
            status_code=404, detail="Candidate not found — upload your resume first"
        )

    # Build queries from preferred roles; fall back to domain-aware job titles
    if profile.preferred_roles:
        queries = profile.preferred_roles[:3]
    else:
        queries = _infer_queries(profile.seniority, profile.domains, profile.skills)
    logger.info("Smart search queries: %s", queries)
    locations = payload.locations or profile.locations

    # Search each query and deduplicate by title+company
    all_jobs = []
    for query in queries:
        result = job_discovery_service.search(
            JobSearchRequest(
                query=query,
                locations=locations,
                remote_only=payload.remote_only,
                max_results=payload.max_results,
            )
        )
        all_jobs.extend(result.jobs)

    seen: set[str] = set()
    unique_jobs = []
    for job in all_jobs:
        key = f"{job.title.lower().strip()}|{job.company.lower().strip()}"
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)

    candidate_for_match = CandidateForMatch(
        skills=profile.skills,
        years_experience=profile.years_experience,
        locations=profile.locations,
        preferred_roles=profile.preferred_roles,
        domains=profile.domains,
        seniority=profile.seniority,
        salary_min=profile.salary_min,
    )
    candidate_skills_lower = {s.lower() for s in profile.skills}

    scored: list[ScoredJob] = []
    for job in unique_jobs:
        # Fast skill match: find which candidate skills appear in title + description
        searchable = (job.title + " " + job.description).lower()
        matching = sorted(s for s in candidate_skills_lower if s in searchable)
        missing = sorted(candidate_skills_lower - set(matching))

        score_result = matching_service.score(
            MatchScoreRequest(
                candidate=candidate_for_match,
                job=JobForMatch(
                    job_id=job.job_id,
                    title=job.title,
                    company=job.company,
                    required_skills=matching,
                    preferred_skills=[],
                    location=job.location,
                    description=job.description,
                    salary=job.salary,
                ),
            ),
            fast=True,
        )
        scored.append(
            ScoredJob(
                job=job,
                match_score=score_result.match_score,
                key_matching_skills=[s.title() for s in matching[:8]],
                missing_skills=[s.title() for s in missing[:6]],
                recommendation=score_result.recommendation,
                explanation=score_result.explanation,
                fit_reasons=score_result.fit_reasons,
                breakdown=score_result.breakdown.model_dump(),
            )
        )

    scored.sort(key=lambda x: x.match_score, reverse=True)
    return SmartSearchResponse(
        scored_jobs=scored,
        total_found=len(unique_jobs),
        queries_used=queries,
    )
