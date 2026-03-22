import hashlib
import json
import logging
import re

from app.core.ai_client import ai_complete
from app.schemas.candidate import CandidateIngestRequest, CandidateIngestResponse

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    """Extract the first JSON object from a string, stripping markdown fences and preamble."""
    # Try a fenced code block first (```json ... ``` or ``` ... ```)
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    # Fall back to the first { ... } block in the text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    raise ValueError("No JSON object found in response")


SKILL_LEXICON = {
    "python", "java", "javascript", "typescript", "go", "rust", "c++", "c#", "ruby", "scala",
    "fastapi", "django", "flask", "spring", "express", "nextjs", "react", "angular", "vue",
    "tensorflow", "pytorch", "scikit-learn", "keras", "pandas", "numpy", "spark",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "cassandra",
    "docker", "kubernetes", "terraform", "ansible", "jenkins", "github actions",
    "aws", "gcp", "azure", "cloudflare",
    "machine learning", "deep learning", "nlp", "computer vision", "data engineering",
    "signal processing", "embedded systems",
    "graphql", "rest api", "grpc", "kafka", "rabbitmq",
    "git", "ci/cd", "agile", "scrum",
}

DOMAIN_KEYWORDS = {
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "signal processing": "Signal Processing",
    "communications": "Communications",
    "rf": "RF Systems",
    "nlp": "Natural Language Processing",
    "computer vision": "Computer Vision",
    "data engineer": "Data Engineering",
    "data scien": "Data Science",
    "backend": "Backend Engineering",
    "frontend": "Frontend Engineering",
    "full stack": "Full Stack Development",
    "devops": "DevOps",
    "cloud": "Cloud Infrastructure",
    "cybersecurity": "Cybersecurity",
    "mobile": "Mobile Development",
}


class CVParserService:
    """Parses raw CV text into a normalized profile using AI + heuristic fallback."""

    def parse(self, payload: CandidateIngestRequest) -> CandidateIngestResponse:
        fingerprint = hashlib.sha1(payload.email.encode("utf-8")).hexdigest()[:10]
        candidate_id = f"cand_{fingerprint}"

        ai_result = self._ai_parse(payload.raw_cv_text)
        if ai_result:
            return CandidateIngestResponse(
                candidate_id=candidate_id,
                skills=ai_result.get("skills", []),
                domains=ai_result.get("domains", []),
                seniority=ai_result.get("seniority", "mid"),
                years_experience=ai_result.get("years_experience", 3),
                strengths=ai_result.get("strengths", []),
                skill_gaps=ai_result.get("skill_gaps", []),
                summary=ai_result.get("summary", ""),
            )

        return self._heuristic_parse(payload, candidate_id)

    def _ai_parse(self, cv_text: str) -> dict | None:
        system = (
            "You are an expert CV/resume analyst. Extract structured information from the CV text. "
            "Return valid JSON with keys: skills (list), domains (list), "
            "seniority (junior|mid|senior|staff|principal), years_experience (int), "
            "strengths (list of 3-5 key strengths), skill_gaps (list of skills the candidate could "
            "improve for top tech roles), summary (2-3 sentence professional summary)."
        )
        prompt = f"Analyze this CV and return structured JSON:\n\n{cv_text[:4000]}"
        raw = ai_complete(system, prompt, max_tokens=1024)
        if not raw:
            return None
        try:
            return json.loads(_extract_json(raw))
        except (json.JSONDecodeError, ValueError):
            logger.warning("AI CV parse returned invalid JSON, falling back to heuristic")
            return None

    def _heuristic_parse(
        self, payload: CandidateIngestRequest, candidate_id: str
    ) -> CandidateIngestResponse:
        text = payload.raw_cv_text.lower()

        matched_skills = sorted({skill.title() for skill in SKILL_LEXICON if skill in text})
        domains = sorted({label for key, label in DOMAIN_KEYWORDS.items() if key in text})

        years = self._extract_experience_years(text)
        seniority = self._infer_seniority(years)
        strengths = self._derive_strengths(matched_skills)
        skill_gaps = self._infer_gaps(matched_skills)

        summary = (
            f"{payload.name} is a {seniority}-level professional with "
            f"{years} years of experience in {', '.join(domains[:3]) or 'technology'}."
        )

        return CandidateIngestResponse(
            candidate_id=candidate_id,
            skills=matched_skills,
            domains=domains,
            seniority=seniority,
            years_experience=years,
            strengths=strengths,
            skill_gaps=skill_gaps,
            summary=summary,
        )

    @staticmethod
    def _extract_experience_years(text: str) -> int:
        match = re.search(r"(\d+)\+?\s+years", text)
        if match:
            return int(match.group(1))
        return 3

    @staticmethod
    def _infer_seniority(years: int) -> str:
        if years >= 10:
            return "principal"
        if years >= 8:
            return "staff"
        if years >= 5:
            return "senior"
        if years >= 2:
            return "mid"
        return "junior"

    @staticmethod
    def _derive_strengths(skills: list[str]) -> list[str]:
        strengths: list[str] = []
        if "Python" in skills:
            strengths.append("Production-grade Python development")
        if "Fastapi" in skills or "Django" in skills or "Flask" in skills:
            strengths.append("API design and web service delivery")
        if "Machine Learning" in skills or "Deep Learning" in skills:
            strengths.append("ML modeling and experimentation")
        if "Docker" in skills or "Kubernetes" in skills:
            strengths.append("Container orchestration and DevOps")
        if "Aws" in skills or "Gcp" in skills or "Azure" in skills:
            strengths.append("Cloud infrastructure expertise")
        if "React" in skills or "Angular" in skills or "Vue" in skills:
            strengths.append("Modern frontend development")
        if not strengths:
            strengths.append("Cross-domain adaptability")
        return strengths

    @staticmethod
    def _infer_gaps(skills: list[str]) -> list[str]:
        core_skills = {"Python", "Sql", "Aws", "Docker", "Git", "Ci/Cd"}
        return sorted(skill for skill in core_skills if skill not in set(skills))
