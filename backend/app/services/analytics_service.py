import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.jats_models import ApplicationEntry, ApplicationSkill

logger = logging.getLogger(__name__)


def get_overview(db: Session) -> dict:
    total = db.query(func.count(ApplicationEntry.id)).scalar() or 0
    rows = (
        db.query(ApplicationEntry.status, func.count(ApplicationEntry.id))
        .group_by(ApplicationEntry.status)
        .all()
    )
    by_status: dict[str, int] = {status: count for status, count in rows}

    # Funnel counts
    n_applied = sum(
        by_status.get(s, 0) for s in ("applied", "interview", "offer", "rejected")
    )
    n_interviewed = by_status.get("interview", 0) + by_status.get("offer", 0)
    n_offered = by_status.get("offer", 0)
    n_rejected = by_status.get("rejected", 0)

    interview_rate = round(n_interviewed / max(n_applied, 1) * 100, 1)
    offer_rate = round(n_offered / max(n_applied, 1) * 100, 1)
    rejection_rate = round(n_rejected / max(n_applied, 1) * 100, 1)

    # Avg response time (days between applied and first non-applied event)
    avg_response_days: float | None = None

    return {
        "total": total,
        "by_status": by_status,
        "applied_count": n_applied,
        "interview_count": n_interviewed,
        "offer_count": n_offered,
        "rejected_count": n_rejected,
        "interview_rate": interview_rate,
        "offer_rate": offer_rate,
        "rejection_rate": rejection_rate,
        "avg_response_days": avg_response_days,
    }


def get_by_platform(db: Session) -> list[dict]:
    rows = (
        db.query(ApplicationEntry.platform, func.count(ApplicationEntry.id))
        .group_by(ApplicationEntry.platform)
        .order_by(func.count(ApplicationEntry.id).desc())
        .all()
    )
    return [{"platform": p or "Unknown", "count": c} for p, c in rows]


def get_by_industry(db: Session) -> list[dict]:
    rows = (
        db.query(ApplicationEntry.industry, func.count(ApplicationEntry.id))
        .filter(ApplicationEntry.industry.isnot(None))
        .group_by(ApplicationEntry.industry)
        .order_by(func.count(ApplicationEntry.id).desc())
        .all()
    )
    return [{"industry": i, "count": c} for i, c in rows]


def get_by_status(db: Session) -> list[dict]:
    rows = (
        db.query(ApplicationEntry.status, func.count(ApplicationEntry.id))
        .group_by(ApplicationEntry.status)
        .order_by(func.count(ApplicationEntry.id).desc())
        .all()
    )
    return [{"status": s, "count": c} for s, c in rows]


def get_by_remote_type(db: Session) -> list[dict]:
    rows = (
        db.query(ApplicationEntry.remote_type, func.count(ApplicationEntry.id))
        .group_by(ApplicationEntry.remote_type)
        .order_by(func.count(ApplicationEntry.id).desc())
        .all()
    )
    return [{"remote_type": r or "Unknown", "count": c} for r, c in rows]


def get_timeline(db: Session, group_by: str = "week") -> list[dict]:
    """Return applications grouped by week (Monday) or month."""
    rows = (
        db.query(ApplicationEntry.date_applied)
        .filter(ApplicationEntry.date_applied.isnot(None))
        .all()
    )

    bucket: dict[str, int] = defaultdict(int)
    for (date_str,) in rows:
        try:
            d = datetime.fromisoformat(date_str).date()
        except (ValueError, TypeError):
            continue
        if group_by == "month":
            key = d.strftime("%Y-%m")
        else:
            monday = d - timedelta(days=d.weekday())
            key = monday.isoformat()
        bucket[key] += 1

    return [{"date": k, "count": v} for k, v in sorted(bucket.items())]


def get_skills_frequency(db: Session, limit: int = 20) -> list[dict]:
    rows = (
        db.query(ApplicationSkill.skill_name, func.count(ApplicationSkill.id))
        .filter(ApplicationSkill.skill_type == "required")
        .group_by(ApplicationSkill.skill_name)
        .order_by(func.count(ApplicationSkill.id).desc())
        .limit(limit)
        .all()
    )
    return [{"skill": s, "count": c} for s, c in rows]


def get_salary_distribution(db: Session) -> dict:
    rows = (
        db.query(
            ApplicationEntry.salary_min,
            ApplicationEntry.salary_max,
            ApplicationEntry.currency,
        )
        .filter(
            (ApplicationEntry.salary_min.isnot(None))
            | (ApplicationEntry.salary_max.isnot(None))
        )
        .all()
    )

    if not rows:
        return {"buckets": [], "avg_min": None, "avg_max": None, "currency": None}

    mins = [r[0] for r in rows if r[0] is not None]
    maxs = [r[1] for r in rows if r[1] is not None]
    currency = rows[0][2] if rows else None

    # Build salary buckets (50k-wide)
    all_vals = mins + maxs
    if not all_vals:
        return {"buckets": [], "avg_min": None, "avg_max": None, "currency": currency}

    lo = (min(all_vals) // 50_000) * 50_000
    hi = ((max(all_vals) // 50_000) + 1) * 50_000
    buckets: dict[str, int] = {}
    step = 50_000
    bucket_start = lo
    while bucket_start < hi:
        label = f"{bucket_start // 1000}k–{(bucket_start + step) // 1000}k"
        buckets[label] = 0
        bucket_start += step

    for val in all_vals:
        bucket_start = (val // step) * step
        label = f"{bucket_start // 1000}k–{(bucket_start + step) // 1000}k"
        if label in buckets:
            buckets[label] += 1

    return {
        "buckets": [{"range": k, "count": v} for k, v in buckets.items() if v > 0],
        "avg_min": round(sum(mins) / len(mins)) if mins else None,
        "avg_max": round(sum(maxs) / len(maxs)) if maxs else None,
        "currency": currency,
    }


def get_seniority_distribution(db: Session) -> list[dict]:
    rows = (
        db.query(ApplicationEntry.seniority, func.count(ApplicationEntry.id))
        .filter(ApplicationEntry.seniority.isnot(None))
        .group_by(ApplicationEntry.seniority)
        .order_by(func.count(ApplicationEntry.id).desc())
        .all()
    )
    return [{"seniority": s, "count": c} for s, c in rows]


def get_full_analytics(db: Session) -> dict:
    return {
        "overview": get_overview(db),
        "by_platform": get_by_platform(db),
        "by_industry": get_by_industry(db),
        "by_status": get_by_status(db),
        "by_remote_type": get_by_remote_type(db),
        "timeline": get_timeline(db),
        "skills_frequency": get_skills_frequency(db),
        "salary": get_salary_distribution(db),
        "seniority": get_seniority_distribution(db),
    }
