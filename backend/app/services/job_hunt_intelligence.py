from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.ai_client import ai_complete

logger = logging.getLogger(__name__)

SKILL_CLUSTER_MAP: dict[str, set[str]] = {
    "programming": {
        "python",
        "java",
        "javascript",
        "typescript",
        "go",
        "rust",
        "c++",
        "c#",
        "scala",
        "ruby",
        "php",
        "kotlin",
        "swift",
        "react",
        "react native",
        "nextjs",
        "next.js",
        "vue",
        "angular",
        "node.js",
        "node",
        "express",
        "fastapi",
        "django",
        "flask",
        "spring",
        "laravel",
        "html",
        "css",
    },
    "ml_ai": {
        "machine learning",
        "deep learning",
        "generative ai",
        "llm",
        "nlp",
        "computer vision",
        "tensorflow",
        "pytorch",
        "scikit-learn",
        "keras",
        "reinforcement learning",
        "rag",
        "langchain",
        "hugging face",
        "feature engineering",
        "mlops",
        "openai",
        "prompt engineering",
    },
    "data": {
        "sql",
        "postgresql",
        "mysql",
        "mongodb",
        "pandas",
        "numpy",
        "spark",
        "data engineering",
        "etl",
        "warehouse",
        "airflow",
        "dbt",
        "snowflake",
        "bigquery",
        "redshift",
        "tableau",
        "power bi",
        "data science",
        "statistics",
    },
    "tools": {
        "docker",
        "kubernetes",
        "aws",
        "gcp",
        "azure",
        "terraform",
        "github actions",
        "ci/cd",
        "jenkins",
        "git",
        "linux",
        "rest api",
        "graphql",
        "microservices",
        "gitlab",
        "jira",
        "slack",
        "selenium",
        "playwright",
        "terraform",
    },
}

INDUSTRY_HINTS: list[tuple[set[str], list[str]]] = [
    ({"bank", "payments", "fintech", "trading", "wealth", "insurance"}, ["FinTech", "Banking"]),
    ({"hospital", "patient", "medical", "clinical", "healthcare", "biotech"}, ["Healthcare", "Biotech"]),
    ({"retail", "ecommerce", "shop", "marketplace", "consumer"}, ["Retail", "E-commerce"]),
    ({"telecom", "wireless", "communications", "5g", "rf"}, ["Telecommunications"]),
    ({"education", "edtech", "learning", "university"}, ["Education", "EdTech"]),
    ({"logistics", "supply chain", "transport", "fleet"}, ["Logistics"]),
    ({"cybersecurity", "security operations", "threat", "siem"}, ["Cybersecurity"]),
    ({"defence", "defense", "radar", "aerospace", "satellite"}, ["Defense", "Aerospace"]),
    ({"government", "public sector", "citizen"}, ["Government"]),
    ({"saas", "b2b", "platform"}, ["SaaS"]),
]

ROLE_HINTS: list[tuple[set[str], list[str]]] = [
    (
        {"machine learning", "deep learning", "ai", "llm", "computer vision", "nlp"},
        ["Machine Learning Engineer", "ML Engineer", "AI Engineer", "Applied Scientist", "Data Scientist"],
    ),
    (
        {"data engineering", "etl", "warehouse", "spark", "airflow", "dbt"},
        ["Data Engineer", "Senior Data Engineer", "Analytics Engineer", "Data Platform Engineer"],
    ),
    (
        {"data science", "analytics", "experimentation", "statistics"},
        ["Data Scientist", "Senior Data Scientist", "Machine Learning Engineer", "Analytics Scientist"],
    ),
    (
        {"backend", "fastapi", "django", "flask", "microservices", "api"},
        ["Backend Engineer", "Software Engineer", "Backend Developer", "Platform Engineer"],
    ),
    (
        {"full stack", "frontend", "react", "typescript", "javascript"},
        ["Full Stack Engineer", "Frontend Engineer", "Software Engineer", "Frontend Developer"],
    ),
    (
        {"devops", "cloud", "docker", "kubernetes", "terraform", "aws", "gcp", "azure"},
        ["Platform Engineer", "DevOps Engineer", "Cloud Engineer", "Site Reliability Engineer"],
    ),
    (
        {"wireless", "communications", "rf", "signal processing", "radar"},
        ["Signal Processing Engineer", "RF Engineer", "Research Engineer", "Communications Engineer"],
    ),
    (
        {"research", "scientist"},
        ["Research Engineer", "Research Scientist", "Applied Scientist"],
    ),
]

