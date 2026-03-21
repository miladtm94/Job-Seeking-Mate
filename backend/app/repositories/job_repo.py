from sqlalchemy.orm import Session

from app.db.models import JobModel


class JobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_many(self, jobs: list[JobModel]) -> list[JobModel]:
        for job in jobs:
            self.db.merge(job)
        self.db.commit()
        return jobs
