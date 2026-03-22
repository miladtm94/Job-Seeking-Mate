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
                elif source == "jsearch":
                    all_jobs.extend(self._search_jsearch(payload))
                elif source == "indeed":
                    # "indeed" source now routes to JSearch if key is available
                    all_jobs.extend(self._search_jsearch(payload))
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
        country = get_settings().adzuna_country
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

    def _search_jsearch(self, payload: JobSearchRequest) -> list[JobPosting]:
        """Search via JSearch (RapidAPI) — aggregates Indeed, LinkedIn, Glassdoor, and more."""
        settings = get_settings()
        if not settings.jsearch_api_key:
            logger.info("JSEARCH_API_KEY not configured — skipping")
            return []

        location = payload.locations[0] if payload.locations else ""
        # JSearch works best with "role in city, country" format
        query = f"{payload.query} in {location}" if location else payload.query

        params: dict[str, str] = {
            "query": query,
            "page": "1",
            "num_pages": "1",
            "date_posted": "month",
        }
        if payload.remote_only:
            params["remote_jobs_only"] = "true"

        try:
            response = httpx.get(
                "https://jsearch.p.rapidapi.com/search",
                params=params,
                headers={
                    "X-RapidAPI-Key": settings.jsearch_api_key,
                    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            jobs: list[JobPosting] = []
            for r in data.get("data", []):
                salary_str = None
                lo = r.get("job_min_salary")
                hi = r.get("job_max_salary")
                currency = r.get("job_salary_currency", "")
                if lo or hi:
                    parts = []
                    if lo:
                        parts.append(f"{currency}${int(lo):,}")
                    if hi:
                        parts.append(f"{currency}${int(hi):,}")
                    salary_str = " – ".join(parts)
                    period = r.get("job_salary_period", "")
                    if period:
                        salary_str += f" /{period.lower()}"

                jobs.append(
                    JobPosting(
                        job_id=f"jsearch_{r.get('job_id', '')}",
                        title=r.get("job_title", "").strip(),
                        company=r.get("employer_name", "Unknown"),
                        source="indeed" if "indeed" in r.get("job_apply_link", "").lower()
                               else r.get("job_publisher", "jsearch").lower(),
                        location=(
                            f"{r.get('job_city', '')}, {r.get('job_country', '')}".strip(", ")
                            or location
                        ),
                        description=r.get("job_description", "")[:2000],
                        url=r.get("job_apply_link") or r.get("job_google_link", ""),
                        salary=salary_str,
                    )
                )
            return jobs
        except httpx.HTTPError:
            logger.exception("JSearch API request failed")
            return []

    def _generate_demo_jobs(
        self, payload: JobSearchRequest, source: str = "demo", count: int = 5
    ) -> list[JobPosting]:
        query = payload.query.strip().title()
        location = payload.locations[0] if payload.locations else "Remote"
        templates = [
            ("", "TechCorp", "Design and implement scalable systems for a fast-growing product."),
            ("Senior ", "InnovateLabs", "Lead technical projects and mentor a team of engineers."),
            ("Lead ", "DataDriven Inc", "Drive architecture decisions and own delivery."),
            ("Junior ", "StartupXYZ", "Build features and grow your skills in a supportive team."),
            ("Staff ", "MegaTech", "Shape technical strategy across multiple product lines."),
            ("Principal ", "Visionary AI", "Own the technical roadmap for a core AI platform."),
            ("", "FinanceHub", "Work on high-impact features serving millions of users."),
            ("Senior ", "CloudScale", "Build and operate distributed infrastructure at scale."),
        ]  # fmt: skip

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