SENIORITY_PREFIX = {
    "junior": "Junior",
    "mid": "",
    "senior": "Senior",
    "staff": "Staff",
    "principal": "Principal",
}

SENIORITY_LEVELS = {"junior": 1, "mid": 2, "senior": 3, "staff": 4, "principal": 5}

# ---------------------------------------------------------------------------
# Platform-specific role title overrides
# ---------------------------------------------------------------------------
# Seek.com.au and Indeed.com.au are Australian job boards.  Some US-centric
# titles ("Staff Engineer", "Applied Scientist", "SRE") are uncommon in the
# AU job market and produce few results.  These mappings translate them to
# equivalent titles that actually appear in AU postings.
_PLATFORM_ROLE_OVERRIDES: dict[str, dict[str, str]] = {
    "seek": {
        "applied scientist":        "Data Scientist",
        "analytics scientist":      "Data Scientist",
        "staff engineer":           "Senior Software Engineer",
        "staff software engineer":  "Senior Software Engineer",
        "principal software engineer": "Principal Engineer",
        "site reliability engineer":"DevOps Engineer",
        "sre":                      "DevOps Engineer",
        "ml engineer":              "Machine Learning Engineer",
        "analytics engineer":       "Data Engineer",
        "data platform engineer":   "Data Engineer",
    },
    "indeed": {
        "applied scientist":        "Data Scientist",
        "analytics scientist":      "Data Scientist",
        "staff engineer":           "Senior Software Engineer",
        "staff software engineer":  "Senior Software Engineer",
        "site reliability engineer":"DevOps Engineer",
        "sre":                      "DevOps Engineer",
        "ml engineer":              "Machine Learning Engineer",
        "data platform engineer":   "Data Engineer",
    },
    "linkedin": {
        # LinkedIn global — US titles are well-indexed; only normalise short forms
        "ml engineer":  "Machine Learning Engineer",
        "sre":          "Site Reliability Engineer",
    },
}

# Location hints shown in the UI per platform
_PLATFORM_LOCATION_HINTS: dict[str, str] = {
    "seek": (
        "Seek works best with 'Suburb State' format — e.g. 'Sydney NSW', 'Melbourne VIC'. "
        "Leave blank to search all of Australia."
    ),
    "indeed": (
        "Enter a city name (e.g. 'Sydney') or leave blank for nationwide results."
    ),
    "linkedin": (
        "Enter a city (e.g. 'Sydney, New South Wales, Australia') "
        "or a short form like 'Sydney'. LinkedIn geocodes it automatically."
    ),
}

# State abbreviations used to reformat AU location strings for Seek
_AU_STATE_MAP: dict[str, str] = {
    "new south wales": "NSW",   "nsw": "NSW",
    "victoria":        "VIC",   "vic": "VIC",
    "queensland":      "QLD",   "qld": "QLD",
    "western australia": "WA",  "wa":  "WA",
    "south australia": "SA",    "sa":  "SA",
    "tasmania":        "TAS",   "tas": "TAS",
    "northern territory": "NT", "nt":  "NT",
    "australian capital territory": "ACT", "act": "ACT",
}


def _normalise_location_seek(location: str) -> str:
    """Reformat a location string to 'City STATE' for Seek's search bar.

    Examples:
        "Sydney"                 → "Sydney"
        "Sydney, NSW"            → "Sydney NSW"
        "Sydney, New South Wales"→ "Sydney NSW"
        "Melbourne, Victoria"    → "Melbourne VIC"
        "Australia"              → ""  (means all-AU)
    """
    loc = location.strip()
    if not loc or loc.lower() in ("australia", "all australia", "all of australia", "remote"):
        return ""
    # Already has a known AU state abbreviation
    upper = loc.upper()
    for abbr in _AU_STATE_MAP.values():
        if abbr in upper.split():
            return loc  # already formatted
    # Try to extract "city, full-state-name"
    parts = [p.strip() for p in loc.replace(",", " ").split() if p.strip()]
    # Look for a known state name at the end
    for length in (3, 2, 1):
        if len(parts) >= length:
            candidate = " ".join(parts[-length:]).lower()
            if candidate in _AU_STATE_MAP:
                city_parts = parts[:-length]
                city = " ".join(city_parts).title() if city_parts else loc
                return f"{city} {_AU_STATE_MAP[candidate]}"
    return loc


