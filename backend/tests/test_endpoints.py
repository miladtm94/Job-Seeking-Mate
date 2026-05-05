from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)

SAMPLE_CV = (
    "Jane Smith, experienced Python developer with 6 years of experience. "
    "Skilled in FastAPI, SQL, Docker, AWS, machine learning, and TensorFlow. "
    "Built production ML pipelines and scalable backend services."
)


def auth_headers() -> dict[str, str]:
    settings = get_settings()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": settings.app_username, "password": settings.app_password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_candidate_ingest() -> None:
    response = client.post(
        "/api/v1/candidates/ingest",
        json={
            "name": "Jane Smith",
            "email": "jane.test@example.com",
            "raw_cv_text": SAMPLE_CV,
            "preferred_roles": ["ML Engineer"],
            "locations": ["Sydney"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["candidate_id"].startswith("cand_")
    assert len(data["skills"]) > 0
    assert data["summary"] != ""


def test_candidate_list() -> None:
    # First ingest a candidate
    client.post(
        "/api/v1/candidates/ingest",
        json={
            "name": "List Test",
            "email": "list.test@example.com",
            "raw_cv_text": SAMPLE_CV,
        },
    )
    response = client.get("/api/v1/candidates/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_job_search_post() -> None:
    response = client.post(
        "/api/v1/jobs/search",
        json={"query": "Data Scientist", "locations": ["Sydney"], "max_results": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) > 0
    assert data["query"] == "Data Scientist"


def test_job_search_get() -> None:
    response = client.get("/api/v1/jobs/search?query=Engineer&max_results=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) > 0


def test_matching_score() -> None:
    response = client.post(
        "/api/v1/matching/score",
        json={
            "candidate": {
                "skills": ["Python", "SQL"],
                "years_experience": 5,
                "locations": ["Sydney"],
            },
            "job": {
                "title": "Backend Dev",
                "company": "TestCo",
                "required_skills": ["Python", "SQL"],
                "location": "Sydney",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert 0 <= data["match_score"] <= 100
    assert data["recommendation"] in ("strong_apply", "apply", "maybe", "skip")


def test_matching_batch() -> None:
    response = client.post(
        "/api/v1/matching/batch",
        json={
            "candidate": {
                "skills": ["Python"],
                "years_experience": 3,
            },
            "jobs": [
                {
                    "job_id": "j1",
                    "title": "Dev",
                    "required_skills": ["Python"],
                    "location": "Remote",
                },
                {
                    "job_id": "j2",
                    "title": "Dev2",
                    "required_skills": ["Java", "Scala"],
                    "location": "NYC",
                },
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


def test_application_generate() -> None:
    response = client.post(
        "/api/v1/applications/generate",
        json={
            "candidate_profile": {
                "name": "Test",
                "skills": ["Python", "SQL"],
                "experience_summary": "3 years backend dev",
            },
            "job": {
                "title": "Engineer",
                "company": "TestCo",
                "description": "Build systems",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["customized_resume"] != ""
    assert data["tailored_cover_letter"] != ""
    assert data["status"] == "prepared"


def test_application_stats() -> None:
    response = client.get("/api/v1/applications/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "interview_rate" in data


def test_jats_application_documents_and_free_text_industry() -> None:
    headers = auth_headers()
    create_response = client.post(
        "/api/v1/jats/applications",
        headers=headers,
        json={
            "company": "Docs Co",
            "role_title": "Policy Writer",
            "platform": "Direct",
            "date_applied": "2026-04-23",
            "status": "applied",
            "industry": "Public Sector Transformation",
            "notes": "Tracking submitted documents",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    app_id = created["id"]
    assert created["industry"] == "Public Sector Transformation"
    assert created["document_count"] == 0

    upload_response = client.post(
        f"/api/v1/jats/applications/{app_id}/documents",
        headers=headers,
        data={"category": "resume"},
        files={"file": ("resume.doc", b"resume bytes", "application/msword")},
    )
    assert upload_response.status_code == 200
    document = upload_response.json()
    assert document["category"] == "resume"
    assert document["filename"] == "resume.doc"

    detail_response = client.get(f"/api/v1/jats/applications/{app_id}", headers=headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["document_count"] == 1
    assert detail["documents"][0]["filename"] == "resume.doc"
    assert detail["industry"] == "Public Sector Transformation"

    download_response = client.get(
        f"/api/v1/jats/applications/{app_id}/documents/{document['id']}/download",
        headers=headers,
    )
    assert download_response.status_code == 200
    assert download_response.content == b"resume bytes"

    delete_doc_response = client.delete(
        f"/api/v1/jats/applications/{app_id}/documents/{document['id']}",
        headers=headers,
    )
    assert delete_doc_response.status_code == 200

    delete_app_response = client.delete(f"/api/v1/jats/applications/{app_id}", headers=headers)
    assert delete_app_response.status_code == 200
