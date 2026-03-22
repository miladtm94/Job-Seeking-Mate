from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DB_PATH = _PROJECT_ROOT / "data" / "jats.db"


class JATSBase(DeclarativeBase):
    pass


def _make_engine():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{_DB_PATH}",
        connect_args={"check_same_thread": False},
    )


engine = _make_engine()
JATSSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_jats_db():
    db = JATSSessionLocal()
    try:
        yield db
    finally:
        db.close()