def build_platform_queries(
    profile: dict[str, Any],
    platform: str,
    max_queries: int = 6,
) -> dict[str, Any]:
    """Build a complete, platform-tailored search plan for a candidate profile.

    Called by the search-plan API endpoint and by agents at runtime.

    Returns a dict with:
      queries         — list of platform-appropriate job title phrases
      location        — pre-formatted location string for this platform
      location_hint   — human-readable guidance shown in the UI
      work_type       — from profile.work_type
      salary_min      — from profile.salary_min
      max_jobs        — sensible default
      min_score       — sensible default
      date_range      — sensible default (days)
    """
    # 1. Generate generic job-title queries from the profile
    base_queries = build_search_queries(profile, max_queries=max_queries * 2)

    # 2. Apply platform-specific role overrides
    overrides = _PLATFORM_ROLE_OVERRIDES.get(platform.lower(), {})
    adjusted: list[str] = []
    for query in base_queries:
        replaced = overrides.get(query.lower(), query)
        adjusted.append(replaced)
    platform_queries = unique_preserve(adjusted)[:max_queries]

    # 3. Format location
    locations = profile.get("locations") or []
    raw_loc = (locations[0] if locations else "").strip()

    if platform.lower() == "seek":
        location = _normalise_location_seek(raw_loc)
    elif platform.lower() == "indeed":
        # Indeed AU: city name only, no state needed
        location = raw_loc.split(",")[0].strip() if raw_loc else "Australia"
    else:
        # LinkedIn: city + country suffix works best for AU
        location = raw_loc or "Australia"

    return {
        "queries":       platform_queries,
        "location":      location,
        "location_hint": _PLATFORM_LOCATION_HINTS.get(platform.lower(), ""),
        "work_type":     profile.get("work_type", "any"),
        "salary_min":    profile.get("salary_min"),
        "max_jobs":      20,
        "min_score":     60,
        "date_range":    7,
    }


def unique_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def titleize_skill(skill: str) -> str:
    normalized = re.sub(r"\s+", " ", skill.strip())
    if not normalized:
        return skill

    replacements = {
        "aws": "AWS",
        "gcp": "GCP",
        "sql": "SQL",
        "llm": "LLM",
        "ml": "ML",
        "ai": "AI",
        "nlp": "NLP",
        "rf": "RF",
        "ci/cd": "CI/CD",
        "c++": "C++",
        "c#": "C#",
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "fastapi": "FastAPI",
        "scikit-learn": "scikit-learn",
        "github actions": "GitHub Actions",
        "node.js": "Node.js",
        "mysql": "MySQL",
        "postgresql": "PostgreSQL",
        "fintech": "FinTech",
        "saas": "SaaS",
        "mlops": "MLOps",
        "openai": "OpenAI",
    }
    if normalized.lower() in replacements:
        return replacements[normalized.lower()]

    def replace_token(match: re.Match[str]) -> str:
        token = match.group(0)
        lowered = token.lower()
        if lowered in replacements:
            return replacements[lowered]
        if token.isupper() and len(token) <= 5:
            return token
        return token.capitalize()

    return re.sub(r"[A-Za-z0-9.+#/-]+", replace_token, normalized)


def normalize_role_label(role: str) -> str:
    cleaned = re.sub(r"\s+", " ", role.strip())
    if not cleaned:
        return role
    return _strip_known_seniority(cleaned)


def normalize_role_labels(roles: list[str]) -> list[str]:
    return unique_preserve([normalize_role_label(role) for role in roles if role.strip()])


