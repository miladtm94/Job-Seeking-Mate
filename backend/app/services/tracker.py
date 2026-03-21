import logging
import uuid

from app.schemas.application import ApplicationListResponse, ApplicationRecord

logger = logging.getLogger(__name__)

VALID_STATUSES = {"saved", "prepared", "applied", "interview", "rejected", "offer", "withdrawn"}
VALID_TRANSITIONS = {
    "saved": {"prepared", "withdrawn"},
    "prepared": {"applied", "saved", "withdrawn"},
    "applied": {"interview", "rejected", "withdrawn"},
    "interview": {"offer", "rejected", "withdrawn"},
    "rejected": set(),
    "offer": {"withdrawn"},
    "withdrawn": set(),
}


class ApplicationTracker:
    """In-memory application tracking with status management.

    In production, this would be backed by the database via repositories.
    """

    def __init__(self) -> None:
        self._records: dict[str, ApplicationRecord] = {}

    def save(self, record: ApplicationRecord) -> ApplicationRecord:
        if not record.application_id:
            record.application_id = f"app_{uuid.uuid4().hex[:12]}"
        self._records[record.application_id] = record
        logger.info(
            "Tracked application %s: %s at %s [%s]",
            record.application_id,
            record.role,
            record.company,
            record.status,
        )
        return record

    def get(self, application_id: str) -> ApplicationRecord | None:
        return self._records.get(application_id)

    def update_status(
        self, application_id: str, new_status: str, notes: str = "",
    ) -> ApplicationRecord | None:
        record = self._records.get(application_id)
        if not record:
            return None

        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}")

        allowed = VALID_TRANSITIONS.get(record.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{record.status}' to '{new_status}'. "
                f"Allowed: {allowed}"
            )

        record.status = new_status
        if notes:
            record.notes = notes
        self._records[application_id] = record
        return record

    def list_all(
        self,
        candidate_id: str | None = None,
        status: str | None = None,
    ) -> ApplicationListResponse:
        records = list(self._records.values())

        if candidate_id:
            records = [r for r in records if r.candidate_id == candidate_id]
        if status:
            records = [r for r in records if r.status == status]

        records.sort(key=lambda r: r.created_at, reverse=True)

        return ApplicationListResponse(applications=records, total=len(records))

    def get_stats(self, candidate_id: str | None = None) -> dict:
        records = list(self._records.values())
        if candidate_id:
            records = [r for r in records if r.candidate_id == candidate_id]

        stats: dict[str, int] = {}
        for r in records:
            stats[r.status] = stats.get(r.status, 0) + 1

        total = len(records)
        applied = stats.get("applied", 0) + stats.get("interview", 0) + stats.get("offer", 0)
        interviews = stats.get("interview", 0) + stats.get("offer", 0)
        interview_rate = round(interviews / max(applied, 1) * 100, 1)

        return {
            "total": total,
            "by_status": stats,
            "interview_rate": interview_rate,
            "offers": stats.get("offer", 0),
        }


# Singleton instance
tracker = ApplicationTracker()
