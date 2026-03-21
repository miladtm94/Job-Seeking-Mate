import logging
from datetime import datetime

from app.agents.base import AgentTask
from app.agents.specialists import ApplicationAgent, CVAgent, JobDiscoveryAgent, MatchingAgent
from app.schemas.application import ApplicationRecord
from app.services.tracker import tracker

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates the full job search pipeline: Parse -> Discover -> Match -> Apply."""

    def __init__(self) -> None:
        self.cv_agent = CVAgent()
        self.job_agent = JobDiscoveryAgent()
        self.matching_agent = MatchingAgent()
        self.application_agent = ApplicationAgent()

    def run_full_cycle(self, payload: dict) -> dict:
        """Run the complete pipeline: CV parse -> Job search -> Match -> Generate applications."""
        steps = []
        errors = []

        # Step 1: Parse candidate profile
        cv_result = self.cv_agent.run(AgentTask(name="cv_parse", payload=payload))
        steps.append({
            "agent": "cv_agent", "result": cv_result.output, "success": cv_result.success,
        })
        if not cv_result.success:
            errors.append(f"CV parsing failed: {cv_result.errors}")
            return self._build_response(steps, errors)

        # Step 2: Discover jobs
        search_payload = {
            "query": payload.get("query", payload.get("preferred_roles", [""])[0]),
            "locations": payload.get("locations", []),
            "sources": payload.get("sources", ["indeed", "adzuna"]),
            "remote_only": payload.get("remote_only", False),
            "salary_min": payload.get("salary_min"),
            "max_results": payload.get("max_results", 25),
        }
        job_result = self.job_agent.run(AgentTask(name="job_search", payload=search_payload))
        steps.append({
            "agent": "job_discovery", "result": job_result.output, "success": job_result.success,
        })
        if not job_result.success or not job_result.output.get("jobs"):
            errors.append("No jobs found matching criteria")
            return self._build_response(steps, errors)

        # Step 3: Score and rank matches
        match_payload = {
            "candidate": {
                "skills": cv_result.output.get("skills", []),
                "years_experience": cv_result.output.get("years_experience", 3),
                "locations": payload.get("locations", []),
                "preferred_roles": payload.get("preferred_roles", []),
                "domains": cv_result.output.get("domains", []),
                "seniority": cv_result.output.get("seniority", "mid"),
                "salary_min": payload.get("salary_min"),
            },
            "jobs": job_result.output.get("jobs", []),
        }
        match_result = self.matching_agent.run(AgentTask(name="matching", payload=match_payload))
        steps.append({
            "agent": "matching", "result": match_result.output, "success": match_result.success,
        })

        # Step 4: Generate applications for top matches
        applications = []
        matches = match_result.output.get("matches", [])
        top_matches = [m for m in matches if m.get("match_score", 0) >= 60][:5]

        mode = payload.get("mode", "manual")

        for match in top_matches:
            job_data = self._find_job(job_result.output.get("jobs", []), match.get("job_id", ""))
            if not job_data:
                continue

            app_payload = {
                "candidate_profile": {
                    "name": payload.get("name", ""),
                    "skills": cv_result.output.get("skills", []),
                    "experience_summary": cv_result.output.get("summary", ""),
                    "raw_cv_text": payload.get("raw_cv_text", ""),
                    "seniority": cv_result.output.get("seniority", "mid"),
                },
                "job": {
                    "job_id": job_data.get("job_id", ""),
                    "title": job_data.get("title", ""),
                    "company": job_data.get("company", ""),
                    "description": job_data.get("description", ""),
                    "location": job_data.get("location", ""),
                    "salary": job_data.get("salary"),
                    "url": job_data.get("url", ""),
                },
                "mode": mode,
            }
            app_result = self.application_agent.run(
                AgentTask(name="application_generate", payload=app_payload)
            )

            if app_result.success:
                app_output = app_result.output
                app_output["match_score"] = match.get("match_score", 0)
                applications.append(app_output)

                # Track the application
                tracker.save(
                    ApplicationRecord(
                        application_id=app_output.get("application_id", ""),
                        candidate_id=cv_result.output.get("candidate_id", ""),
                        job_id=job_data.get("job_id", ""),
                        company=job_data.get("company", ""),
                        role=job_data.get("title", ""),
                        match_score=match.get("match_score", 0),
                        status="prepared",
                        mode=mode,
                    )
                )

        steps.append({
            "agent": "application",
            "result": {"applications_generated": len(applications)},
            "success": len(applications) > 0,
        })

        return self._build_response(
            steps,
            errors,
            extra={
                "candidate": cv_result.output,
                "jobs_found": len(job_result.output.get("jobs", [])),
                "matches": matches,
                "applications": applications,
                "top_match_score": matches[0].get("match_score", 0) if matches else 0,
            },
        )

    def search_and_match(self, payload: dict) -> dict:
        """Search jobs and score matches without generating applications."""
        search_payload = {
            "query": payload.get("query", ""),
            "locations": payload.get("locations", []),
            "sources": payload.get("sources", ["indeed", "adzuna"]),
            "remote_only": payload.get("remote_only", False),
            "salary_min": payload.get("salary_min"),
            "max_results": payload.get("max_results", 25),
        }
        job_result = self.job_agent.run(AgentTask(name="job_search", payload=search_payload))

        if not job_result.success or not job_result.output.get("jobs"):
            return {"jobs": [], "matches": [], "error": "No jobs found"}

        candidate = payload.get("candidate", {})
        if not candidate.get("skills"):
            return {
                "jobs": job_result.output.get("jobs", []),
                "matches": [],
                "message": "Provide candidate profile for matching",
            }

        match_payload = {"candidate": candidate, "jobs": job_result.output.get("jobs", [])}
        match_result = self.matching_agent.run(AgentTask(name="matching", payload=match_payload))

        return {
            "jobs": job_result.output.get("jobs", []),
            "matches": match_result.output.get("matches", []),
            "rejected_count": match_result.output.get("rejected_count", 0),
        }

    @staticmethod
    def _find_job(jobs: list[dict], job_id: str) -> dict | None:
        for job in jobs:
            if job.get("job_id") == job_id:
                return job
        return jobs[0] if jobs else None

    @staticmethod
    def _build_response(
        steps: list[dict], errors: list[str], extra: dict | None = None
    ) -> dict:
        confidences = []
        for step in steps:
            result = step.get("result", {})
            if isinstance(result, dict) and "confidence" in result:
                confidences.append(result["confidence"])

        response = {
            "steps": steps,
            "errors": errors,
            "requires_human_approval": True,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if extra:
            response.update(extra)
        return response
