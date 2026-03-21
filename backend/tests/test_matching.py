from app.schemas.matching import (
    BatchMatchRequest,
    CandidateForMatch,
    JobForMatch,
    MatchScoreRequest,
)
from app.services.matcher import MatchingService


def test_match_score_strong_apply_threshold() -> None:
    service = MatchingService()
    payload = MatchScoreRequest(
        candidate=CandidateForMatch(
            skills=["Python", "TensorFlow", "SQL", "AWS"],
            years_experience=7,
            locations=["Sydney"],
            seniority="senior",
        ),
        job=JobForMatch(
            title="Senior ML Engineer",
            company="TestCo",
            required_skills=["Python", "TensorFlow", "SQL"],
            preferred_skills=["AWS"],
            location="Sydney",
        ),
    )
    result = service.score(payload)
    assert result.match_score >= 70
    assert result.recommendation in ("strong_apply", "apply")
    assert "python" in [s.lower() for s in result.key_matching_skills]


def test_match_score_skip_threshold() -> None:
    service = MatchingService()
    payload = MatchScoreRequest(
        candidate=CandidateForMatch(
            skills=["Java"],
            years_experience=1,
            locations=["Melbourne"],
            seniority="junior",
        ),
        job=JobForMatch(
            title="Staff ML Engineer",
            company="TestCo",
            required_skills=["Python", "TensorFlow", "PyTorch", "Kubernetes"],
            location="Sydney",
        ),
    )
    result = service.score(payload)
    assert result.match_score < 55
    assert result.recommendation in ("skip", "maybe")
    assert len(result.missing_skills) > 0


def test_match_breakdown_present() -> None:
    service = MatchingService()
    payload = MatchScoreRequest(
        candidate=CandidateForMatch(
            skills=["Python", "SQL"],
            years_experience=4,
            locations=["Remote"],
        ),
        job=JobForMatch(
            title="Backend Developer",
            company="TestCo",
            required_skills=["Python", "SQL", "Docker"],
            location="Remote",
        ),
    )
    result = service.score(payload)
    assert result.breakdown.skill_score >= 0
    assert result.breakdown.location_score >= 0
    assert result.explanation != ""


def test_batch_matching() -> None:
    service = MatchingService()
    candidate = CandidateForMatch(
        skills=["Python", "React", "SQL"],
        years_experience=5,
        locations=["Sydney"],
    )
    jobs = [
        JobForMatch(
            job_id="j1",
            title="Full Stack Developer",
            company="Co1",
            required_skills=["Python", "React"],
            location="Sydney",
        ),
        JobForMatch(
            job_id="j2",
            title="Data Scientist",
            company="Co2",
            required_skills=["R", "Stata", "SPSS"],
            location="London",
        ),
    ]
    result = service.score_batch(BatchMatchRequest(candidate=candidate, jobs=jobs))
    assert len(result.results) >= 1
    assert result.results[0].match_score >= result.results[-1].match_score
