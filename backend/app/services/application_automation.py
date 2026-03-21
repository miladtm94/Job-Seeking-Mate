import logging
import uuid

from app.core.ai_client import ai_complete
from app.schemas.application import ApplicationGenerateRequest, ApplicationGenerateResponse
from app.services.cover_letter import CoverLetterService
from app.services.resume_tailor import ResumeTailoringService

logger = logging.getLogger(__name__)


class ApplicationAutomationService:
    """Prepares application artifacts with AI-powered content and approval gates."""

    def __init__(self) -> None:
        self.resume_service = ResumeTailoringService()
        self.cover_service = CoverLetterService()

    def generate(self, payload: ApplicationGenerateRequest) -> ApplicationGenerateResponse:
        application_id = f"app_{uuid.uuid4().hex[:12]}"

        resume = self.resume_service.generate(payload.candidate_profile, payload.job)
        letter = self.cover_service.generate(payload.candidate_profile, payload.job)
        talking_points = self._generate_talking_points(payload)

        checklist = [
            "Facts verified against source CV",
            "Job-relevant skills emphasized",
            "ATS-safe formatting maintained",
            "Cover letter personalized for company",
            "Talking points prepared for interview",
        ]

        if payload.mode != "auto":
            checklist.append("Human approval required before submission")

        return ApplicationGenerateResponse(
            application_id=application_id,
            customized_resume=resume,
            tailored_cover_letter=letter,
            talking_points=talking_points,
            readiness_checklist=checklist,
            mode=payload.mode,
            status="prepared",
        )

    def _generate_talking_points(self, payload: ApplicationGenerateRequest) -> list[str]:
        system = (
            "Generate 4-5 key talking points for a job interview. Each should be a concise "
            "bullet that connects the candidate's experience to the job requirements. "
            "Return a JSON array of strings only."
        )
        prompt = (
            f"Candidate skills: {', '.join(payload.candidate_profile.skills)}\n"
            f"Experience: {payload.candidate_profile.experience_summary[:500]}\n"
            f"Job: {payload.job.title} at {payload.job.company}\n"
            f"Description: {payload.job.description[:500]}"
        )
        raw = ai_complete(system, prompt, max_tokens=512)
        if raw:
            import json

            try:
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1]
                    cleaned = cleaned.rsplit("```", 1)[0]
                return json.loads(cleaned)
            except (json.JSONDecodeError, IndexError):
                pass

        return [
            f"Highlight experience with {', '.join(payload.candidate_profile.skills[:3])}",
            f"Discuss relevant projects that align with {payload.job.title} responsibilities",
            f"Show enthusiasm for {payload.job.company}'s mission and culture",
            "Prepare questions about team structure and growth opportunities",
        ]
