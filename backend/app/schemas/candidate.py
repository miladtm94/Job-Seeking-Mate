from pydantic import BaseModel, EmailStr, Field


class CandidateIngestRequest(BaseModel):
    name: str
    email: EmailStr
    raw_cv_text: str = Field(min_length=50)
    preferred_roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    work_type: str = "any"  # remote | hybrid | onsite | any
    visa_status: str | None = None


class CandidateIngestResponse(BaseModel):
    candidate_id: str
    skills: list[str]
    domains: list[str]
    seniority: str
    years_experience: int
    strengths: list[str]
    skill_gaps: list[str]
    summary: str


class CandidateProfile(BaseModel):
    candidate_id: str
    name: str
    email: str
    skills: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    seniority: str = "mid"
    years_experience: int = 0
    preferred_roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    work_type: str = "any"
    visa_status: str | None = None
    strengths: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    raw_cv_text: str = ""
    summary: str = ""
