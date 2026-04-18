from pydantic import BaseModel, EmailStr, Field


class CandidateSkillClusters(BaseModel):
    programming: list[str] = Field(default_factory=list)
    ml_ai: list[str] = Field(default_factory=list)
    data: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


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
    skill_clusters: CandidateSkillClusters = Field(default_factory=CandidateSkillClusters)
    domains: list[str]
    industries: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    seniority: str
    years_experience: int
    keywords: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    strengths: list[str]
    skill_gaps: list[str]
    summary: str


class CandidateProfile(BaseModel):
    candidate_id: str
    name: str
    email: str
    skills: list[str] = Field(default_factory=list)
    skill_clusters: CandidateSkillClusters = Field(default_factory=CandidateSkillClusters)
    domains: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    seniority: str = "mid"
    years_experience: int = 0
    target_roles: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    work_type: str = "any"
    visa_status: str | None = None
    strengths: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    raw_cv_text: str = ""
    summary: str = ""
    filename: str = ""     # original uploaded filename, e.g. "resume_ml.pdf"
    pdf_path: str = ""     # absolute path to the saved PDF on disk — used for file upload during application
