import hashlib
import json
import logging
import re

from app.core.ai_client import ai_complete
from app.schemas.candidate import (
    CandidateIngestRequest,
    CandidateIngestResponse,
    CandidateSkillClusters,
)
from app.services.job_hunt_intelligence import (
    build_resume_keywords,
    build_search_queries,
    cluster_skills,
    infer_industries,
    infer_target_roles,
)

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
    "php", "kotlin", "swift",
    "fastapi", "django", "flask", "spring", "express", "nextjs", "next.js", "react", "react native", "angular", "vue",
    "tensorflow", "pytorch", "scikit-learn", "keras", "pandas", "numpy", "spark", "rag", "langchain", "openai", "mlops",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "cassandra", "snowflake", "bigquery", "dbt", "airflow", "tableau", "power bi",
    "docker", "kubernetes", "terraform", "ansible", "jenkins", "github actions", "playwright", "selenium",
    "aws", "gcp", "azure", "cloudflare",
    "machine learning", "deep learning", "nlp", "computer vision", "data engineering",
    "signal processing", "embedded systems", "wireless", "communications", "rf",
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
    "fintech": "FinTech Platforms",
    "healthcare": "Healthcare Technology",
    "ecommerce": "E-commerce Platforms",
    "telecom": "Telecommunications",
    "education": "Education Technology",
    "saas": "SaaS Platforms",
}


class CVParserService:
    """Parses raw CV text into a normalized profile using AI + heuristic fallback."""

    def parse(self, payload: CandidateIngestRequest) -> CandidateIngestResponse:
        # Hash email + CV content so each unique resume gets a distinct ID.
        # This allows multiple resumes from the same person (different files → different IDs).
        content_seed = payload.email + payload.raw_cv_text[:500]
        fingerprint = hashlib.sha1(content_seed.encode("utf-8")).hexdigest()[:10]
        candidate_id = f"cand_{fingerprint}"

        ai_result = self._ai_parse(payload.raw_cv_text)
        if ai_result:
            return self._build_response(payload, candidate_id, ai_result)

        return self._build_response(
            payload,
            candidate_id,
            self._heuristic_parse(payload),
        )

    def _ai_parse(self, cv_text: str) -> dict | None:
        system = (
            "You are an expert CV/resume analyst. Extract structured information from the CV text. "
            "Return valid JSON with keys: skills (list), skill_clusters (object with programming, "
            "ml_ai, data, tools arrays), domains (list), industries (list), target_roles (list), seniority "
            "(junior|mid|senior|staff|principal), years_experience (int), keywords (list), "
            "strengths (list of 3-5 key strengths), skill_gaps (list of skills the candidate could "
            "improve for top tech roles), summary (2-3 sentence professional summary), "
            "search_queries (list of 3-6 search strings for job hunting)."
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

    def _heuristic_parse(self, payload: CandidateIngestRequest) -> dict:
        text = payload.raw_cv_text.lower()

        matched_skills = sorted({skill for skill in SKILL_LEXICON if skill in text})
        domains = sorted({label for key, label in DOMAIN_KEYWORDS.items() if key in text})

        years = self._extract_experience_years(text)
        seniority = self._infer_seniority(years)
        formatted_skills = [self._format_skill(skill) for skill in matched_skills]
        strengths = self._derive_strengths(formatted_skills)
        skill_gaps = self._infer_gaps(formatted_skills)
        industries = infer_industries(payload.raw_cv_text, formatted_skills, domains)
        target_roles = infer_target_roles(payload.raw_cv_text, formatted_skills, domains, seniority)
        skill_clusters = cluster_skills(formatted_skills)
        keywords = build_resume_keywords(target_roles, formatted_skills, domains, industries, strengths)
        search_queries = build_search_queries(
            {
                "preferred_roles": payload.preferred_roles,
                "target_roles": target_roles,
                "skill_clusters": skill_clusters,
                "keywords": keywords,
                "skills": formatted_skills,
                "domains": domains,
                "industries": industries,
                "seniority": seniority,
                "work_type": payload.work_type,
                "raw_cv_text": payload.raw_cv_text,
            }
        )

        summary = (
            f"{payload.name} is a {seniority}-level professional with "
            f"{years} years of experience in {', '.join(domains[:3]) or 'technology'}."
        )

        return {
            "skills": formatted_skills,
            "skill_clusters": skill_clusters,
            "domains": domains,
            "industries": industries,
            "target_roles": target_roles,
            "seniority": seniority,
            "years_experience": years,
            "keywords": keywords,
            "search_queries": search_queries,
            "strengths": strengths,
            "skill_gaps": skill_gaps,
            "summary": summary,
        }

    def _build_response(
        self,
        payload: CandidateIngestRequest,
        candidate_id: str,
        parsed: dict,
    ) -> CandidateIngestResponse:
        skills = [self._format_skill(skill) for skill in parsed.get("skills", [])]
        skill_clusters = parsed.get("skill_clusters") or cluster_skills(skills)
        industries = parsed.get("industries") or infer_industries(
            payload.raw_cv_text,
            skills,
            parsed.get("domains", []),
        )
        target_roles = parsed.get("target_roles") or infer_target_roles(
            payload.raw_cv_text,
            skills,
            parsed.get("domains", []),
            parsed.get("seniority", "mid"),
        )
        keywords = parsed.get("keywords") or build_resume_keywords(
            target_roles,
            skills,
            parsed.get("domains", []),
            industries,
            parsed.get("strengths", []),
        )
        search_queries = parsed.get("search_queries") or build_search_queries(
            {
                "preferred_roles": payload.preferred_roles,
                "target_roles": target_roles,
                "skill_clusters": skill_clusters,
                "keywords": keywords,
                "skills": skills,
                "domains": parsed.get("domains", []),
                "industries": industries,
                "seniority": parsed.get("seniority", "mid"),
                "work_type": payload.work_type,
                "raw_cv_text": payload.raw_cv_text,
            }
        )

        return CandidateIngestResponse(
            candidate_id=candidate_id,
            skills=skills,
            skill_clusters=CandidateSkillClusters.model_validate(skill_clusters),
            domains=parsed.get("domains", []),
            industries=industries,
            target_roles=target_roles,
            seniority=parsed.get("seniority", "mid"),
            years_experience=parsed.get("years_experience", 3),
            keywords=keywords,
            search_queries=search_queries,
            strengths=parsed.get("strengths", []),
            skill_gaps=parsed.get("skill_gaps", []),
            summary=parsed.get("summary", ""),
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
        core_skills = {"Python", "SQL", "AWS", "Docker", "Git", "CI/CD"}
        return sorted(skill for skill in core_skills if skill not in set(skills))

    @staticmethod
    def _format_skill(skill: str) -> str:
        replacements = {
            "aws": "AWS",
            "gcp": "GCP",
            "sql": "SQL",
            "nlp": "NLP",
            "ci/cd": "CI/CD",
            "c++": "C++",
            "c#": "C#",
            "github actions": "GitHub Actions",
        }
        return replacements.get(skill.lower(), skill.title())
