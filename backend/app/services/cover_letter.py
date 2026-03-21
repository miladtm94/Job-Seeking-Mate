import logging

from app.core.ai_client import ai_complete
from app.schemas.application import CandidateProfileInput, JobInput

logger = logging.getLogger(__name__)


class CoverLetterService:
    """AI-powered cover letter generation with company-specific personalization."""

    def generate(self, candidate: CandidateProfileInput, job: JobInput) -> str:
        ai_letter = self._ai_generate(candidate, job)
        if ai_letter:
            return ai_letter
        return self._fallback_generate(candidate, job)

    def _ai_generate(self, candidate: CandidateProfileInput, job: JobInput) -> str | None:
        system = (
            "You are an expert cover letter writer. Write a compelling, personalized cover letter. "
            "Structure:\n"
            "1. Role-specific introduction (why this role excites the candidate)\n"
            "2. Skills & experience alignment (concrete examples)\n"
            "3. Company-specific motivation (if info available)\n"
            "4. Strong closing with call to action\n\n"
            "Rules:\n"
            "- Avoid generic language and cliches\n"
            "- Be concise (250-350 words)\n"
            "- Be specific about how skills match the role\n"
            "- NEVER fabricate experience\n"
            "- Use a professional but warm tone\n"
            "- Output plain text, no markdown"
        )
        prompt = (
            f"Candidate: {candidate.name}\n"
            f"Skills: {', '.join(candidate.skills)}\n"
            f"Experience Summary:\n{candidate.experience_summary}\n\n"
            f"--- Target Job ---\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location}\n"
            f"Description:\n{job.description[:2000]}\n\n"
            "Write a targeted cover letter."
        )
        return ai_complete(system, prompt, max_tokens=1000)

    @staticmethod
    def _fallback_generate(candidate: CandidateProfileInput, job: JobInput) -> str:
        top_skills = ", ".join(candidate.skills[:5])
        return (
            f"Dear Hiring Team at {job.company},\n\n"
            f"I am writing to express my strong interest in the {job.title} position. "
            f"With expertise in {top_skills}, I am confident in my ability to make meaningful "
            f"contributions to your team.\n\n"
            f"{candidate.experience_summary}\n\n"
            f"My technical background aligns well with the requirements of this role, and I am "
            f"eager to bring my skills in {', '.join(candidate.skills[:3])} to {job.company}. "
            f"I thrive in collaborative environments and am passionate about delivering "
            f"high-quality solutions.\n\n"
            f"I would welcome the opportunity to discuss how my experience and enthusiasm can "
            f"support your team's goals. Thank you for considering my application.\n\n"
            f"Sincerely,\n{candidate.name}"
        )
