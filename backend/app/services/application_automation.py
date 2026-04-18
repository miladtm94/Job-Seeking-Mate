import json
import logging
import uuid

from app.core.ai_client import ai_complete
from app.schemas.application import ApplicationGenerateRequest, ApplicationGenerateResponse
from app.services.cover_letter import CoverLetterService
from app.services.resume_tailor import ResumeTailoringService

logger = logging.getLogger(__name__)


# Step 4 decision thresholds from the expert recruiter workflow
_THRESHOLD_USE_AS_IS = 65
_THRESHOLD_SURGICAL  = 50
_THRESHOLD_NEW_RESUME = 41


class ApplicationAutomationService:
    """Orchestrates application artifact generation using the expert recruiter workflow.

    Decision logic (Step 4):
    ≥ 65  → use resume as-is + cover letter + strategic positioning
    50–64 → surgical resume improvements (Step 9) + cover letter
    41–49 → full new tailored resume (Step 5) + cover letter
    ≤ 40  → do_not_apply — return early with explanation only
    """

    def __init__(self) -> None:
        self.resume_service = ResumeTailoringService()
        self.cover_service = CoverLetterService()

    def generate(self, payload: ApplicationGenerateRequest) -> ApplicationGenerateResponse:
        application_id = f"app_{uuid.uuid4().hex[:12]}"
        score = payload.match_score  # may be None if not passed

        # Step 4 decision logic
        decision, surgical = self._decide(score)

        if decision == "do_not_apply":
            return ApplicationGenerateResponse(
                application_id=application_id,
                customized_resume="",
                tailored_cover_letter="",
                talking_points=[],
                readiness_checklist=["Score ≤ 40 — this role is a poor fit. Do not apply."],
                match_score=score,
                mode=payload.mode,
                status="rejected_by_filter",
                decision="do_not_apply",
                shortlisting_probability="Low",
            )

        # Generate artifacts
        resume = self.resume_service.generate(payload.candidate_profile, payload.job, surgical=surgical)
        letter = self.cover_service.generate(payload.candidate_profile, payload.job)
        talking_points = self._generate_talking_points(payload)

        # Strategic positioning + ATS + risks (Step 6 + partial Step 10)
        positioning_data = self._generate_strategic_positioning(payload, score)

        checklist = self._build_checklist(decision, payload.mode)

        return ApplicationGenerateResponse(
            application_id=application_id,
            customized_resume=resume,
            tailored_cover_letter=letter,
            talking_points=talking_points,
            readiness_checklist=checklist,
            match_score=score,
            mode=payload.mode,
            status="prepared",
            decision=decision,
            shortlisting_probability=positioning_data.get("shortlisting_probability", "Medium"),
            strategic_positioning=positioning_data.get("key_strengths", []),
            recruiter_risks=positioning_data.get("risks_objections", []),
            ats_keywords=positioning_data.get("ats_keywords", {}),
            resume_improvements=positioning_data.get("resume_improvements", []),
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _decide(score: int | None) -> tuple[str, bool]:
        """Return (decision_label, surgical_mode) based on score."""
        if score is None:
            return "use_as_is", False
        if score >= _THRESHOLD_USE_AS_IS:
            return "use_as_is", False
        if score >= _THRESHOLD_SURGICAL:
            return "improve", True          # surgical improvements
        if score >= _THRESHOLD_NEW_RESUME:
            return "new_resume_needed", False  # full new resume
        return "do_not_apply", False

    @staticmethod
    def _build_checklist(decision: str, mode: str) -> list[str]:
        base = [
            "Facts verified against source CV — no fabrications",
            "ATS-safe formatting maintained",
            "Cover letter personalized for role and company",
            "Talking points prepared for interview",
        ]
        if decision == "improve":
            base.insert(0, "Apply surgical resume improvements before submitting")
        elif decision == "new_resume_needed":
            base.insert(0, "Review new resume carefully — verify all facts against original CV")
        if mode != "auto":
            base.append("Human approval required before submission")
        return base

    def _generate_talking_points(self, payload: ApplicationGenerateRequest) -> list[str]:
        system = (
            "You are an expert interview coach. Generate 4–5 sharp talking points for a job interview. "
            "Each point must connect a specific candidate achievement or skill to a concrete JD requirement. "
            "Use STAR structure implicitly (situation/task implied, action + result explicit). "
            "Be specific, not generic. Return a JSON array of strings only — no markdown, no wrapper."
        )
        prompt = (
            f"Candidate seniority: {payload.candidate_profile.seniority}\n"
            f"Skills: {', '.join(payload.candidate_profile.skills[:15])}\n"
            f"Background: {payload.candidate_profile.experience_summary[:600]}\n\n"
            f"Role: {payload.job.title} at {payload.job.company}\n"
            f"JD priorities:\n{payload.job.description[:800]}"
        )
        raw = ai_complete(system, prompt, max_tokens=600)
        if raw:
            try:
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1]
                    cleaned = cleaned.rsplit("```", 1)[0]
                return json.loads(cleaned)
            except (json.JSONDecodeError, IndexError):
                pass
        return [
            f"Highlight depth in {', '.join(payload.candidate_profile.skills[:3])} with concrete project examples",
            f"Align past outcomes to {payload.job.title} responsibilities directly",
            f"Demonstrate awareness of {payload.job.company}'s domain and technical challenges",
            "Prepare 2 questions about team structure, tech stack decisions, and growth trajectory",
        ]

    def _generate_strategic_positioning(
        self, payload: ApplicationGenerateRequest, score: int | None
    ) -> dict:
        """Steps 6 + 10 — strategic positioning, ATS keywords, recruiter risks, salary estimate."""
        system = (
            "You are an expert senior recruiter and ATS optimization specialist. "
            "Provide strategic positioning advice and application intelligence for this candidate. "
            "Return ONLY a valid JSON object — no markdown, no text outside JSON."
        )
        prompt = (
            "Analyze this candidate-job pair and return a JSON object with these exact keys:\n\n"
            "{\n"
            '  "key_strengths": ["specific strength 1", "..."],\n'
            '  "risks_objections": ["recruiter concern 1", "..."],\n'
            '  "positioning_strategy": "2-3 lines: narrative shift, what to emphasize/downplay",\n'
            '  "shortlisting_probability": "Low" | "Medium" | "High",\n'
            '  "ats_keywords": {"keyword": "present"|"partial"|"missing"},\n'
            '  "resume_improvements": ["surgical tweak 1", "..."],\n'
            '  "salary_min": 0,\n'
            '  "salary_max": 0,\n'
            '  "salary_notes": "1-line justification based on market benchmarks"\n'
            "}\n\n"
            "Rules:\n"
            "- key_strengths: 3–5 specific, evidence-based strengths (not generic)\n"
            "- risks_objections: 3–5 honest recruiter concerns\n"
            "- ats_keywords: 10–15 top JD keywords with classification\n"
            "- resume_improvements: 3–5 surgical bullet/keyword tweaks (only if score < 65)\n"
            "- salary: realistic market min/max in local currency; ensure min < max\n\n"
            f"CANDIDATE\n"
            f"Seniority: {payload.candidate_profile.seniority}\n"
            f"Skills: {', '.join(payload.candidate_profile.skills[:20])}\n"
            f"Background: {payload.candidate_profile.experience_summary[:500]}\n"
            f"Match score: {score}/100\n\n"
            f"ROLE\n"
            f"Title: {payload.job.title}\n"
            f"Company: {payload.job.company}\n"
            f"Location: {payload.job.location}\n"
            f"Salary listed: {payload.job.salary or 'not provided'}\n"
            f"JD:\n{payload.job.description[:2000]}"
        )
        raw = ai_complete(system, prompt, max_tokens=1200)
        if raw:
            try:
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1]
                    cleaned = cleaned.rsplit("```", 1)[0]
                return json.loads(cleaned)
            except (json.JSONDecodeError, IndexError, ValueError):
                logger.warning("Failed to parse strategic positioning JSON")
        return {}
