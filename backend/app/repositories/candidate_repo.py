from sqlalchemy.orm import Session

from app.db.models import CandidateModel


class CandidateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(self, candidate: CandidateModel) -> CandidateModel:
        self.db.merge(candidate)
        self.db.commit()
        return candidate
