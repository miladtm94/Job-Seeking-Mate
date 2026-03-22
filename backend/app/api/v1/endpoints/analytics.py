from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.jats_db import get_jats_db
from app.services import analytics_service

router = APIRouter()


@router.get("/overview")
def overview(db: Session = Depends(get_jats_db)) -> dict:
    return analytics_service.get_overview(db)


@router.get("/platforms")
def by_platform(db: Session = Depends(get_jats_db)) -> list[dict]:
    return analytics_service.get_by_platform(db)


@router.get("/industries")
def by_industry(db: Session = Depends(get_jats_db)) -> list[dict]:
    return analytics_service.get_by_industry(db)


@router.get("/statuses")
def by_status(db: Session = Depends(get_jats_db)) -> list[dict]:
    return analytics_service.get_by_status(db)


@router.get("/remote-types")
def by_remote_type(db: Session = Depends(get_jats_db)) -> list[dict]:
    return analytics_service.get_by_remote_type(db)


@router.get("/timeline")
def timeline(
    group_by: str = "week",
    db: Session = Depends(get_jats_db),
) -> list[dict]:
    return analytics_service.get_timeline(db, group_by=group_by)


@router.get("/skills")
def skills_frequency(
    limit: int = 20,
    db: Session = Depends(get_jats_db),
) -> list[dict]:
    return analytics_service.get_skills_frequency(db, limit=limit)


@router.get("/salary")
def salary(db: Session = Depends(get_jats_db)) -> dict:
    return analytics_service.get_salary_distribution(db)


@router.get("/seniority")
def seniority(db: Session = Depends(get_jats_db)) -> list[dict]:
    return analytics_service.get_seniority_distribution(db)


@router.get("/all")
def full_analytics(db: Session = Depends(get_jats_db)) -> dict:
    """Single endpoint returning all analytics — use this to avoid N round-trips."""
    return analytics_service.get_full_analytics(db)
