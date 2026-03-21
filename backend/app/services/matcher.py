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

    def score(self, payload: MatchScoreRequest) -> MatchScoreResponse:
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

        # Try AI explanation, fall back to heuristic
        explanation = self._ai_explanation(payload, match_score, key_matching, missing)
        if not explanation:
            explanation = (
                f"Matched {len(key_matching)}/{len(required)} required skills. "
                f"{len(missing)} gaps identified. "
                f"Experience ({payload.candidate.years_experience}yr) and location "
                f"{'match' if location_match else 'mismatch'} adjusted score to {match_score}."
            )

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
        )

    def score_batch(self, payload: BatchMatchRequest) -> BatchMatchResponse:
        results = []
        rejected = 0
        for job in payload.jobs:
            req = MatchScoreRequest(candidate=payload.candidate, job=job)
            result = self.score(req)
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

    def _ai_explanation(
        self,
        payload: MatchScoreRequest,
        score: int,
        matching: list[str],
        missing: list[str],
    ) -> str | None:
        system = (
            "You are a career advisor. Write a brief (2-3 sentence) explanation of how well "
            "this candidate matches the job. Be specific and actionable. No markdown."
        )
        prompt = (
            f"Job: {payload.job.title} at {payload.job.company}\n"
            f"Candidate skills: {', '.join(payload.candidate.skills[:10])}\n"
            f"Experience: {payload.candidate.years_experience}yr "
            f"({payload.candidate.seniority})\n"
            f"Matching skills: {', '.join(s.title() for s in matching)}\n"
            f"Missing skills: {', '.join(s.title() for s in missing)}\n"
            f"Score: {score}/100"
        )
        return ai_complete(system, prompt, max_tokens=256)

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
