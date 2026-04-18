import json
import logging

from app.core.ai_client import ai_complete
from app.schemas.matching import (
    BatchMatchRequest,
    BatchMatchResponse,
    MatchBreakdown,
    MatchScoreRequest,
    MatchScoreResponse,
)

logger = logging.getLogger(__name__)

SENIORITY_LEVELS = {"junior": 1, "mid": 2, "senior": 3, "staff": 4, "principal": 5}


class MatchingService:
    """Multi-dimensional scoring with AI-powered explanations."""

    def score(self, payload: MatchScoreRequest, fast: bool = False) -> MatchScoreResponse:
        candidate_skills = {skill.lower() for skill in payload.candidate.skills}
        required = {skill.lower() for skill in payload.job.required_skills}
        preferred = {skill.lower() for skill in payload.job.preferred_skills}

        key_matching = sorted(required.intersection(candidate_skills))
        missing = sorted(required.difference(candidate_skills))

        # Skill score: 40% weight
        skill_score = (len(key_matching) / max(len(required), 1)) * 40
        preferred_overlap = len(preferred.intersection(candidate_skills))
        skill_score += (preferred_overlap / max(len(preferred), 1)) * 10 if preferred else 5

        # Experience score: 15% weight
        exp_score = min(payload.candidate.years_experience / 10, 1.0) * 15

        # Domain score: 15% weight
        domain_score = self._compute_domain_score(payload)

        # Location score: 10% weight
        location_match = any(
            loc.lower() in payload.job.location.lower() for loc in payload.candidate.locations
        )
        location_score = 10 if location_match or "remote" in payload.job.location.lower() else 3

        # Seniority score: 10% weight
        seniority_score = self._compute_seniority_score(payload)

        breakdown = MatchBreakdown(
            skill_score=round(skill_score, 1),
            experience_score=round(exp_score, 1),
            domain_score=round(domain_score, 1),
            location_score=round(location_score, 1),
            seniority_score=round(seniority_score, 1),
        )

        raw_score = skill_score + exp_score + domain_score + location_score + seniority_score
        match_score = int(min(max(raw_score, 0), 100))

        recommendation = self._recommendation(match_score)
        probability = round(min(match_score / 100 + 0.05, 0.95), 2)

        fit_reasons = self._generate_fit_reasons(payload, key_matching, location_match)
        improvement_suggestions = self._generate_improvements(missing, payload)

        heuristic_explanation = (
            f"Matched {len(key_matching)}/{max(len(required), 1)} required skills. "
            f"{len(missing)} gaps identified. "
            f"Experience ({payload.candidate.years_experience}yr) and location "
            f"{'match' if location_match else 'mismatch'} adjusted score to {match_score}."
        )

        # In fast mode (batch scoring) skip AI; in single-job mode run full expert evaluation
        ai_eval: dict = {}
        if not fast:
            ai_eval = self._ai_full_evaluate(payload, match_score, key_matching, missing) or {}

        explanation = ai_eval.get("explanation") or heuristic_explanation
        if ai_eval.get("fit_reasons"):
            fit_reasons = ai_eval["fit_reasons"]

        return MatchScoreResponse(
            job_id=payload.job.job_id,
            match_score=match_score,
            key_matching_skills=[skill.title() for skill in key_matching],
            missing_skills=[skill.title() for skill in missing],
            recommendation=recommendation,
            probability_of_success=probability,
            explanation=explanation,
            fit_reasons=fit_reasons,
            improvement_suggestions=improvement_suggestions,
            breakdown=breakdown,
            early_rejection=bool(ai_eval.get("early_rejection", False)),
            rejection_reason=ai_eval.get("rejection_reason"),
            technical_fit=int(ai_eval.get("technical_fit", 0)),
            experience_fit=int(ai_eval.get("experience_fit", 0)),
            ats_match=int(ai_eval.get("ats_match", 0)),
            shortlisting_probability=ai_eval.get("shortlisting_probability", "Medium"),
            ats_keywords=ai_eval.get("ats_keywords", {}),
            recruiter_risks=ai_eval.get("risks", []),
            strategic_positioning=ai_eval.get("strategic_positioning", []),
        )

    def score_batch(self, payload: BatchMatchRequest) -> BatchMatchResponse:
        results = []
        rejected = 0
        for job in payload.jobs:
            req = MatchScoreRequest(candidate=payload.candidate, job=job)
            result = self.score(req, fast=True)
            if result.match_score >= 40:  # include even low-scores for visibility
                results.append(result)
            else:
                rejected += 1

        results.sort(key=lambda r: r.match_score, reverse=True)
        return BatchMatchResponse(results=results, rejected_count=rejected)

    def _compute_domain_score(self, payload: MatchScoreRequest) -> float:
        if not payload.candidate.domains or not payload.job.description:
            return 7.5
        desc_lower = payload.job.description.lower()
        matches = sum(1 for d in payload.candidate.domains if d.lower() in desc_lower)
        return min((matches / max(len(payload.candidate.domains), 1)) * 15, 15)

    def _compute_seniority_score(self, payload: MatchScoreRequest) -> float:
        title_lower = payload.job.title.lower()
        job_seniority = 2  # default to mid
        for level, rank in SENIORITY_LEVELS.items():
            if level in title_lower:
                job_seniority = rank
                break
        if "lead" in title_lower or "principal" in title_lower:
            job_seniority = 4

        candidate_level = SENIORITY_LEVELS.get(payload.candidate.seniority, 2)
        diff = abs(candidate_level - job_seniority)
        if diff == 0:
            return 10
        if diff == 1:
            return 7
        return max(10 - diff * 3, 0)

    @staticmethod
    def _generate_fit_reasons(
        payload: MatchScoreRequest, key_matching: list[str], location_match: bool
    ) -> list[str]:
        reasons = []
        if key_matching:
            reasons.append(
                f"Strong skill alignment: {', '.join(s.title() for s in key_matching[:5])}"
            )
        if payload.candidate.years_experience >= 5:
            reasons.append(
                f"{payload.candidate.years_experience} years of experience demonstrates depth"
            )
        if location_match:
            reasons.append("Location preference matches job location")
        if payload.candidate.preferred_roles:
            for role in payload.candidate.preferred_roles:
                if role.lower() in payload.job.title.lower():
                    reasons.append(f"Role '{payload.job.title}' aligns with preference '{role}'")
                    break
        return reasons

    @staticmethod
    def _generate_improvements(missing: list[str], payload: MatchScoreRequest) -> list[str]:
        suggestions = []
        if missing:
            suggestions.append(
                f"Consider developing: {', '.join(s.title() for s in missing[:3])}"
            )
        if payload.candidate.years_experience < 3:
            suggestions.append("Gain more hands-on project experience")
        return suggestions

    def _ai_full_evaluate(
        self,
        payload: MatchScoreRequest,
        score: int,
        matching: list[str],
        missing: list[str],
    ) -> dict | None:
        """Run the expert recruiter evaluation workflow (Steps 0–4, 6).

        Returns a structured dict with ATS analysis, multi-dimensional scores,
        shortlisting probability, recruiter risks, and strategic positioning.
        """
        system = (
            "You are an expert senior recruiter, hiring manager, and ATS optimization specialist "
            "with deep experience across academia and industry. You evaluate candidates rigorously, "
            "think like a hiring panel, and optimize applications for maximum shortlisting probability. "
            "Be analytical, critical, and evidence-based. Avoid generic advice.\n\n"
            "Return ONLY a valid JSON object — no markdown fences, no explanation outside the JSON."
        )
        prompt = (
            "Evaluate this candidate for the job below and return a JSON object with these exact keys:\n\n"
            "{\n"
            '  "early_rejection": false,\n'
            '  "rejection_reason": null,\n'
            '  "ats_keywords": {\n'
            '    "<keyword>": "present" | "partial" | "missing"\n'
            "  },\n"
            '  "technical_fit": 0,\n'
            '  "experience_fit": 0,\n'
            '  "ats_match": 0,\n'
            '  "shortlisting_probability": "Low" | "Medium" | "High",\n'
            '  "explanation": "2-3 sentence honest summary",\n'
            '  "fit_reasons": ["concrete strength 1", "..."],\n'
            '  "risks": ["recruiter objection 1", "..."],\n'
            '  "strategic_positioning": ["positioning tip 1", "..."]\n'
            "}\n\n"
            "Rules:\n"
            "- early_rejection: true ONLY if domain, seniority, or core skills are fundamentally "
            "misaligned (not just a stretch)\n"
            "- ats_keywords: extract 10–15 top JD keywords; classify each\n"
            "- technical_fit / experience_fit / ats_match: score each 0–100 based on real hiring standards\n"
            "- fit_reasons: 3–5 specific, evidence-based strengths (not generic)\n"
            "- risks: 3–5 honest recruiter objections\n"
            "- strategic_positioning: 3–5 actionable tips (narrative shift, what to emphasize/downplay)\n\n"
            f"CANDIDATE\n"
            f"Seniority: {payload.candidate.seniority}\n"
            f"Experience: {payload.candidate.years_experience} years\n"
            f"Skills: {', '.join(payload.candidate.skills[:20])}\n"
            f"Domains: {', '.join(payload.candidate.domains)}\n"
            f"Preferred roles: {', '.join(payload.candidate.preferred_roles)}\n\n"
            f"JOB\n"
            f"Title: {payload.job.title}\n"
            f"Company: {payload.job.company}\n"
            f"Matching skills (from heuristic): {', '.join(s.title() for s in matching)}\n"
            f"Missing skills (from heuristic): {', '.join(s.title() for s in missing)}\n"
            f"Heuristic score: {score}/100\n\n"
            f"Job Description:\n{payload.job.description[:3000]}"
        )
        raw = ai_complete(system, prompt, max_tokens=1200)
        if not raw:
            return None
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                cleaned = cleaned.rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError, ValueError):
            logger.warning("Failed to parse AI evaluation JSON")
            return None

    @staticmethod
    def _recommendation(score: int) -> str:
        if score >= 75:
            return "strong_apply"
        if score >= 60:
            return "apply"
        if score >= 45:
            return "maybe"
        return "skip"

    @staticmethod
    def extract_skills_from_description(description: str) -> tuple[list[str], list[str]]:
        """Extract required and preferred skills from a job description using AI."""
        system = (
            "Extract skills from this job description. Return JSON with two keys: "
            "'required' (list of must-have skills) and 'preferred' (list of nice-to-have skills). "
            "Only return valid JSON."
        )
        raw = ai_complete(system, description[:3000], max_tokens=512)
        if not raw:
            return [], []
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                cleaned = cleaned.rsplit("```", 1)[0]
            data = json.loads(cleaned)
            return data.get("required", []), data.get("preferred", [])
        except (json.JSONDecodeError, IndexError):
            return [], []
