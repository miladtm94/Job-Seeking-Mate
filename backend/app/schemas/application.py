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


class ApplicationGenerateResponse(BaseModel):
    application_id: str = ""
    customized_resume: str
    tailored_cover_letter: str
    talking_points: list[str] = Field(default_factory=list)
    readiness_checklist: list[str] = Field(default_factory=list)
    match_score: int | None = None
    mode: str = "manual"
    status: str = "prepared"


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
