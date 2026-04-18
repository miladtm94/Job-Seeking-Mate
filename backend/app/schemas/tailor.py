from pydantic import BaseModel


class TailorRequest(BaseModel):
    cv_text: str
    job_description: str
    # Optional additional context
    key_achievements: str = ""
    target_industry: str = ""
    career_narrative: str = ""
    portfolio_links: str = ""
    constraints: str = ""


class TailorResponse(BaseModel):
    resume: str
    cover_letter: str
    strategic_notes: str = ""


class ParseFileResponse(BaseModel):
    text: str


class EvaluateRequest(BaseModel):
    cv_text: str
    job_description: str


class EvaluateResponse(BaseModel):
    ats_score: int  # 0-100
    interview_probability: int  # 0-100
    strengths: list[str]
    gaps: list[str]
    keyword_matches: dict[str, str]  # keyword -> "present" | "partial" | "missing"
    summary: str
    recommendation: str


class CoverLetterRequest(BaseModel):
    cv_text: str
    job_description: str


class CoverLetterResponse(BaseModel):
    cover_letter: str
