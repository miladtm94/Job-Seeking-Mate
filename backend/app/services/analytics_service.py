import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.jats_models import ApplicationEntry, ApplicationEvent, ApplicationSkill

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
    response_rate = round((n_interviewed + n_rejected) / max(n_applied, 1) * 100, 1)

    # Avg response time: days from date_applied to first non-applied event per app
    first_response_subq = (
        db.query(
            ApplicationEvent.application_id,
            func.min(ApplicationEvent.event_date).label("first_response_date"),
        )
        .filter(ApplicationEvent.event_type != "applied")
        .group_by(ApplicationEvent.application_id)
        .subquery()
    )
    response_rows = (
        db.query(ApplicationEntry.date_applied, first_response_subq.c.first_response_date)
        .join(first_response_subq, ApplicationEntry.id == first_response_subq.c.application_id)
        .all()
    )
    times: list[int] = []
    for applied_str, response_str in response_rows:
        try:
            applied = datetime.fromisoformat(applied_str).date()
            responded = datetime.fromisoformat(response_str).date()
            days = (responded - applied).days
            if 0 <= days <= 365:
                times.append(days)
        except (ValueError, TypeError):
            pass
    avg_response_days: float | None = round(sum(times) / len(times), 1) if times else None

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
        "response_rate": response_rate,
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
        .filter(ApplicationEntry.industry.isnot(None), ApplicationEntry.industry != "")
        .group_by(ApplicationEntry.industry)
        .order_by(func.count(ApplicationEntry.id).desc(), ApplicationEntry.industry.asc())
        .all()
    )
    return [{"industry": industry, "count": count} for industry, count in rows]


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


def get_fit_score_analytics(db: Session) -> dict:
    """Fit-to-role score insights: overall avg, distribution, and avg by outcome."""
    rows = (
        db.query(ApplicationEntry.fit_score, ApplicationEntry.status)
        .filter(ApplicationEntry.fit_score.isnot(None))
        .all()
    )
    if not rows:
        return {"avg": None, "count": 0, "distribution": [], "by_status": []}

    scores = [r[0] for r in rows]
    avg = round(sum(scores) / len(scores), 1)

    buckets: dict[str, int] = {"0–40": 0, "41–60": 0, "61–80": 0, "81–100": 0}
    for s in scores:
        if s <= 40:
            buckets["0–40"] += 1
        elif s <= 60:
            buckets["41–60"] += 1
        elif s <= 80:
            buckets["61–80"] += 1
        else:
            buckets["81–100"] += 1

    # Avg fit score per outcome status
    status_totals: dict[str, list[int]] = {}
    for score, status in rows:
        status_totals.setdefault(status, []).append(score)
    by_status = sorted(
        [
            {"status": s, "avg_score": round(sum(v) / len(v), 1), "count": len(v)}
            for s, v in status_totals.items()
        ],
        key=lambda x: -(x["avg_score"] if isinstance(x["avg_score"], (int, float)) else 0),
    )

    return {
        "avg": avg,
        "count": len(scores),
        "distribution": [{"range": k, "count": v} for k, v in buckets.items()],
        "by_status": by_status,
    }


def get_overdue_followups(db: Session) -> list[dict]:
    """Applications with follow_up_date <= today and still active."""
    today_str = date.today().isoformat()
    rows = (
        db.query(ApplicationEntry)
        .filter(
            ApplicationEntry.follow_up_date.isnot(None),
            ApplicationEntry.follow_up_date <= today_str,
            ApplicationEntry.status.in_(["applied", "interview", "saved"]),
        )
        .order_by(ApplicationEntry.follow_up_date.asc())
        .all()
    )
    today_date = date.today()
    result = []
    for e in rows:
        try:
            due = datetime.fromisoformat(e.follow_up_date or "").date()
            days_overdue = (today_date - due).days
        except (ValueError, TypeError):
            days_overdue = 0
        result.append({
            "id": e.id,
            "company": e.company,
            "role_title": e.role_title,
            "status": e.status,
            "follow_up_date": e.follow_up_date,
            "days_overdue": days_overdue,
        })
    return result


def get_skills_by_outcome(db: Session) -> dict:
    """Top required skills split by application outcome."""

    def top_skills(statuses: list[str], limit: int = 10) -> list[dict]:
        subq = (
            db.query(ApplicationEntry.id)
            .filter(ApplicationEntry.status.in_(statuses))
            .subquery()
        )
        rows = (
            db.query(ApplicationSkill.skill_name, func.count(ApplicationSkill.id))
            .join(subq, ApplicationSkill.application_id == subq.c.id)
            .filter(ApplicationSkill.skill_type == "required")
            .group_by(ApplicationSkill.skill_name)
            .order_by(func.count(ApplicationSkill.id).desc())
            .limit(limit)
            .all()
        )
        return [{"skill": s, "count": c} for s, c in rows]

    return {
        "interviewed": top_skills(["interview", "offer"]),
        "applied_only": top_skills(["applied"]),
        "rejected": top_skills(["rejected"]),
    }


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
        "overdue_followups": get_overdue_followups(db),
        "skills_by_outcome": get_skills_by_outcome(db),
        "fit_score": get_fit_score_analytics(db),
    }
