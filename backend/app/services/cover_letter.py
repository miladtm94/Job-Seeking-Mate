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
            "You are an expert cover letter writer acting as a senior recruiter who knows what "
            "hiring panels look for. Write a targeted, high-impact cover letter that maximizes "
            "shortlisting probability.\n\n"
            "STRICT REQUIREMENTS:\n"
            "- Length: 250–350 words exactly (count carefully)\n"
            "- Opening: role-specific — prove you read the JD; NOT 'I am excited to apply'\n"
            "- Body: evidence-based alignment — cite specific skills/projects from the candidate's "
            "background that directly address JD priorities; no vague claims\n"
            "- Do NOT repeat resume bullet points verbatim — add narrative context and insight\n"
            "- No clichés: ban 'passionate', 'excited', 'thrilled', 'team player', 'hardworking'\n"
            "- Closing: confident call to action, one sentence\n"
            "- Tone: persuasive, direct, natural — not stiff or overly formal\n"
            "- Output plain text only, no markdown, no headers\n"
            "- NEVER fabricate experience or qualifications"
        )
        salary_line = f"Salary: {job.salary}\n" if job.salary else ""
        prompt = (
            f"CANDIDATE\n"
            f"Name: {candidate.name}\n"
            f"Seniority: {candidate.seniority}\n"
            f"Skills: {', '.join(candidate.skills)}\n"
            f"Background:\n{candidate.experience_summary}\n\n"
            f"TARGET ROLE\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location}\n"
            f"{salary_line}"
            f"Job Description:\n{job.description[:2500]}\n\n"
            "Write the cover letter now. Must be 250–350 words. "
            "Start with the candidate's name and a role-specific opening sentence."
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