def cluster_skills(skills: list[str]) -> dict[str, list[str]]:
    clusters = {name: [] for name in SKILL_CLUSTER_MAP}
    for skill in unique_preserve(skills):
        lowered = skill.lower()
        for cluster_name, known_skills in SKILL_CLUSTER_MAP.items():
            if lowered in known_skills:
                clusters[cluster_name].append(titleize_skill(skill))
                break
    return {name: unique_preserve(values) for name, values in clusters.items()}


def infer_target_roles(
    raw_cv_text: str,
    skills: list[str],
    domains: list[str],
    seniority: str,
) -> list[str]:
    text = f"{raw_cv_text.lower()} {' '.join(s.lower() for s in skills)} {' '.join(d.lower() for d in domains)}"
    roles: list[str] = []
    for keywords, candidates in ROLE_HINTS:
        if any(keyword in text for keyword in keywords):
            roles.extend(candidates)
        if len(roles) >= 5:
            break

    if not roles:
        primary = next(iter(unique_preserve(skills)), "Software")
        roles = [f"{titleize_skill(primary)} Engineer"]

    return normalize_role_labels(roles)[:5]


def build_resume_keywords(
    roles: list[str],
    skills: list[str],
    domains: list[str],
    industries: list[str] | None = None,
    strengths: list[str] | None = None,
) -> list[str]:
    keywords = roles[:4] + skills[:20] + domains[:8] + (industries or [])[:6] + (strengths or [])[:4]
    return unique_preserve([titleize_skill(keyword) for keyword in keywords])[:30]


def infer_industries(raw_cv_text: str, skills: list[str], domains: list[str]) -> list[str]:
    text = f"{raw_cv_text.lower()} {' '.join(s.lower() for s in skills)} {' '.join(d.lower() for d in domains)}"
    industries: list[str] = []
    for keywords, labels in INDUSTRY_HINTS:
        if any(keyword in text for keyword in keywords):
            industries.extend(labels)
    return unique_preserve(industries)[:6]


def _role_variants_for_platforms(role: str) -> list[str]:
    role_lower = role.lower()
    variants = [role]

    if "machine learning engineer" in role_lower or "ml engineer" in role_lower:
        variants.extend(["Machine Learning Engineer", "ML Engineer", "AI Engineer", "Applied Scientist", "Data Scientist"])
    elif "data scientist" in role_lower:
        variants.extend(["Data Scientist", "Machine Learning Engineer", "Applied Scientist", "Analytics Scientist"])
    elif "data engineer" in role_lower:
        variants.extend(["Data Engineer", "Analytics Engineer", "Data Platform Engineer", "Analytics Developer"])
    elif "backend" in role_lower:
        variants.extend(["Backend Engineer", "Backend Developer", "Software Engineer", "Platform Engineer"])
    elif "frontend" in role_lower:
        variants.extend(["Frontend Engineer", "Frontend Developer", "Software Engineer"])
    elif "full stack" in role_lower:
        variants.extend(["Full Stack Engineer", "Software Engineer", "Full Stack Developer"])
    elif "devops" in role_lower or "platform engineer" in role_lower or "cloud engineer" in role_lower:
        variants.extend(["Platform Engineer", "DevOps Engineer", "Cloud Engineer", "Site Reliability Engineer"])
    elif "signal processing" in role_lower or "rf engineer" in role_lower:
        variants.extend(["Signal Processing Engineer", "RF Engineer", "Communications Engineer", "Research Engineer"])

    return unique_preserve(variants)


def _strip_known_seniority(role: str) -> str:
    for prefix in ("Junior ", "Senior ", "Staff ", "Principal ", "Lead ", "Mid "):
        if role.startswith(prefix):
            return role[len(prefix) :]
    return role
