from fastapi import APIRouter

from app.schemas.matching import (
    BatchMatchRequest,
    BatchMatchResponse,
    MatchScoreRequest,
    MatchScoreResponse,
)
from app.services.matcher import MatchingService

router = APIRouter()
matching_service = MatchingService()


@router.post("/score", response_model=MatchScoreResponse)
def score_match(payload: MatchScoreRequest) -> MatchScoreResponse:
    return matching_service.score(payload)


@router.post("/batch", response_model=BatchMatchResponse)
def score_batch(payload: BatchMatchRequest) -> BatchMatchResponse:
    return matching_service.score_batch(payload)
