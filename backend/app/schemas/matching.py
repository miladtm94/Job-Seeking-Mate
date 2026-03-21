from pydantic import BaseModel, Field


class CandidateForMatch(BaseModel):
    skills: list[str]
    years_experience: int = Field(ge=0)
    locations: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    seniority: str = "mid"
    salary_min: int | None = None


class JobForMatch(BaseModel):
    job_id: str = ""
    title: str
    company: str = ""
    required_skills: list[str]
    preferred_skills: list[str] = Field(default_factory=list)
    location: str
    description: str = ""
    salary: str | None = None


class MatchScoreRequest(BaseModel):
    candidate: CandidateForMatch
    job: JobForMatch


class MatchBreakdown(BaseModel):
    skill_score: float = 0
    experience_score: float = 0
    domain_score: float = 0
    location_score: float = 0
    seniority_score: float = 0


class MatchScoreResponse(BaseModel):
    job_id: str = ""
    match_score: int = Field(ge=0, le=100)
    key_matching_skills: list[str]
    missing_skills: list[str]
    recommendation: str
    probability_of_success: float = Field(ge=0.0, le=1.0)
    explanation: str
    fit_reasons: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    breakdown: MatchBreakdown = Field(default_factory=MatchBreakdown)


class BatchMatchRequest(BaseModel):
    candidate: CandidateForMatch
    jobs: list[JobForMatch]


class BatchMatchResponse(BaseModel):
    results: list[MatchScoreResponse]
    rejected_count: int = 0
