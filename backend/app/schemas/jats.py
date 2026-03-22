from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


# ── NLP Extraction ──────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    job_description: str


class ExtractedJobData(BaseModel):
    role_title: str = ""
    company: str = ""
    location_city: str | None = None
    location_country: str | None = None
    remote_type: Literal["remote", "hybrid", "onsite"] | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    seniority: Literal["junior", "mid", "senior", "staff", "principal"] | None = None
    employment_type: Literal["fulltime", "parttime", "contract", "casual"] | None = None
    industry: str | None = None


# ── Application Logging ──────────────────────────────────────────────────────

class LogApplicationRequest(BaseModel):
    company: str
    role_title: str
    platform: str = ""
    date_applied: str = Field(default_factory=lambda: date.today().isoformat())
    status: str = "applied"

    location_city: str | None = None
    location_country: str | None = None
    remote_type: str | None = None

    salary_min: int | None = None
    salary_max: int | None = None
    currency: str = "AUD"

    industry: str | None = None
    seniority: str | None = None
    employment_type: str | None = None

    description_raw: str = ""
    resume_used: str = ""
    cover_letter: str = ""
    answers_text: str = ""
    notes: str = ""

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)


class UpdateApplicationRequest(BaseModel):
    status: str | None = None
    notes: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str | None = None
    location_city: str | None = None
    location_country: str | None = None
    remote_type: str | None = None
    industry: str | None = None
    seniority: str | None = None
    employment_type: str | None = None
    platform: str | None = None


# ── Events ───────────────────────────────────────────────────────────────────

class AddEventRequest(BaseModel):
    event_type: str
    event_date: str = Field(default_factory=lambda: date.today().isoformat())
    notes: str = ""


class EventResponse(BaseModel):
    id: int
    application_id: str
    event_type: str
    event_date: str
    notes: str


# ── Responses ────────────────────────────────────────────────────────────────

class SkillResponse(BaseModel):
    skill_name: str
    skill_type: str


class ApplicationSummary(BaseModel):
    id: str
    company: str
    role_title: str
    platform: str
    date_applied: str
    status: str
    location_city: str | None
    location_country: str | None
    remote_type: str | None
    salary_min: int | None
    salary_max: int | None
    currency: str
    industry: str | None
    seniority: str | None
    employment_type: str | None
    created_at: str
    required_skills: list[str] = Field(default_factory=list)


class ApplicationDetail(ApplicationSummary):
    description_raw: str
    notes: str
    skills: list[SkillResponse] = Field(default_factory=list)
    events: list[EventResponse] = Field(default_factory=list)
    resume_used: str = ""
    cover_letter: str = ""
    answers_text: str = ""


class ApplicationListResponse(BaseModel):
    applications: list[ApplicationSummary]
    total: int
