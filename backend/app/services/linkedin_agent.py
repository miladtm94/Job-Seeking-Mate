"""LinkedIn agentic job-hunt service.

Logs in to LinkedIn, searches for jobs matching the user's criteria, scores
each against their profile, and auto-applies via Easy Apply for strong matches
— streaming live events back to the caller over a WebSocket.

Usage
-----
Called from the /ws/agent/linkedin/{session_id} WebSocket endpoint.

Events emitted
--------------
{"type": "progress",    "step": str, "message": str}
{"type": "job_found",   "job": {title, company, location, url, easy_apply, job_id}}
{"type": "job_scored",  "job_id": str, "score": int, "recommendation": str}
{"type": "applying",    "job_id": str, "message": str}
{"type": "confirm",     "field": str, "label": str, "suggestion": str, "confidence": float}
{"type": "applied",     "job_id": str, "message": str}
{"type": "skipped",     "job_id": str, "reason": str}
{"type": "screenshot",  "data": str}   # base64 JPEG
{"type": "success",     "message": str}
{"type": "error",       "message": str}
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import urllib.parse
from typing import Any, Callable, Coroutine

from app.services.browser_launcher import launch_for_agent
from app.services.job_hunt_intelligence import (
    JobHuntIntelligenceService,
    build_platform_queries,
    build_search_queries,
)

logger = logging.getLogger(__name__)

Event  = dict[str, Any]
SendFn = Callable[[Event], Coroutine]

_LINKEDIN_JOBS_HOME = "https://www.linkedin.com/jobs/"
_CDP_PORT = 9224

# Score threshold to auto-apply without asking
AUTO_APPLY_THRESHOLD = 60
# Score threshold to skip entirely
SKIP_THRESHOLD = 40
# Delay between applications (seconds) — looks human, avoids rate-limiting
INTER_APPLY_DELAY = 45

_job_hunt_service = JobHuntIntelligenceService()


class LinkedInAgent:
    """Drives a visible Playwright browser through LinkedIn job search + Easy Apply."""

    TIMEOUT_MS = 15_000

    async def _human_pause(self, page, minimum_ms: int = 120, maximum_ms: int = 380) -> None:
        await page.wait_for_timeout(random.randint(minimum_ms, maximum_ms))

    async def _type_like_human(self, page, selector: str, value: str) -> None:
        locator = page.locator(selector).first
        await locator.click()
        await self._human_pause(page, 120, 260)
        await locator.fill("")           # clear any existing value
        await self._human_pause(page, 60, 120)
        for char in value:
            await page.keyboard.type(char, delay=random.randint(55, 130))
        await self._human_pause(page, 100, 200)

    async def _confirm_search_plan(
        self,
        send_event: SendFn,
        reply_queue: asyncio.Queue,
        profile: dict,
        criteria: dict,
        queries: list[str],
        location: str,
    ) -> dict | None:
        plan = {
            "queries": queries,
            "location": location,
            "max_jobs": int(criteria.get("max_jobs", 100) or 100),
            "min_score": int(criteria.get("min_score", AUTO_APPLY_THRESHOLD) or AUTO_APPLY_THRESHOLD),
            "date_range": int(criteria.get("date_range", 7) or 7),
            "salary_min": criteria.get("salary_min"),
            "industries": list(criteria.get("industries") or []),
            "work_type": criteria.get("work_type", "any"),
            "target_roles": list(profile.get("preferred_roles") or profile.get("target_roles") or [])[:6],
        }
        await send_event({
            "type": "confirm",
            "field": "search_plan",
            "label": "Review the LinkedIn search plan. Edit the JSON if needed, then click Confirm to start scraping.",
            "suggestion": json.dumps(plan, indent=2),
            "confidence": 1.0,
        })
        reply = await reply_queue.get()
        if reply.get("action") == "cancel":
            return None
        if reply.get("action") == "edit" and reply.get("value"):
            try:
                edited = json.loads(reply["value"])
                if isinstance(edited, dict):
                    return edited
            except Exception:
                await send_event({
                    "type": "progress",
                    "step": "search",
                    "message": "Edited search plan was not valid JSON, so the original plan will be used.",
                })
        return plan

    @staticmethod
    def _normalize_autocomplete_text(value: str) -> str:
        return " ".join(value.lower().replace(",", " ").split())

    async def _click_best_suggestion(self, page, selectors: list[str], desired: str) -> bool:
        desired_norm = self._normalize_autocomplete_text(desired)
        best_locator = None
        best_score = -1
        for selector in selectors:
            try:
                options = page.locator(selector)
                count = await options.count()
                for index in range(min(count, 8)):
                    option = options.nth(index)
                    if not await option.is_visible(timeout=300):
                        continue
                    text = (await option.inner_text()).strip()
                    if not text:
                        continue
                    text_norm = self._normalize_autocomplete_text(text)
                    score = 0
                    if text_norm == desired_norm:
                        score = 100
                    elif desired_norm in text_norm:
                        score = 90
                    elif text_norm in desired_norm:
                        score = 80
                    else:
                        desired_tokens = set(desired_norm.split())
                        text_tokens = set(text_norm.split())
                        score = len(desired_tokens & text_tokens) * 10
                    if score > best_score:
                        best_score = score
                        best_locator = option
            except Exception:
                continue
        if best_locator and best_score >= 10:
            await best_locator.click()
            await page.wait_for_timeout(450)
            return True
        return False

    async def _type_autocomplete(
        self,
        page,
        selectors: list[str],
        value: str,
        suggestion_sels: list[str] | None = None,
    ) -> bool:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if not await locator.is_visible(timeout=2000):
                    continue
                await locator.click()
                await self._human_pause(page, 120, 240)
                await page.keyboard.press("Control+a")
                await self._human_pause(page, 60, 140)
                await page.keyboard.press("Delete")
                await self._human_pause(page, 90, 220)
                await locator.type(value, delay=random.randint(55, 130))
                await page.wait_for_timeout(700)

                if suggestion_sels and await self._click_best_suggestion(page, suggestion_sels, value):
                    return True

                await locator.press("Tab")
                await page.wait_for_timeout(200)
                return True
            except Exception:
                continue
        return False

    async def run(
        self,
        session_id: str,
        credentials: dict,        # {email, password}
        profile: dict,            # candidate profile
        criteria: dict,           # {keywords, location, max_jobs, min_score}
        send_event: SendFn,
        reply_queue: asyncio.Queue,
    ) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            await send_event({"type": "error", "message": "Playwright not installed."})
            return

        try:
            async with async_playwright() as pw:
                ctx, page, cleanup = await launch_for_agent(pw, "linkedin", _CDP_PORT)
                try:
                    # ── 1. Login ──────────────────────────────────────────────────
                    logged_in = await self._login(page, credentials, send_event, reply_queue)
                    if not logged_in:
                        return

                    runtime_criteria = dict(criteria)
                    if runtime_criteria.get("queries"):
                        runtime_queries = list(runtime_criteria["queries"])
                        runtime_location = str(runtime_criteria.get("location", "Australia")).strip() or "Australia"
                    else:
                        # Build platform-tailored search plan from the resume
                        plan = build_platform_queries(profile, "linkedin", max_queries=6)
                        runtime_queries = plan["queries"]
                        runtime_location = str(runtime_criteria.get("location") or plan["location"] or "Australia").strip()
                        # Merge sensible defaults the user didn't override
                        for key in ("work_type", "min_score", "max_jobs", "date_range"):
                            if not runtime_criteria.get(key):
                                runtime_criteria[key] = plan.get(key)
                    confirmed_plan = await self._confirm_search_plan(
                        send_event, reply_queue, profile, runtime_criteria, runtime_queries, runtime_location
                    )
                    if confirmed_plan is None:
                        return
                    runtime_criteria.update({k: v for k, v in confirmed_plan.items() if k != "queries"})
                    runtime_queries = list(confirmed_plan.get("queries") or runtime_queries)
                    runtime_location = str(confirmed_plan.get("location", runtime_location)).strip() or runtime_location
                    max_jobs = int(runtime_criteria.get("max_jobs", 100) or 100)
                    min_score = int(runtime_criteria.get("min_score", AUTO_APPLY_THRESHOLD) or AUTO_APPLY_THRESHOLD)

                    # ── 2. Search ─────────────────────────────────────────────────
                    jobs: list[dict] = []
                    for idx, query in enumerate(runtime_queries, start=1):
                        remaining = max_jobs - len(jobs)
                        if remaining <= 0:
                            break
                        await send_event({
                            "type": "progress",
                            "step": "search",
                            "message": f"Running query {idx}/{len(runtime_queries)} on LinkedIn: {query}",
                        })
                        jobs.extend(await self._search_jobs(page, query, runtime_location, remaining, runtime_criteria, profile, send_event))
                    if not jobs:
                        await send_event({"type": "error", "message": "No Easy Apply jobs found for your search."})
                        return

                    applied = 0
                    # ── 3. Score + apply loop ─────────────────────────────────────
                    for job in jobs:
                        try:
                            cancelled = await self._process_job(
                                page, job, profile, runtime_criteria, min_score,
                                send_event, reply_queue,
                            )
                            if cancelled:
                                break
                            if job.get("_applied"):
                                applied += 1
                                if applied < len(jobs):
                                    await send_event({"type": "progress", "step": "delay",
                                                      "message": f"Waiting {INTER_APPLY_DELAY}s before next application…"})
                                    await asyncio.sleep(INTER_APPLY_DELAY)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            logger.exception("Error processing job %s", job.get("title"))
                            await send_event({"type": "progress", "step": "error",
                                              "message": f"Skipped '{job.get('title')}': {exc}"})

                    await send_event({
                        "type": "success",
                        "message": f"Agent finished. Applied to {applied} job(s) out of {len(jobs)} found.",
                    })
                finally:
                    await cleanup()

        except asyncio.CancelledError:
            await send_event({"type": "error", "message": "Agent session cancelled."})
        except Exception as exc:
            logger.exception("LinkedIn agent failed")
            await send_event({"type": "error", "message": f"Unexpected error: {exc}"})

    # ── login ─────────────────────────────────────────────────────────────────

    async def _login(self, page, credentials, send_event, reply_queue) -> bool:
        await send_event({"type": "progress", "step": "login", "message": "Opening LinkedIn login…"})
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        try:
            await self._type_like_human(page, '#username', credentials["email"])
            await self._type_like_human(page, '#password', credentials["password"])
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=self.TIMEOUT_MS)
        except Exception:
            pass

        # Verify login succeeded
        if "feed" in page.url or "mynetwork" in page.url or "jobs" in page.url:
            await send_event({"type": "progress", "step": "login", "message": "✓ Logged in to LinkedIn"})
            await self._screenshot(page, send_event)
            return True

        # May need verification / CAPTCHA
        await send_event({
            "type": "confirm", "field": "login",
            "label": "LinkedIn requires verification — please complete it in the browser",
            "suggestion": "Complete the login/verification step, then click Confirm to continue.",
            "confidence": 0.0,
        })
        reply = await reply_queue.get()
        if reply.get("action") == "cancel":
            return False

        await send_event({"type": "progress", "step": "login", "message": "✓ Logged in to LinkedIn"})
        await self._screenshot(page, send_event)
        return True

    # ── search ────────────────────────────────────────────────────────────────

    async def _search_jobs(self, page, keywords: str, location: str, max_jobs: int, criteria: dict, profile: dict, send_event) -> list[dict]:
        await send_event({"type": "progress", "step": "search",
                          "message": f"Searching LinkedIn for {keywords!r} in {location!r}…"})

        # ── Build search URL directly (reliable, no fragile form-filling) ─────
        date_range = int(criteria.get("date_range", 7) or 7)
        _tpr_map = [(1, 86400), (3, 259200), (7, 604800), (14, 1209600), (30, 2592000)]
        tpr_seconds = next((s for d, s in _tpr_map if d >= date_range), 2592000)

        search_url = (
            "https://www.linkedin.com/jobs/search/?"
            + urllib.parse.urlencode({
                "keywords": keywords,
                "location": location,
                "f_AL": "true",           # Easy Apply only
                "f_TPR": f"r{tpr_seconds}",
                "distance": "50",
            })
        )
        await page.goto(search_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)

        # Extra experience / work-type filters via LinkedIn's filter dropdowns
        await self._apply_linkedin_filters(page, criteria, profile, send_event)
        await self._screenshot(page, send_event)

        jobs: list[dict] = []
        page_num = 0
        while len(jobs) < max_jobs:
            page_num += 1
            await send_event({"type": "progress", "step": "search",
                               "message": f"Scanning page {page_num}…"})

            new_jobs = await self._extract_job_cards(page)
            if not new_jobs:
                break

            for job in new_jobs:
                if len(jobs) >= max_jobs:
                    break
                if not any(j["job_id"] == job["job_id"] for j in jobs):
                    jobs.append(job)
                    await send_event({"type": "job_found", "job": job})

            # Next page
            try:
                next_btn = page.locator('button[aria-label="View next page"]').first
                if await self._is_visible(next_btn):
                    await next_btn.click()
                    await page.wait_for_timeout(2000)
                else:
                    break
            except Exception:
                break

        await send_event({"type": "progress", "step": "search",
                          "message": f"✓ Found {len(jobs)} Easy Apply jobs"})
        return jobs

    async def _ensure_easy_apply_filter(self, page) -> None:
        current_url = page.url
        if "f_AL=true" in current_url:
            return
        sep = "&" if "?" in current_url else "?"
        await page.goto(f"{current_url}{sep}f_AL=true", wait_until="domcontentloaded")
        await page.wait_for_timeout(1800)

    async def _apply_linkedin_filters(self, page, criteria: dict, profile: dict, send_event: SendFn) -> None:
        date_range = int(criteria.get("date_range", 7) or 7)
        target_date_label = "Past 24 hours" if date_range <= 1 else "Past week" if date_range <= 7 else "Past month" if date_range <= 30 else ""
        if target_date_label:
            changed = await self._apply_dropdown_filter(
                page,
                trigger_labels=["Date posted"],
                option_labels=[target_date_label],
            )
            if changed:
                await send_event({
                    "type": "progress",
                    "step": "search",
                    "message": f"LinkedIn filter applied: Date posted = {target_date_label}",
                })

        experience_labels = self._experience_labels_for_profile(profile)
        if experience_labels:
            changed = await self._apply_dropdown_filter(
                page,
                trigger_labels=["Experience level"],
                option_labels=experience_labels,
                multi_select=True,
            )
            if changed:
                await send_event({
                    "type": "progress",
                    "step": "search",
                    "message": f"LinkedIn filter applied: Experience = {', '.join(experience_labels)}",
                })

        work_type = str(criteria.get("work_type") or "any").lower()
        if work_type in {"remote", "hybrid", "onsite"}:
            changed = await self._apply_all_filters_modal(page, work_type)
            if changed:
                await send_event({
                    "type": "progress",
                    "step": "search",
                    "message": f"LinkedIn filter applied: Work arrangement = {work_type}",
                })

    def _experience_labels_for_profile(self, profile: dict) -> list[str]:
        seniority = str(profile.get("seniority", "mid")).lower()
        if seniority == "junior":
            return ["Entry level", "Associate"]
        if seniority == "mid":
            return ["Associate", "Mid-Senior level"]
        if seniority == "senior":
            return ["Mid-Senior level"]
        return ["Director", "Mid-Senior level"]

    async def _apply_dropdown_filter(
        self,
        page,
        trigger_labels: list[str],
        option_labels: list[str],
        multi_select: bool = False,
    ) -> bool:
        trigger = None
        for label in trigger_labels:
            for selector in [
                f'button:has-text("{label}")',
                f'div[role="button"]:has-text("{label}")',
            ]:
                try:
                    candidate = page.locator(selector).first
                    if await candidate.is_visible(timeout=1000):
                        trigger = candidate
                        break
                except Exception:
                    pass
            if trigger:
                break
        if not trigger:
            return False

        try:
            await trigger.click()
            await page.wait_for_timeout(500)
        except Exception:
            return False

        changed = False
        for option_label in option_labels:
            option = page.locator(
                f'label:has-text("{option_label}"), li:has-text("{option_label}"), div:has-text("{option_label}")'
            ).first
            try:
                if await option.is_visible(timeout=1200):
                    checkbox = option.locator('input[type="checkbox"], input[type="radio"]').first
                    needs_click = True
                    try:
                        if await checkbox.count() > 0 and await checkbox.is_checked():
                            needs_click = False
                    except Exception:
                        pass
                    if needs_click:
                        await option.click()
                        changed = True
                        await page.wait_for_timeout(250)
                    if not multi_select:
                        break
            except Exception:
                continue

        for apply_selector in [
            'button:has-text("Show results")',
            'button:has-text("Apply current filters")',
            'button:has-text("Done")',
        ]:
            try:
                button = page.locator(apply_selector).last
                if await button.is_visible(timeout=1000):
                    await button.click()
                    await page.wait_for_timeout(1600)
                    return changed
            except Exception:
                pass

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(600)
        return changed

    async def _apply_all_filters_modal(self, page, work_type: str) -> bool:
        trigger = page.locator('button:has-text("All filters"), div[role="button"]:has-text("All filters")').first
        try:
            if not await trigger.is_visible(timeout=1200):
                return False
            await trigger.click()
            await page.wait_for_timeout(700)
        except Exception:
            return False

        labels = {
            "remote": ["Remote"],
            "hybrid": ["Hybrid"],
            "onsite": ["On-site"],
        }.get(work_type, [])
        changed = False
        for label in ["Easy Apply", *labels]:
            try:
                option = page.locator(f'label:has-text("{label}"), div:has-text("{label}")').first
                if await option.is_visible(timeout=1200):
                    checkbox = option.locator('input[type="checkbox"]').first
                    needs_click = True
                    try:
                        if await checkbox.count() > 0 and await checkbox.is_checked():
                            needs_click = False
                    except Exception:
                        pass
                    if needs_click:
                        await option.click()
                        changed = True
                        await page.wait_for_timeout(250)
            except Exception:
                continue

        for apply_selector in [
            'button:has-text("Show results")',
            'button:has-text("Apply")',
            'button:has-text("Done")',
        ]:
            try:
                button = page.locator(apply_selector).last
                if await button.is_visible(timeout=1200):
                    await button.click()
                    await page.wait_for_timeout(1800)
                    return changed
            except Exception:
                pass
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(600)
        return changed

    async def _extract_job_cards(self, page) -> list[dict]:
        """Extract job cards from the current LinkedIn search results page."""
        try:
            return await page.evaluate("""() => {
                const cards = document.querySelectorAll(
                    '.job-card-container, .jobs-search-results__list-item, [data-job-id]'
                );
                const results = [];
                cards.forEach(card => {
                    try {
                        const titleEl  = card.querySelector('.job-card-list__title, .job-card-container__link, h3');
                        const compEl   = card.querySelector('.job-card-container__company-name, .job-card-container__primary-description, h4');
                        const locEl    = card.querySelector('.job-card-container__metadata-item, .job-card-container__metadata-wrapper li');
                        const linkEl   = card.querySelector('a[href*="/jobs/view/"]');
                        const jobId    = card.getAttribute('data-job-id') ||
                                         (linkEl?.href.match(/\\/jobs\\/view\\/(\\d+)/) || [])[1] || '';
                        if (!titleEl || !jobId) return;
                        results.push({
                            job_id:     jobId,
                            title:      titleEl.innerText.trim(),
                            company:    compEl?.innerText.trim() || '',
                            location:   locEl?.innerText.trim()  || '',
                            url:        linkEl?.href || '',
                            easy_apply: !!card.querySelector('[aria-label*="Easy Apply"], .job-card-container__apply-method'),
                        });
                    } catch(e) {}
                });
                return results;
            }""")
        except Exception:
            return []

    # ── process single job ────────────────────────────────────────────────────

    async def _process_job(self, page, job: dict, profile: dict, criteria: dict, min_score: int,
                            send_event, reply_queue) -> bool:
        """Score the job and apply if above threshold. Returns True if user cancelled."""
        # Click the job card to load the detail pane
        job_id = job["job_id"]
        try:
            card_sel = f'[data-job-id="{job_id}"]'
            card = page.locator(card_sel).first
            if await self._is_visible(card):
                await card.click()
                await page.wait_for_timeout(1500)
            elif job.get("url"):
                url = str(job["url"])
                if url.startswith("/"):
                    url = urllib.parse.urljoin("https://www.linkedin.com", url)
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
        except Exception:
            pass

        # Extract description from detail pane
        description = await self._extract_description(page)
        job["description"] = description
        filter_reason = _job_hunt_service.filter_job(job, criteria)
        if filter_reason:
            await send_event({"type": "skipped", "job_id": job_id, "reason": filter_reason})
            return False

        # Score against profile using AI (weighted: role 30%, skills 40%, exp 20%, domain 10%)
        score, recommendation, missing, match_summary = await self._score_job(job, profile)
        job["score"] = score
        await send_event({"type": "job_scored", "job_id": job_id,
                          "score": score, "recommendation": recommendation,
                          "title": job["title"], "company": job["company"],
                          "missing": missing, "match_summary": match_summary})

        if score < SKIP_THRESHOLD:
            await send_event({"type": "skipped", "job_id": job_id,
                               "reason": f"Score {score} below minimum {SKIP_THRESHOLD}"})
            return False

        if score < min_score:
            await send_event({"type": "skipped", "job_id": job_id,
                               "reason": f"Score {score} below your threshold {min_score}"})
            return False

        has_easy = job.get("easy_apply", False)
        if not has_easy:
            await send_event({"type": "skipped", "job_id": job_id,
                               "reason": "Skipped because LinkedIn Easy Apply is not available"})
            return False

        # ── User review gate — show job card and wait for approval ───────────
        await send_event({
            "type": "confirm", "field": "review_job",
            "label": f"Apply to {job['title']} at {job['company']}?",
            "suggestion": "easy_apply" if has_easy else "external_apply",
            "confidence": score / 100,
            "job": {
                "job_id":              job_id,
                "title":               job["title"],
                "company":             job["company"],
                "location":            job.get("location", ""),
                "salary":              job.get("salary", ""),
                "score":               score,
                "recommendation":      recommendation,
                "url":                 job.get("url", ""),
                "has_quick_apply":     has_easy,
                "description_excerpt": description[:500],
                "missing":             missing,
                "match_summary":       match_summary,
            },
        })
        reply = await reply_queue.get()
        if reply.get("action") == "cancel":
            return True
        if reply.get("action") == "skip":
            job["_skipped"] = True
            await send_event({"type": "skipped", "job_id": job_id, "reason": "Skipped by you"})
            return False

        # Generate application documents
        await send_event({"type": "applying", "job_id": job_id,
                          "message": f"Generating tailored application for {job['title']} at {job['company']}…"})
        documents = await self._generate_documents(job, profile)

        # Apply via Easy Apply
        from app.services.browser_apply import BrowserApplyService, FieldMapper
        mapper = FieldMapper(profile, documents)
        apply_svc = BrowserApplyService()

        cancelled = await apply_svc._fill_linkedin_modal(
            page, profile, documents, mapper, send_event, reply_queue
        )
        if cancelled:
            return True

        job["_applied"] = True
        await send_event({"type": "applied", "job_id": job_id,
                          "message": f"✓ Applied to {job['title']} at {job['company']}"})

        # Log to JATS
        try:
            from app.schemas.jats import LogApplicationRequest
            from app.services.jats_service import log_application
            from app.db.jats_db import JATSSessionLocal
            from datetime import date
            req = LogApplicationRequest(
                company=job["company"],
                role_title=job["title"],
                platform="LinkedIn",
                date_applied=date.today().isoformat(),
                status="applied",
                job_url=job.get("url", ""),
                notes="Auto-applied via LinkedIn Agent",
            )
            db = JATSSessionLocal()
            try:
                log_application(db, req)
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.warning("JATS log failed: %s", exc)

        return False

    async def _extract_description(self, page) -> str:
        """Extract job description text from the LinkedIn detail pane."""
        try:
            desc = await page.evaluate("""() => {
                const el = document.querySelector(
                    '.jobs-description__content, .job-view-layout .jobs-box__html-content, ' +
                    '[class*="description"] .jobs-description-content__text'
                );
                return el ? el.innerText.trim() : '';
            }""")
            # Expand "Show more" if present
            try:
                more = page.locator('button:has-text("Show more")').first
                if await more.is_visible(timeout=1000):
                    await more.click()
                    await page.wait_for_timeout(500)
                    desc = await page.evaluate("""() => {
                        const el = document.querySelector('.jobs-description__content, [class*="description"]');
                        return el ? el.innerText.trim() : '';
                    }""")
            except Exception:
                pass
            return desc or ""
        except Exception:
            return ""

    async def _score_job(self, job: dict, profile: dict) -> tuple[int, str, list[str], str]:
        # Run synchronous (blocking) AI call in a thread pool so it
        # doesn't freeze the event loop or kill the WebSocket keepalive.
        return await asyncio.to_thread(_job_hunt_service.score_job, job, profile)

    async def _generate_documents(self, job: dict, profile: dict) -> dict:
        """Generate tailored resume + cover letter for a job."""
        # Always include the PDF path so the apply service can upload the right file
        pdf_path = profile.get("pdf_path", "")
        base = {
            "resume_pdf_path": pdf_path,
            "job_title":       job["title"],
            "job_company":     job["company"],
            "job_description": job.get("description", ""),
        }
        try:
            from app.services.resume_tailor import ResumeTailor
            from app.services.cover_letter import CoverLetterService
            from app.schemas.candidate import CandidateProfile
            from app.schemas.job import JobPosting

            c = CandidateProfile(**{k: profile.get(k, v) for k, v in {
                "candidate_id": "agent", "name": "", "email": "", "skills": [],
                "domains": [], "seniority": "mid", "years_experience": 0,
                "preferred_roles": [], "locations": [], "strengths": [],
                "skill_gaps": [], "summary": "", "raw_cv_text": "",
            }.items()})
            j = JobPosting(
                job_id=job.get("job_id", "agent"),
                title=job["title"],
                company=job["company"],
                description=job.get("description", ""),
                location=job.get("location", ""),
            )

            tailor = ResumeTailor()
            cl_svc = CoverLetterService()
            return {
                **base,
                "resume_text":  tailor.generate(c, j, surgical=True),
                "cover_letter": cl_svc.generate(c, j),
            }
        except Exception as exc:
            logger.warning("Document generation failed: %s", exc)
            return {
                **base,
                "resume_text":  profile.get("raw_cv_text", ""),
                "cover_letter": "",
            }

    # ── utils ─────────────────────────────────────────────────────────────────

    async def _screenshot(self, page, send_event: SendFn) -> None:
        try:
            data = await page.screenshot(type="jpeg", quality=65, full_page=False)
            await send_event({"type": "screenshot", "data": base64.b64encode(data).decode()})
        except Exception:
            pass

    @staticmethod
    async def _is_visible(locator) -> bool:
        try:
            return await locator.is_visible(timeout=1500)
        except Exception:
            return False
