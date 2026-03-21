import logging

from app.core.ai_client import ai_complete
from app.schemas.application import CandidateProfileInput, JobInput

logger = logging.getLogger(__name__)


class ResumeTailoringService:
    """AI-powered resume tailoring with ATS optimization and truthfulness constraints."""

    def generate(self, candidate: CandidateProfileInput, job: JobInput) -> str:
        ai_resume = self._ai_generate(candidate, job)
        if ai_resume:
            return ai_resume
        return self._fallback_generate(candidate, job)

    def _ai_generate(self, candidate: CandidateProfileInput, job: JobInput) -> str | None:
        system = (
            "You are an expert resume writer. Create a tailored resume section for the candidate "
            "targeting the specific job. Rules:\n"
            "1. NEVER fabricate experience or qualifications\n"
            "2. Rewrite the summary to align with the job requirements\n"
            "3. Reframe experience bullets to highlight relevant achievements\n"
            "4. Inject relevant keywords for ATS optimization\n"
            "5. Use clear, professional formatting with sections\n"
            "6. Keep it concise and impactful\n"
            "7. Output plain text with clear section headers (no markdown)"
        )
        prompt = (
            f"Candidate: {candidate.name}\n"
            f"Seniority: {candidate.seniority}\n"
            f"Skills: {', '.join(candidate.skills)}\n"
            f"Experience Summary:\n{candidate.experience_summary}\n\n"
            f"--- Target Job ---\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Description:\n{job.description[:2000]}\n\n"
            "Generate a tailored resume. Only use facts from the candidate's actual background."
        )
        if candidate.raw_cv_text:
            prompt += f"\n\nOriginal CV (source of truth):\n{candidate.raw_cv_text[:2000]}"

        return ai_complete(system, prompt, max_tokens=1500)

    @staticmethod
    def _fallback_generate(candidate: CandidateProfileInput, job: JobInput) -> str:
        relevant_skills = ", ".join(candidate.skills[:10])
        return (
            f"{candidate.name}\n"
            f"Target Role: {job.title} at {job.company}\n\n"
            "PROFESSIONAL SUMMARY\n"
            f"{candidate.experience_summary}\n\n"
            "RELEVANT SKILLS\n"
            f"{relevant_skills}\n\n"
            "ALIGNMENT\n"
            f"Prepared to contribute to the {job.title} role at {job.company}, "
            f"bringing expertise in {', '.join(candidate.skills[:3])} "
            f"and a track record of delivering results in technical environments."
        )
