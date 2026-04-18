import logging

from app.core.ai_client import ai_complete
from app.schemas.application import CandidateProfileInput, JobInput

logger = logging.getLogger(__name__)


class ResumeTailoringService:
    """AI-powered resume tailoring with ATS optimization and truthfulness constraints.

    Two modes driven by match score (Step 4 decision logic):
    - surgical=True  (score 50–64): targeted bullet rewrites + keyword insertions only (Step 9)
    - surgical=False (score 41–49): full new tailored resume (Step 5)
    """

    def generate(self, candidate: CandidateProfileInput, job: JobInput, surgical: bool = False) -> str:
        ai_result = (
            self._ai_surgical(candidate, job)
            if surgical
            else self._ai_full_generate(candidate, job)
        )
        return ai_result or self._fallback_generate(candidate, job)

    def _ai_full_generate(self, candidate: CandidateProfileInput, job: JobInput) -> str | None:
        """Step 5 — generate a fully new tailored resume (triggered when score is 41–49)."""
        system = (
            "You are an expert resume writer and ATS optimization specialist. Generate a NEW "
            "tailored resume for this candidate targeting the specific job. This is triggered "
            "because the candidate needs strategic repositioning to be competitive.\n\n"
            "REQUIREMENTS:\n"
            "1. NEVER fabricate experience, credentials, or qualifications\n"
            "2. Strategically reposition the candidate's real background for this role\n"
            "3. ATS-optimized: naturally integrate the top JD keywords throughout\n"
            "4. Impact-driven bullets: action verb + quantified outcome (estimate reasonably if "
            "exact metrics aren't provided, based on the seniority level)\n"
            "5. Industry-aligned language for this specific role and sector\n"
            "6. 1–2 pages — concise and dense with value, no filler\n"
            "7. Sections in order: PROFESSIONAL SUMMARY | CORE SKILLS | EXPERIENCE | EDUCATION\n"
            "8. Summary: 3–4 lines, tailored to this exact role, includes top 3 JD keywords\n"
            "9. Output plain text with clear section headers in ALL CAPS, no markdown"
        )
        cv_section = (
            f"\nOriginal CV (source of truth — do not invent beyond this):\n{candidate.raw_cv_text[:2500]}"
            if candidate.raw_cv_text
            else ""
        )
        prompt = (
            f"CANDIDATE\n"
            f"Name: {candidate.name}\n"
            f"Seniority: {candidate.seniority}\n"
            f"Skills: {', '.join(candidate.skills)}\n"
            f"Background:\n{candidate.experience_summary}\n"
            f"{cv_section}\n\n"
            f"TARGET ROLE\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Description:\n{job.description[:2500]}\n\n"
            "Generate the new tailored resume now."
        )
        return ai_complete(system, prompt, max_tokens=2000)

    def _ai_surgical(self, candidate: CandidateProfileInput, job: JobInput) -> str | None:
        """Step 9 — surgical improvements only (triggered when score is 50–64).

        Does NOT rewrite the full resume. Provides targeted bullet rewrites,
        missing keyword insertions, and positioning tweaks only.
        """
        system = (
            "You are an expert ATS optimization specialist and resume coach. Provide ONLY "
            "surgical improvements to the existing resume — do NOT rewrite the full resume.\n\n"
            "Format your response with these exact sections:\n\n"
            "SUMMARY REWRITE\n"
            "(Write a new 3–4 line professional summary targeting this specific role. "
            "Include the top 3 JD keywords naturally. Be specific, not generic.)\n\n"
            "BULLET REWRITES\n"
            "(Rewrite 3–5 of the weakest/most relevant existing bullets to be more impactful "
            "and keyword-aligned. Use format: Original: ... → Improved: ...)\n\n"
            "MISSING ATS KEYWORDS\n"
            "(List 5–8 important JD keywords missing from the resume. For each, suggest "
            "where/how to naturally add it.)\n\n"
            "POSITIONING NOTES\n"
            "(1–3 lines: what to emphasize vs downplay; any narrative shift needed)\n\n"
            "Rules:\n"
            "- NEVER fabricate experience\n"
            "- Only suggest improvements grounded in the candidate's actual background\n"
            "- Be surgical and specific — no generic advice\n"
            "- Output plain text, no markdown"
        )
        cv_section = (
            f"Existing Resume:\n{candidate.raw_cv_text[:2500]}"
            if candidate.raw_cv_text
            else f"Skills: {', '.join(candidate.skills)}\nBackground: {candidate.experience_summary}"
        )
        prompt = (
            f"CANDIDATE\n"
            f"Name: {candidate.name}\n"
            f"Seniority: {candidate.seniority}\n"
            f"{cv_section}\n\n"
            f"TARGET ROLE\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Description:\n{job.description[:2500]}\n\n"
            "Provide surgical improvements now."
        )
        return ai_complete(system, prompt, max_tokens=1500)

    @staticmethod
    def _fallback_generate(candidate: CandidateProfileInput, job: JobInput) -> str:
        relevant_skills = ", ".join(candidate.skills[:10])
        return (
            f"{candidate.name}\n"
            f"Target Role: {job.title} at {job.company}\n\n"
            "PROFESSIONAL SUMMARY\n"
            f"{candidate.experience_summary}\n\n"
            "CORE SKILLS\n"
            f"{relevant_skills}\n\n"
            "ALIGNMENT\n"
            f"Prepared to contribute to the {job.title} role at {job.company}, "
            f"bringing expertise in {', '.join(candidate.skills[:3])} "
            f"and a track record of delivering results in technical environments."
        )
