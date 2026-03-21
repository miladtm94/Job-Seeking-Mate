from app.schemas.job import JobSearchRequest
from app.services.job_discovery import JobDiscoveryService


def test_search_returns_jobs() -> None:
    service = JobDiscoveryService()
    payload = JobSearchRequest(
        query="Data Scientist",
        locations=["Sydney"],
        max_results=10,
    )
    result = service.search(payload)
    assert len(result.jobs) > 0
    assert result.total > 0
    assert result.query == "Data Scientist"


def test_search_deduplicates() -> None:
    service = JobDiscoveryService()
    payload = JobSearchRequest(
        query="ML Engineer",
        locations=["Melbourne"],
        sources=["demo"],
    )
    result = service.search(payload)
    titles = [(j.title, j.company) for j in result.jobs]
    assert len(titles) == len(set(titles))


def test_search_respects_max_results() -> None:
    service = JobDiscoveryService()
    payload = JobSearchRequest(
        query="Developer",
        max_results=3,
    )
    result = service.search(payload)
    assert len(result.jobs) <= 3


def test_job_has_required_fields() -> None:
    service = JobDiscoveryService()
    payload = JobSearchRequest(query="Engineer")
    result = service.search(payload)
    for job in result.jobs:
        assert job.job_id
        assert job.title
        assert job.company
        assert job.source
        assert job.url
