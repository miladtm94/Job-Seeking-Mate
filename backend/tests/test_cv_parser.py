from app.schemas.candidate import CandidateIngestRequest
from app.services.cv_parser import CVParserService


def test_parse_extracts_skills() -> None:
    service = CVParserService()
    payload = CandidateIngestRequest(
        name="Jane Doe",
        email="jane@example.com",
        raw_cv_text=(
            "Experienced Python developer with 5+ years building FastAPI and Django applications. "
            "Skilled in SQL, Docker, AWS, and machine learning. "
            "Delivered production ML pipelines using TensorFlow and Kubernetes."
        ),
    )
    result = service.parse(payload)
    assert result.candidate_id.startswith("cand_")
    skills_lower = [s.lower() for s in result.skills]
    assert "python" in skills_lower
    assert "docker" in skills_lower
    assert result.seniority in ("senior", "staff", "mid")
    assert result.years_experience >= 3
    assert len(result.strengths) > 0
    assert result.summary != ""


def test_parse_minimal_cv() -> None:
    service = CVParserService()
    payload = CandidateIngestRequest(
        name="Test User",
        email="test@example.com",
        raw_cv_text=(
            "A junior developer with experience in javascript "
            "and react building web apps for 1 year"
        ),
    )
    result = service.parse(payload)
    assert result.candidate_id.startswith("cand_")
    assert result.seniority in ("junior", "mid")
    assert len(result.skill_gaps) >= 0


def test_parse_deterministic_id() -> None:
    service = CVParserService()
    payload = CandidateIngestRequest(
        name="Test",
        email="same@example.com",
        raw_cv_text=(
            "Python developer with 3 years of experience "
            "in backend development and sql databases"
        ),
    )
    r1 = service.parse(payload)
    r2 = service.parse(payload)
    assert r1.candidate_id == r2.candidate_id
