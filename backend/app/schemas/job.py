from pydantic import BaseModel, Field


class JobSearchRequest(BaseModel):
    query: str
    locations: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=lambda: ["indeed", "adzuna"])
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
