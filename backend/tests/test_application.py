from app.schemas.application import (
    ApplicationGenerateRequest,
    ApplicationRecord,
    CandidateProfileInput,
    JobInput,
)
from app.services.application_automation import ApplicationAutomationService
from app.services.tracker import ApplicationTracker


def test_generate_application() -> None:
    service = ApplicationAutomationService()
    payload = ApplicationGenerateRequest(
        candidate_profile=CandidateProfileInput(
            name="Jane Doe",
            skills=["Python", "SQL", "FastAPI"],
            experience_summary="5 years building backend systems",
        ),
        job=JobInput(
            title="Backend Engineer",
            company="TestCo",
            description="Build scalable APIs and microservices",
        ),
    )
    result = service.generate(payload)
    assert result.application_id.startswith("app_")
    assert result.customized_resume != ""
    assert result.tailored_cover_letter != ""
    assert len(result.readiness_checklist) > 0
    assert result.status == "prepared"
    assert result.mode == "manual"


def test_generate_auto_mode() -> None:
    service = ApplicationAutomationService()
    payload = ApplicationGenerateRequest(
        candidate_profile=CandidateProfileInput(
            name="Test",
            skills=["Python"],
            experience_summary="2 years",
        ),
        job=JobInput(
            title="Dev",
            company="Co",
            description="Development work",
        ),
        mode="auto",
    )
    result = service.generate(payload)
    assert result.mode == "auto"
    assert "Human approval required before submission" not in result.readiness_checklist


def test_tracker_save_and_get() -> None:
    tracker = ApplicationTracker()
    record = ApplicationRecord(
        application_id="test_001",
        candidate_id="cand_123",
        job_id="job_456",
        company="TestCo",
        role="Developer",
        match_score=85,
        status="saved",
    )
    saved = tracker.save(record)
    assert saved.application_id == "test_001"

    fetched = tracker.get("test_001")
    assert fetched is not None
    assert fetched.company == "TestCo"


def test_tracker_status_transitions() -> None:
    tracker = ApplicationTracker()
    tracker.save(
        ApplicationRecord(
            application_id="test_002",
            candidate_id="c",
            job_id="j",
            company="X",
            role="Y",
            match_score=70,
            status="saved",
        )
    )

    # Valid transition
    updated = tracker.update_status("test_002", "prepared")
    assert updated is not None
    assert updated.status == "prepared"

    # Invalid transition
    import pytest

    with pytest.raises(ValueError):
        tracker.update_status("test_002", "offer")


def test_tracker_list_and_stats() -> None:
    tracker = ApplicationTracker()
    for i in range(3):
        tracker.save(
            ApplicationRecord(
                application_id=f"stat_{i}",
                candidate_id="c1",
                job_id=f"j{i}",
                company=f"Co{i}",
                role="Dev",
                match_score=70 + i * 5,
                status="saved",
            )
        )

    listing = tracker.list_all(candidate_id="c1")
    assert listing.total == 3

    stats = tracker.get_stats(candidate_id="c1")
    assert stats["total"] == 3
    assert stats["by_status"]["saved"] == 3
