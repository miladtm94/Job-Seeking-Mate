from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.orchestrator import AgentOrchestrator

router = APIRouter()
orchestrator = AgentOrchestrator()


class FullCycleRequest(BaseModel):
    name: str
    email: str
    raw_cv_text: str = Field(min_length=50)
    query: str = ""
    preferred_roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    remote_only: bool = False
    sources: list[str] = Field(default_factory=lambda: ["indeed", "adzuna"])
    max_results: int = 25
    mode: str = "manual"


class SearchMatchRequest(BaseModel):
    query: str
    locations: list[str] = Field(default_factory=list)
    remote_only: bool = False
    salary_min: int | None = None
    max_results: int = 25
    sources: list[str] = Field(default_factory=lambda: ["indeed", "adzuna"])
    candidate: dict = Field(default_factory=dict)


@router.post("/full-cycle")
def run_full_cycle(payload: FullCycleRequest) -> dict:
    """Run the complete agent pipeline: CV parse -> Job search -> Match -> Generate applications."""
    return orchestrator.run_full_cycle(payload.model_dump())


@router.post("/search-match")
def search_and_match(payload: SearchMatchRequest) -> dict:
    """Search for jobs and score matches without generating applications."""
    return orchestrator.search_and_match(payload.model_dump())
