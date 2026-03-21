from app.agents.base import AgentTask
from app.agents.specialists import ApplicationAgent, CVAgent, JobDiscoveryAgent, MatchingAgent


def test_cv_agent_parses_profile() -> None:
    agent = CVAgent()
    task = AgentTask(
        name="cv_parse",
        payload={
            "name": "Test User",
            "email": "test@example.com",
            "raw_cv_text": (
                "Python developer with 5+ years experience in fastapi, sql, docker, "
                "and machine learning. Built production systems at scale."
            ),
        },
    )
    result = agent.run(task)
    assert result.success
    assert result.confidence > 0.5
    assert "skills" in result.output
    assert len(result.output["skills"]) > 0


def test_job_discovery_agent() -> None:
    agent = JobDiscoveryAgent()
    task = AgentTask(
        name="job_search",
        payload={
            "query": "Software Engineer",
            "locations": ["Sydney"],
            "sources": ["demo"],
            "max_results": 5,
        },
    )
    result = agent.run(task)
    assert result.success
    assert result.output.get("total", 0) > 0
    assert len(result.output.get("jobs", [])) > 0


def test_matching_agent() -> None:
    agent = MatchingAgent()
    task = AgentTask(
        name="matching",
        payload={
            "candidate": {
                "skills": ["Python", "SQL", "Docker"],
                "years_experience": 5,
                "locations": ["Sydney"],
                "seniority": "senior",
            },
            "jobs": [
                {
                    "job_id": "j1",
                    "title": "Backend Engineer",
                    "company": "TestCo",
                    "required_skills": ["Python", "SQL"],
                    "preferred_skills": ["Docker"],
                    "location": "Sydney",
                    "description": "Build backend services",
                },
            ],
        },
    )
    result = agent.run(task)
    assert result.success
    assert len(result.output.get("matches", [])) > 0


def test_application_agent() -> None:
    agent = ApplicationAgent()
    task = AgentTask(
        name="app_gen",
        payload={
            "candidate_profile": {
                "name": "Jane",
                "skills": ["Python", "SQL"],
                "experience_summary": "5 years backend dev",
            },
            "job": {
                "title": "Developer",
                "company": "TestCo",
                "description": "Build things",
            },
            "mode": "manual",
        },
    )
    result = agent.run(task)
    assert result.success
    assert result.output.get("customized_resume")
    assert result.output.get("tailored_cover_letter")
