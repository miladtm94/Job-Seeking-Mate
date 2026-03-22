from pydantic import BaseModel, Field


class JobSearchRequest(BaseModel):
    query: str
    locations: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=lambda: ["adzuna", "jsearch"])
    remote_only: bool = False
    salary_min: int | None = None
    max_results: int = 25
    candidate_id: str | None = None


class JobPosting(BaseModel):
    job_id: str
    title: str
    company: str
    source: str
    location: str
    description: str
    url: str
    salary: str | None = None
    match_score: int | None = None


class JobSearchResponse(BaseModel):
    jobs: list[JobPosting]
    total: int = 0
    query: str = ""


# Smart search (profile-driven, scored results)

class SmartSearchRequest(BaseModel):
    candidate_id: str
    max_results: int = 20
    remote_only: bool = False
    locations: list[str] = Field(default_factory=list)  # overrides profile locations


class ScoredJob(BaseModel):
    job: JobPosting
    match_score: int = Field(ge=0, le=100)
    key_matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    recommendation: str  # strong_apply | apply | maybe | skip
    explanation: str
    fit_reasons: list[str] = Field(default_factory=list)
    breakdown: dict = Field(default_factory=dict)


class SmartSearchResponse(BaseModel):
    scored_jobs: list[ScoredJob]
    total_found: int
    queries_used: list[str]
