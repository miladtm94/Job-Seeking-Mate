import logging

from app.agents.base import AgentPlan, AgentResult, AgentTask, BaseAgent
from app.schemas.application import ApplicationGenerateRequest, CandidateProfileInput, JobInput
from app.schemas.candidate import CandidateIngestRequest
from app.schemas.job import JobSearchRequest
from app.schemas.matching import BatchMatchRequest, CandidateForMatch, JobForMatch
from app.services.application_automation import ApplicationAutomationService
from app.services.cv_parser import CVParserService
from app.services.job_discovery import JobDiscoveryService
from app.services.matcher import MatchingService

logger = logging.getLogger(__name__)


class CVAgent(BaseAgent):
    name = "cv_agent"
    confidence_threshold = 0.6

    def __init__(self) -> None:
        self.service = CVParserService()

    def plan(self, task: AgentTask) -> AgentPlan:
        return AgentPlan(
            steps=["Parse CV text", "Extract skills and domains", "Infer seniority"],
            required_data=["raw_cv_text", "email", "name"],
            success_criteria=["Skills extracted", "Seniority determined"],
        )

    def act(self, task: AgentTask, plan: AgentPlan) -> AgentResult:
        try:
            request = CandidateIngestRequest(**task.payload)
            result = self.service.parse(request)
            confidence = min(len(result.skills) / 5, 1.0) * 0.8 + 0.2
            return AgentResult(
                self.name,
                True,
                round(confidence, 2),
                result.model_dump(),
            )
        except Exception as e:
            return AgentResult(self.name, False, 0, {}, [str(e)])


class JobDiscoveryAgent(BaseAgent):
    name = "job_discovery_agent"
    confidence_threshold = 0.5

    def __init__(self) -> None:
        self.service = JobDiscoveryService()

    def plan(self, task: AgentTask) -> AgentPlan:
        sources = task.payload.get("sources", ["indeed", "adzuna"])
        return AgentPlan(
            steps=[f"Search {s}" for s in sources] + ["Deduplicate", "Rank results"],
            required_data=["query"],
            success_criteria=["Jobs found", "Results deduplicated"],
        )

    def act(self, task: AgentTask, plan: AgentPlan) -> AgentResult:
        try:
            request = JobSearchRequest(**task.payload)
            result = self.service.search(request)
            confidence = min(len(result.jobs) / 5, 1.0) * 0.7 + 0.3
            return AgentResult(
                self.name,
                True,
                round(confidence, 2),
                {
                    "jobs": [j.model_dump() for j in result.jobs],
                    "total": result.total,
                    "query": result.query,
                },
            )
        except Exception as e:
            return AgentResult(self.name, False, 0, {}, [str(e)])

    def refine(self, task: AgentTask, result: AgentResult) -> AgentTask:
        # Broaden search on retry
        if result.output.get("total", 0) == 0:
            task.payload["sources"] = ["indeed", "adzuna", "demo"]
            if task.payload.get("remote_only"):
                task.payload["remote_only"] = False
        return super().refine(task, result)


class MatchingAgent(BaseAgent):
    name = "matching_agent"
    confidence_threshold = 0.6

    def __init__(self) -> None:
        self.service = MatchingService()

    def plan(self, task: AgentTask) -> AgentPlan:
        return AgentPlan(
            steps=["Extract skills from jobs", "Compute match scores", "Rank and filter"],
            required_data=["candidate", "jobs"],
            success_criteria=["All jobs scored", "Results ranked"],
        )

    def act(self, task: AgentTask, plan: AgentPlan) -> AgentResult:
        try:
            candidate_data = task.payload["candidate"]
            jobs_data = task.payload["jobs"]

            candidate = CandidateForMatch(**candidate_data)
            jobs = []
            for j in jobs_data:
                # Extract skills from description if not provided
                required = j.get("required_skills", [])
                preferred = j.get("preferred_skills", [])
                if not required and j.get("description"):
                    required, preferred = self.service.extract_skills_from_description(
                        j["description"]
                    )
                    if not required:
                        # Fallback: use candidate skills as proxy
                        required = candidate_data.get("skills", [])[:5]

                jobs.append(
                    JobForMatch(
                        job_id=j.get("job_id", ""),
                        title=j.get("title", ""),
                        company=j.get("company", ""),
                        required_skills=required,
                        preferred_skills=preferred,
                        location=j.get("location", ""),
                        description=j.get("description", ""),
                        salary=j.get("salary"),
                    )
                )

            batch = BatchMatchRequest(candidate=candidate, jobs=jobs)
            result = self.service.score_batch(batch)

            confidence = 0.9 if result.results else 0.5
            return AgentResult(
                self.name,
                True,
                confidence,
                {
                    "matches": [r.model_dump() for r in result.results],
                    "rejected_count": result.rejected_count,
                    "top_score": result.results[0].match_score if result.results else 0,
                },
            )
        except Exception as e:
            logger.exception("Matching agent error")
            return AgentResult(self.name, False, 0, {}, [str(e)])


class ApplicationAgent(BaseAgent):
    name = "application_agent"
    confidence_threshold = 0.65

    def __init__(self) -> None:
        self.service = ApplicationAutomationService()

    def plan(self, task: AgentTask) -> AgentPlan:
        mode = task.payload.get("mode", "manual")
        steps = ["Generate tailored resume", "Generate cover letter", "Create talking points"]
        if mode != "manual":
            steps.append("Pre-fill application form")
        steps.append("Request human approval")
        return AgentPlan(
            steps=steps,
            required_data=["candidate_profile", "job"],
            success_criteria=["Resume generated", "Cover letter generated"],
        )

    def act(self, task: AgentTask, plan: AgentPlan) -> AgentResult:
        try:
            request = ApplicationGenerateRequest(
                candidate_profile=CandidateProfileInput(**task.payload["candidate_profile"]),
                job=JobInput(**task.payload["job"]),
                mode=task.payload.get("mode", "manual"),
            )
            result = self.service.generate(request)
            confidence = 0.85 if result.customized_resume and result.tailored_cover_letter else 0.5
            return AgentResult(
                self.name,
                True,
                confidence,
                result.model_dump(),
            )
        except Exception as e:
            return AgentResult(self.name, False, 0, {}, [str(e)])
