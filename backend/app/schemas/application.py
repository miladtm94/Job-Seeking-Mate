from datetime import UTC, datetime

from pydantic import BaseModel, Field


class CandidateProfileInput(BaseModel):
    name: str
    skills: list[str]
    experience_summary: str
    raw_cv_text: str = ""
    seniority: str = "mid"


class JobInput(BaseModel):
    job_id: str = ""
    title: str
    company: str
    description: str
    location: str = ""
    salary: str | None = None
    url: str = ""


class ApplicationGenerateRequest(BaseModel):
    candidate_profile: CandidateProfileInput
    job: JobInput
    mode: str = "manual"  # manual | assisted | auto
    match_score: int | None = None  # used by Step 4 decision logic


class ApplicationGenerateResponse(BaseModel):
    application_id: str = ""
    customized_resume: str
    tailored_cover_letter: str
    talking_points: list[str] = Field(default_factory=list)
    readiness_checklist: list[str] = Field(default_factory=list)
    match_score: int | None = None
    mode: str = "manual"
    status: str = "prepared"
    # Expert recruiter workflow fields
    decision: str = "use_as_is"  # use_as_is | improve | new_resume_needed | do_not_apply
    shortlisting_probability: str = "Medium"
    strategic_positioning: list[str] = Field(default_factory=list)
    recruiter_risks: list[str] = Field(default_factory=list)
    ats_keywords: dict[str, str] = Field(default_factory=dict)
    resume_improvements: list[str] = Field(default_factory=list)


class ApplicationRecord(BaseModel):
    application_id: str
    candidate_id: str
    job_id: str
    company: str
    role: str
    match_score: int
    status: str = "saved"  # saved | prepared | applied | interview | rejected | offer
    mode: str = "manual"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str = ""


class ApplicationStatusUpdate(BaseModel):
    status: str
    notes: str = ""


class ApplicationListResponse(BaseModel):
    applications: list[ApplicationRecord]
    total: int = 0
