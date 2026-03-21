from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SAMPLE_CV = (
    "Jane Smith, experienced Python developer with 6 years of experience. "
    "Skilled in FastAPI, SQL, Docker, AWS, machine learning, and TensorFlow. "
    "Built production ML pipelines and scalable backend services."
)


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