def build_search_queries(
    profile: dict[str, Any],
    manual_keywords: str | None = None,
    max_queries: int = 6,
) -> list[str]:
    """Build platform-compatible search queries from a candidate profile.

    Queries are job-title phrases only — never raw skill keywords like "PyTorch"
    or "MLOps", which produce zero results on LinkedIn/Seek/Indeed autocomplete.
    """
    manual_queries = unique_preserve(
        [part.strip() for part in re.split(r"[\n;,]+", manual_keywords or "") if part.strip()]
    )
    base_roles = unique_preserve(
        list(profile.get("preferred_roles") or [])
        + list(profile.get("target_roles") or [])
    )
    if not base_roles:
        base_roles = infer_target_roles(
            profile.get("raw_cv_text", ""),
            profile.get("skills", []),
            profile.get("domains", []),
            profile.get("seniority", "mid"),
        )
    base_roles = normalize_role_labels(base_roles)
    expanded_roles = unique_preserve(
        [variant for role in base_roles for variant in _role_variants_for_platforms(role)]
    )

    seniority = str(profile.get("seniority", "mid")).lower()
    seniority_prefix = SENIORITY_PREFIX.get(seniority, "")
    work_type = str(profile.get("work_type") or "any")

    generated: list[str] = []
    role_queries = normalize_role_labels(expanded_roles)

    # 1. Plain role titles (already platform-compatible phrases)
    for role in role_queries:
        generated.append(role)
        if len(generated) >= max_queries:
            break

    # 2. Seniority-prefixed variants of top roles (e.g. "Senior Machine Learning Engineer")
    #    Only add if the role doesn't already start with a seniority word.
    if seniority_prefix:
        seniority_words = {p.lower() for p in SENIORITY_PREFIX.values() if p}
        for role in role_queries[:3]:
            first_word = role.split()[0].lower() if role.split() else ""
            if first_word not in seniority_words:
                generated.append(f"{seniority_prefix} {role}")
            if len(generated) >= max_queries * 2:
                break

    # 3. Remote variant for top role when work_type is remote
    if work_type == "remote" and role_queries:
        generated.append(f"Remote {role_queries[0]}")

    stored_queries = [normalize_role_label(query) for query in list(profile.get("search_queries") or [])]
    combined = manual_queries + generated + stored_queries
    return unique_preserve(combined)[:max_queries]


