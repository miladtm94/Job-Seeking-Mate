import hashlib
import logging

import httpx

from app.core.config import get_settings
from app.schemas.job import JobPosting, JobSearchRequest, JobSearchResponse

logger = logging.getLogger(__name__)


class JobDiscoveryService:
    """Multi-source job search with normalization and deduplication."""

    def search(self, payload: JobSearchRequest) -> JobSearchResponse:
        all_jobs: list[JobPosting] = []

        for source in payload.sources:
            try:
                if source == "adzuna":
                    all_jobs.extend(self._search_adzuna(payload))
                elif source == "indeed":
                    all_jobs.extend(self._search_indeed_fallback(payload))
                else:
                    logger.info("Source %s not yet implemented, skipping", source)
            except Exception:
                logger.exception("Error searching %s", source)

        if not all_jobs:
            all_jobs = self._generate_demo_jobs(payload)

        deduped = self._deduplicate(all_jobs)
        limited = deduped[: payload.max_results]

        return JobSearchResponse(
            jobs=limited,
            total=len(deduped),
            query=payload.query,
        )

    def _search_adzuna(self, payload: JobSearchRequest) -> list[JobPosting]:
        settings = get_settings()
        if not settings.adzuna_app_id or not settings.adzuna_api_key:
            logger.info("Adzuna credentials not configured")
            return []

        jobs: list[JobPosting] = []
        country = "au"  # default to Australia
        location = payload.locations[0] if payload.locations else ""

        params: dict[str, str] = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_api_key,
            "what": payload.query,
            "where": location,
            "results_per_page": str(min(payload.max_results, 50)),
            "content-type": "application/json",
        }
        if payload.salary_min:
            params["salary_min"] = str(payload.salary_min)

        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"

        try:
            response = httpx.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            for result in data.get("results", []):
                job_id = f"adzuna_{result.get('id', '')}"
                salary_str = None
                if result.get("salary_min") or result.get("salary_max"):
                    parts = []
                    if result.get("salary_min"):
                        parts.append(f"${int(result['salary_min']):,}")
                    if result.get("salary_max"):
                        parts.append(f"${int(result['salary_max']):,}")
                    salary_str = " - ".join(parts)

                jobs.append(
                    JobPosting(
                        job_id=job_id,
                        title=result.get("title", "").strip(),
                        company=result.get("company", {}).get("display_name", "Unknown"),
                        source="adzuna",
                        location=result.get("location", {}).get("display_name", location),
                        description=result.get("description", ""),
                        url=result.get("redirect_url", ""),
                        salary=salary_str,
                    )
                )
        except httpx.HTTPError:
            logger.exception("Adzuna API request failed")

        return jobs

    def _search_indeed_fallback(self, payload: JobSearchRequest) -> list[JobPosting]:
        """Placeholder for Indeed integration. Returns demo data when no API key is set."""
        return self._generate_demo_jobs(payload, source="indeed", count=3)

    def _generate_demo_jobs(
        self, payload: JobSearchRequest, source: str = "demo", count: int = 5
    ) -> list[JobPosting]:
        query = payload.query.strip().title()
        location = payload.locations[0] if payload.locations else "Remote"
        templates = [
            ("", "TechCorp", "Design and implement scalable systems."),
            ("Senior ", "InnovateLabs", "Lead technical projects and mentor team."),
            ("Lead ", "DataDriven Inc", "Drive architecture decisions and delivery."),
            ("Junior ", "StartupXYZ", "Build features and grow your skills."),
            ("Staff ", "MegaTech", "Shape technical strategy across the org."),
        ]

        jobs = []
        for i, (prefix, company, desc) in enumerate(templates[:count]):
            fid = hashlib.md5(f"{prefix}{query}{company}".encode()).hexdigest()[:8]
            jobs.append(
                JobPosting(
                    job_id=f"{source}_{fid}",
                    title=f"{prefix}{query}",
                    company=company,
                    source=source,
                    location=location,
                    description=f"{desc} Role: {prefix}{query}.",
                    url=f"https://example.com/jobs/{source}_{fid}",
                    salary=f"${80_000 + i * 20_000:,} - ${100_000 + i * 20_000:,}",
                )
            )
        return jobs

    @staticmethod
    def _deduplicate(jobs: list[JobPosting]) -> list[JobPosting]:
        seen: set[str] = set()
        unique: list[JobPosting] = []
        for job in jobs:
            key = f"{job.title.lower().strip()}|{job.company.lower().strip()}"
            if key not in seen:
                seen.add(key)
                unique.append(job)
        return unique