def _extract_json(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    return json.loads(raw)


class JobHuntIntelligenceService:
    def score_job(self, job: dict[str, Any], profile: dict[str, Any]) -> tuple[int, str, list[str], str]:
        heuristic = self._heuristic_score(job, profile)
        if not self._should_refine_with_ai(heuristic):
            return (
                heuristic["score"],
                heuristic["recommendation"],
                heuristic["missing_requirements"],
                heuristic["match_summary"],
            )
        try:
            system = (
                "You are a precise senior recruiter supporting an automated but user-controlled "
                "job hunt. Score the candidate against the job using EXACT weights:\n"
                "role/title alignment 30, skills overlap 40, experience/seniority 20, "
                "domain/ATS keyword fit 10.\n"
                "Be conservative. Recommend strong_apply only for clear, high-signal fits.\n"
                "Return JSON only with keys: score, recommendation, missing_requirements, "
                "match_summary, role_score, skills_score, experience_score, domain_score."
            )
            prompt = (
                "CANDIDATE\n"
                f"Target roles: {', '.join(profile.get('preferred_roles') or profile.get('target_roles') or [])}\n"
                f"Keywords: {', '.join(profile.get('keywords') or [])}\n"
                f"Programming: {', '.join((profile.get('skill_clusters') or {}).get('programming', []))}\n"
                f"ML/AI: {', '.join((profile.get('skill_clusters') or {}).get('ml_ai', []))}\n"
                f"Data: {', '.join((profile.get('skill_clusters') or {}).get('data', []))}\n"
                f"Tools: {', '.join((profile.get('skill_clusters') or {}).get('tools', []))}\n"
                f"Seniority: {profile.get('seniority', 'mid')}\n"
                f"Experience years: {profile.get('years_experience', 0)}\n"
                f"Domains: {', '.join(profile.get('domains') or [])}\n"
                f"Industries: {', '.join(profile.get('industries') or [])}\n"
                f"Summary: {profile.get('summary', '')[:500]}\n\n"
                "JOB\n"
                f"Title: {job.get('title', '')}\n"
                f"Company: {job.get('company', '')}\n"
                f"Location: {job.get('location', '')}\n"
                f"Description: {job.get('description', '')[:3500]}\n\n"
                "STAGE 1 HEURISTIC SCREEN\n"
                f"Initial score: {heuristic['score']}\n"
                f"Role overlap ratio: {heuristic['role_overlap_ratio']:.2f}\n"
                f"Skills overlap ratio: {heuristic['skills_overlap_ratio']:.2f}\n"
                f"Matched skills: {', '.join(heuristic['matching_keywords'][:8])}\n"
                f"Missing skills: {', '.join(heuristic['missing_requirements'][:8])}\n\n"
                "Return compact JSON only."
            )
            raw = ai_complete(system, prompt, max_tokens=250, task="score")
            if raw:
                data = _extract_json(raw)
                score = max(0, min(100, int(data.get("score", heuristic["score"]))))
                recommendation = str(data.get("recommendation", self._recommendation(score)))
                missing = unique_preserve(
                    [str(item) for item in data.get("missing_requirements", data.get("missing", heuristic["missing_requirements"]))]
                )[:8]
                summary = str(data.get("match_summary", heuristic["match_summary"])).strip() or heuristic["match_summary"]
                return score, recommendation, missing, summary
        except Exception as exc:
            logger.debug("Shared job score AI failed: %s", exc)
        return (
            heuristic["score"],
            heuristic["recommendation"],
            heuristic["missing_requirements"],
            heuristic["match_summary"],
        )

    def _heuristic_score(
        self,
        job: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        title = str(job.get("title", ""))
        description = str(job.get("description", ""))
        text = f"{title} {description}".lower()

        roles = unique_preserve(
            list(profile.get("preferred_roles") or []) + list(profile.get("target_roles") or [])
        )
        profile_keywords = unique_preserve(
            list(profile.get("skills") or [])
            + list(profile.get("keywords") or [])
            + list(profile.get("domains") or [])
            + list(profile.get("industries") or [])
        )

        role_score = 0.0
        best_overlap = 0.0
        if roles:
            for role in roles:
                role_lower = role.lower()
                if role_lower in text:
                    best_overlap = 1.0
                    break
                role_tokens = [token for token in re.split(r"[^a-z0-9+#]+", role_lower) if token]
                if not role_tokens:
                    continue
                overlap = sum(1 for token in role_tokens if token in text) / len(role_tokens)
                best_overlap = max(best_overlap, overlap)
            role_score = round(best_overlap * 30, 1)

        known_job_keywords = unique_preserve(
            [
                titleize_skill(skill)
                for skill in self._extract_job_keywords(text, profile_keywords)
            ]
        )
        candidate_keyword_lookup = {keyword.lower() for keyword in profile_keywords}
        matching_keywords = [kw for kw in known_job_keywords if kw.lower() in candidate_keyword_lookup]
        missing_requirements = [kw for kw in known_job_keywords if kw.lower() not in candidate_keyword_lookup]
        skills_overlap_ratio = (
            len(matching_keywords) / len(known_job_keywords)
            if known_job_keywords else
            min(1.0, sum(1 for keyword in profile_keywords[:12] if keyword.lower() in text) / 6.0)
        )

        if known_job_keywords:
            skills_score = round(skills_overlap_ratio * 40, 1)
        else:
            loose_hits = sum(1 for keyword in profile_keywords[:12] if keyword.lower() in text)
            skills_score = min(40.0, loose_hits * 5.0)

        experience_score = self._experience_score(title, description, profile)
        domain_score = self._domain_score(text, profile)

        score = int(round(role_score + skills_score + experience_score + domain_score))
        score = max(0, min(100, score))
        recommendation = self._recommendation(score)

        summary_bits: list[str] = []
        if roles:
            summary_bits.append(f"best role alignment is {roles[0]}")
        if matching_keywords:
            summary_bits.append(f"matched {', '.join(matching_keywords[:4])}")
        if missing_requirements:
            summary_bits.append(f"gaps include {', '.join(missing_requirements[:3])}")
        if not summary_bits:
            summary_bits.append("fit is based mainly on general title and experience similarity")

        summary = f"Score {score}/100: " + "; ".join(summary_bits) + "."
        return {
            "score": score,
            "recommendation": recommendation,
            "missing_requirements": missing_requirements[:8],
            "match_summary": summary,
            "matching_keywords": matching_keywords[:8],
            "role_overlap_ratio": best_overlap,
            "skills_overlap_ratio": skills_overlap_ratio,
        }

    @staticmethod
    def _should_refine_with_ai(heuristic: dict[str, Any]) -> bool:
        score = int(heuristic.get("score", 0) or 0)
        role_overlap = float(heuristic.get("role_overlap_ratio", 0.0) or 0.0)
        skills_overlap = float(heuristic.get("skills_overlap_ratio", 0.0) or 0.0)
        return (
            score >= 55
            and role_overlap >= 0.34
            and skills_overlap >= 0.18
        )

    @staticmethod
    def _extract_job_keywords(text: str, profile_keywords: list[str]) -> list[str]:
        flattened = {
            skill
            for skills in SKILL_CLUSTER_MAP.values()
            for skill in skills
        }
        flattened.update(keyword.lower() for keyword in profile_keywords)
        ordered = sorted(flattened, key=len, reverse=True)
        return [keyword for keyword in ordered if keyword and keyword in text][:12]

    @staticmethod
    def _experience_score(title: str, description: str, profile: dict[str, Any]) -> float:
        text = f"{title} {description}".lower()
        candidate_level = SENIORITY_LEVELS.get(str(profile.get("seniority", "mid")).lower(), 2)
        candidate_years = int(profile.get("years_experience", 0) or 0)

        required_level = 2
        for level, rank in SENIORITY_LEVELS.items():
            if level in text:
                required_level = rank
                break
        if "lead" in text and required_level < 4:
            required_level = 4

        diff = abs(candidate_level - required_level)
        base = 20.0 if diff == 0 else 16.0 if diff == 1 else max(8.0, 20.0 - diff * 5.0)

        year_match = re.search(r"(\d+)\+?\s+years", text)
        if year_match:
            required_years = int(year_match.group(1))
            if candidate_years >= required_years:
                base = min(20.0, base + 2.0)
            else:
                gap = required_years - candidate_years
                base = max(4.0, base - gap * 2.5)
        return round(max(0.0, min(20.0, base)), 1)

    @staticmethod
    def _domain_score(text: str, profile: dict[str, Any]) -> float:
        domains = [domain.lower() for domain in profile.get("domains") or []]
        keywords = [keyword.lower() for keyword in profile.get("keywords") or []][:10]
        industries = [industry.lower() for industry in profile.get("industries") or []][:6]
        signals = unique_preserve(domains + keywords + industries)
        if not signals:
            return 5.0
        hits = sum(1 for signal in signals if signal in text)
        return round(min(10.0, (hits / max(len(signals), 1)) * 10.0), 1)

    def filter_job(self, job: dict[str, Any], criteria: dict[str, Any]) -> str | None:
        salary_min = int(criteria.get("salary_min") or 0)
        if salary_min:
            salary_floor = self._parse_salary_floor(str(job.get("salary") or ""))
            if salary_floor is not None and salary_floor < salary_min:
                return f"Salary appears below your minimum of ${salary_min:,}"

        desired_industries = unique_preserve([str(item) for item in criteria.get("industries") or []])
        if desired_industries:
            text = f"{job.get('title', '')} {job.get('company', '')} {job.get('description', '')}"
            detected = infer_industries(text, [], [])
            if detected and not any(
                detected_item.lower() == desired_item.lower()
                for detected_item in detected
                for desired_item in desired_industries
            ):
                return f"Posting looks closer to {', '.join(detected[:2])} than your target industries"

        desired_work_type = str(criteria.get("work_type") or "any").lower()
        if desired_work_type in {"remote", "hybrid", "onsite"}:
            text = f"{job.get('title', '')} {job.get('location', '')} {job.get('description', '')}".lower()
            if desired_work_type == "remote" and "hybrid" in text and "remote" not in text:
                return "Job appears to be hybrid rather than remote"
            if desired_work_type == "onsite" and "remote" in text:
                return "Job appears to be remote rather than onsite"

        return None

    @staticmethod
    def _parse_salary_floor(salary_text: str) -> int | None:
        if not salary_text:
            return None
        numbers = [int(match.replace(",", "")) for match in re.findall(r"(\d[\d,]{3,})", salary_text)]
        if not numbers:
            return None
        return min(numbers)

    @staticmethod
    def _recommendation(score: int) -> str:
        if score >= 80:
            return "strong_apply"
        if score >= 68:
            return "apply"
        if score >= 52:
            return "maybe"
        return "skip"
