"""Seek.com.au automated job search + Quick Apply agent.

Human-in-the-loop design
------------------------
* The browser is always visible — you watch every action.
* Manual login — the agent opens the login page and waits for YOU to sign in.
* Job review — for every scored job above your threshold the agent pauses and
  sends a "review_job" event so you can click Apply, Skip, or Stop All.
* Cover-letter review — you see the AI draft and can edit it before it's typed.
* Final-submit confirmation — the agent always pauses before hitting Submit.

Events emitted (→ frontend via WebSocket)
------------------------------------------
{"type": "progress",    "step": str, "message": str}
{"type": "job_found",   "job": {job_id, title, company, location, salary, url, quick_apply}}
{"type": "job_scored",  "job_id": str, "score": int, "recommendation": str,
                         "title": str, "company": str}
{"type": "applying",    "job_id": str, "message": str}
{"type": "confirm",     "field": str, "label": str, "suggestion": str,
                         "confidence": float, "job"?: dict}
{"type": "applied",     "job_id": str, "message": str}
{"type": "skipped",     "job_id": str, "reason": str}
{"type": "screenshot",  "data": str}   # base64 JPEG
{"type": "success",     "message": str}
{"type": "error",       "message": str}

Messages consumed from client (← frontend via WebSocket)
---------------------------------------------------------
{"action": "confirm"}                  – proceed / approve
{"action": "edit",    "value": "..."}  – confirm with edited text
{"action": "skip"}                     – skip this job, continue to next
{"action": "cancel"}                   – stop the agent immediately
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

INTER_APPLY_DELAY = 30   # seconds between applications (looks human)
SKIP_THRESHOLD    = 35   # never show jobs below this score

# CDP debug port — dedicated to Seek so it doesn't clash with Indeed
_CDP_PORT = 9222

_job_hunt_service = JobHuntIntelligenceService()


class SeekAgent:
    """Playwright-driven agent for Seek.com.au Quick Apply jobs."""

    TIMEOUT_MS = 20_000

    async def _human_pause(self, scope, minimum_ms: int = 120, maximum_ms: int = 420) -> None:
        await scope.wait_for_timeout(random.randint(minimum_ms, maximum_ms))

    async def _clear_and_type_like_human(self, scope, locator, value: str) -> None:
        await locator.click()
        await self._human_pause(scope, 120, 240)
        await locator.press("Control+a")
        await self._human_pause(scope, 60, 140)
        await locator.press("Delete")
        await self._human_pause(scope, 100, 220)
        for index, char in enumerate(value):
            await locator.type(char, delay=random.randint(55, 140))
            if char in {" ", ",", "-", "/"}:
                await self._human_pause(scope, 80, 180)
            elif index and index % random.randint(6, 10) == 0:
                await self._human_pause(scope, 90, 240)
        await self._human_pause(scope, 150, 320)

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
            "min_score": int(criteria.get("min_score", 60) or 60),
            "date_range": int(criteria.get("date_range", 7) or 7),
            "salary_min": criteria.get("salary_min"),
            "industries": list(criteria.get("industries") or []),
            "work_type": criteria.get("work_type", "any"),
            "target_roles": list(profile.get("preferred_roles") or profile.get("target_roles") or [])[:6],
        }
        await send_event({
            "type": "confirm",
            "field": "search_plan",
            "label": "Review the Seek search plan. Edit the JSON if needed, then click Confirm to start scraping.",
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

    async def run(
        self,
        session_id: str,  # noqa: ARG002
        profile: dict,
        criteria: dict,
        send_event: SendFn,
        reply_queue: asyncio.Queue,
    ) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            await send_event({"type": "error", "message": "Playwright not installed on the server."})
            return

        try:
            async with async_playwright() as pw:
                # Launch real Chrome via CDP (no automation banner, no bot detection)
                ctx, page, cleanup = await launch_for_agent(pw, "seek", _CDP_PORT)

                try:
                    # ── 1. Login (skipped if session cookie exists) ───────────
                    if not await self._wait_for_login(page, send_event, reply_queue):
                        return

                    runtime_criteria = dict(criteria)
                    if runtime_criteria.get("queries"):
                        runtime_queries = list(runtime_criteria["queries"])
                        runtime_location = str(runtime_criteria.get("location", "All Australia")).strip() or "All Australia"
                    else:
                        plan = build_platform_queries(profile, "seek", max_queries=6)
                        runtime_queries = plan["queries"]
                        runtime_location = str(runtime_criteria.get("location") or plan["location"] or "").strip()
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
                    min_score = int(runtime_criteria.get("min_score", 60) or 60)
                    date_range = int(runtime_criteria.get("date_range", 7) or 7)

                    # ── 2. Search ─────────────────────────────────────────────
                    jobs: list[dict] = []
                    for idx, query in enumerate(runtime_queries, start=1):
                        remaining = max_jobs - len(jobs)
                        if remaining <= 0:
                            break
                        await send_event({
                            "type": "progress",
                            "step": "search",
                            "message": f"Running query {idx}/{len(runtime_queries)} on Seek: {query}",
                        })
                        jobs.extend(
                            await self._search_jobs(
                                page, query, runtime_location, date_range, remaining, send_event
                            )
                        )
                    if not jobs:
                        await send_event({
                            "type": "error",
                            "message": "No jobs found on Seek for your search criteria.",
                        })
                        return

                    applied = 0
                    # ── 3. Score → review → apply loop ────────────────────────
                    for job in jobs:
                        try:
                            stopped = await self._process_job(
                                page, job, profile, runtime_criteria, min_score, send_event, reply_queue
                            )
                            if stopped:
                                break
                            if job.get("_applied"):
                                applied += 1
                                remaining = [j for j in jobs if not j.get("_applied") and not j.get("_skipped")]
                                if remaining:
                                    await send_event({
                                        "type": "progress", "step": "delay",
                                        "message": f"Waiting {INTER_APPLY_DELAY}s before next application…",
                                    })
                                    await asyncio.sleep(INTER_APPLY_DELAY)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            logger.exception("Error processing job %s", job.get("title"))
                            await send_event({
                                "type": "progress", "step": "error",
                                "message": f"Problem with '{job.get('title')}': {exc}",
                            })

                    await send_event({
                        "type": "success",
                        "message": f"Done. Applied to {applied} job(s) out of {len(jobs)} scanned.",
                    })

                finally:
                    await cleanup()

        except asyncio.CancelledError:
            await send_event({"type": "error", "message": "Agent cancelled."})
        except Exception as exc:
            logger.exception("Seek agent unexpected error")
            await send_event({"type": "error", "message": f"Unexpected error: {exc}"})

    # ── login ─────────────────────────────────────────────────────────────────

    async def _wait_for_login(self, page, send_event: SendFn, reply_queue) -> bool:
        await send_event({
            "type": "progress", "step": "login",
            "message": "Opening Seek.com.au…",
        })
        await page.goto("https://www.seek.com.au", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await self._screenshot(page, send_event)

        # Already logged in from a saved session?
        if await self._is_logged_in_seek(page):
            await send_event({
                "type": "progress", "step": "login",
                "message": "✓ Already logged in to Seek (saved session)",
            })
            return True

        # Navigate to login page and wait for user
        await send_event({
            "type": "progress", "step": "login",
            "message": "Not logged in — opening Seek login page…",
        })
        await page.goto("https://www.seek.com.au/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await self._screenshot(page, send_event)

        await send_event({
            "type": "confirm", "field": "login",
            "label": (
                "Please log in to Seek in the browser window "
                "(including any 2FA), then click Confirm here."
            ),
            "suggestion": "", "confidence": 0.0,
        })
        reply = await reply_queue.get()
        if reply.get("action") == "cancel":
            return False

        await self._screenshot(page, send_event)
        await send_event({"type": "progress", "step": "login", "message": "✓ Logged in to Seek"})
        return True

    async def _is_logged_in_seek(self, page) -> bool:
        """Return True if the Seek session cookie / profile menu is present."""
        try:
            # Seek shows a user avatar / "profile" menu when logged in
            el = page.locator(
                '[data-automation="profile-menu-trigger"], '
                '[aria-label="My account"], '
                'a[href*="/profile/"], '
                'button[aria-label*="account" i]'
            ).first
            return await el.is_visible(timeout=4000)
        except Exception:
            return False

    # ── search ────────────────────────────────────────────────────────────────

    async def _type_autocomplete(
        self,
        page,
        selectors: list[str],
        value: str,
        suggestion_sels: list[str] | None = None,
    ) -> bool:
        """Type into a field using real keystrokes (triggers autocomplete JS),
        then optionally select the first suggestion from a dropdown.

        Using `.type()` instead of `.fill()` fires keydown/keypress/input/keyup
        events per character, which React/Vue autocomplete handlers respond to.
        `.fill()` sets the DOM value directly and those events never fire.
        """
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if not await el.is_visible(timeout=2000):
                    continue
                await el.click()
                await self._human_pause(page, 120, 220)
                await self._clear_and_type_like_human(page, el, value)
                await page.wait_for_timeout(700)

                if suggestion_sels:
                    if await self._click_best_suggestion(page, suggestion_sels, value):
                        return True
                    # No suggestion found — Tab out to confirm the typed value
                    await el.press("Tab")
                else:
                    # Keywords are free-text — dismiss any dropdown that appeared
                    await page.keyboard.press("Escape")

                await page.wait_for_timeout(200)
                return True
            except Exception:
                continue
        return False

    async def _search_jobs(
        self, page, keywords: str, location: str,
        date_range: int, max_jobs: int, send_event: SendFn,
    ) -> list[dict]:
        await send_event({
            "type": "progress", "step": "search",
            "message": f"Searching Seek: {keywords!r} in {location!r} (last {date_range} days)…",
        })

        # ── Build Seek search URL directly (reliable, no fragile form-filling) ─
        all_aus = location.strip().lower() in ("all australia", "australia", "")
        params: dict[str, str] = {
            "keywords": keywords,
            "sortmode": "ListedDate",
        }
        if not all_aus:
            params["where"] = location
        if date_range < 30:
            params["daterange"] = str(date_range)

        search_url = "https://www.seek.com.au/jobs?" + urllib.parse.urlencode(params)
        await page.goto(search_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        await self._screenshot(page, send_event)

        jobs: list[dict] = []
        page_num = 0

        while len(jobs) < max_jobs:
            page_num += 1
            await send_event({
                "type": "progress", "step": "search",
                "message": f"Scanning page {page_num}…",
            })

            new_jobs = await self._extract_job_cards(page)
            await send_event({
                "type": "progress", "step": "search",
                "message": f"Page {page_num}: extracted {len(new_jobs)} job(s)",
            })
            if not new_jobs:
                await self._screenshot(page, send_event)
                break

            for job in new_jobs:
                if len(jobs) >= max_jobs:
                    break
                if not any(j["job_id"] == job["job_id"] for j in jobs):
                    jobs.append(job)
                    await send_event({"type": "job_found", "job": job})

            # Next page
            try:
                nxt = page.locator(
                    'a[data-automation="page-next"], '
                    'a[aria-label="Next page"], '
                    'a[aria-label="Go to next page"]'
                ).first
                if await self._is_visible(nxt):
                    await nxt.click()
                    await page.wait_for_timeout(2500)
                else:
                    break
            except Exception:
                break

        await send_event({
            "type": "progress", "step": "search",
            "message": f"✓ Found {len(jobs)} jobs — now scoring each one…",
        })
        return jobs

    async def _extract_job_cards(self, page) -> list[dict]:
        """Three-strategy extraction — always returns what it can find."""
        try:
            return await page.evaluate("""() => {
                const getT = (el, sels) => {
                    for (const s of sels) {
                        const f = el.querySelector(s);
                        if (f) return (f.innerText || f.textContent || '').trim();
                    }
                    return '';
                };
                const getJobId = href => {
                    const m = (href || '').match(/\\/job\\/(\\d+)/);
                    return m ? m[1] : '';
                };

                const results = [];
                const seen    = new Set();

                // ── Strategy 1: article / li cards with data attributes ──────
                const s1 = document.querySelectorAll(
                    'article[data-testid], article[data-card-type], ' +
                    '[data-automation="normalJob"], [data-automation="job-list-item"], ' +
                    'li[data-job-id]'
                );
                s1.forEach(card => {
                    const link = card.querySelector('a[href*="/job/"]');
                    if (!link) return;
                    const jobId = getJobId(link.href);
                    if (!jobId || seen.has(jobId)) return;
                    seen.add(jobId);
                    const title = getT(card, [
                        '[data-automation="jobTitle"]', 'h3 a', 'h2 a', 'h1 a',
                        'h3', 'h2', '.job-title', '[class*="title"]'
                    ]);
                    if (!title) return;
                    results.push({
                        job_id:      jobId,
                        title,
                        company:     getT(card, ['[data-automation="jobCompany"]', '[class*="company"]']),
                        location:    getT(card, ['[data-automation="jobLocation"]', '[class*="location"]']),
                        salary:      getT(card, ['[data-automation="jobSalary"]',   '[class*="salary"]']),
                        url:         'https://www.seek.com.au/job/' + jobId,
                        quick_apply: !!card.querySelector('[data-automation="quickApply"]'),
                    });
                });
                if (results.length) return results;

                // ── Strategy 2: any element with data-job-id ─────────────────
                document.querySelectorAll('[data-job-id]').forEach(card => {
                    const jobId = card.dataset.jobId || getJobId(card.querySelector('a')?.href || '');
                    if (!jobId || seen.has(jobId)) return;
                    seen.add(jobId);
                    const link  = card.querySelector('a[href*="/job/"]');
                    const title = getT(card, ['h3', 'h2', '[class*="title"]', 'a']);
                    if (!title) return;
                    results.push({
                        job_id: jobId, title,
                        company: getT(card, ['[class*="company"]']),
                        location: '', salary: '',
                        url: link?.href || 'https://www.seek.com.au/job/' + jobId,
                        quick_apply: false,
                    });
                });
                if (results.length) return results;

                // ── Strategy 3: grab every distinct /job/ link on the page ───
                document.querySelectorAll('a[href*="/job/"]').forEach(link => {
                    const jobId = getJobId(link.href);
                    if (!jobId || seen.has(jobId)) return;
                    const title = (link.innerText || link.textContent || '').trim();
                    // Skip navigation / footer links (very short text)
                    if (!title || title.length < 4) return;
                    seen.add(jobId);
                    results.push({
                        job_id: jobId, title,
                        company: '', location: '', salary: '',
                        url: 'https://www.seek.com.au/job/' + jobId,
                        quick_apply: false,
                    });
                });
                return results;
            }""")
        except Exception as exc:
            logger.debug("Seek extraction error: %s", exc)
            return []

    # ── process one job ───────────────────────────────────────────────────────

    async def _process_job(
        self, page, job: dict, profile: dict, criteria: dict, min_score: int,
        send_event: SendFn, reply_queue: asyncio.Queue,
    ) -> bool:
        """Score → show to user → apply. Returns True if agent should stop."""
        job_id = job["job_id"]

        # Open job detail page
        try:
            await page.goto(job["url"], wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        description = await self._extract_description(page)
        job["description"] = description
        await self._screenshot(page, send_event)

        filter_reason = _job_hunt_service.filter_job(job, criteria)
        if filter_reason:
            job["_skipped"] = True
            await send_event({"type": "skipped", "job_id": job_id, "reason": filter_reason})
            return False

        # ── Score first — don't waste time checking Quick Apply on bad-fit jobs ─
        score, recommendation, missing, match_summary = await self._score_job(job, profile)
        job["score"] = score
        await send_event({
            "type": "job_scored", "job_id": job_id,
            "score": score, "recommendation": recommendation,
            "title": job["title"], "company": job["company"],
            "missing": missing, "match_summary": match_summary,
        })

        if score < SKIP_THRESHOLD:
            job["_skipped"] = True
            await send_event({"type": "skipped", "job_id": job_id,
                              "reason": f"Score {score} — too low to consider"})
            return False

        if score < min_score:
            job["_skipped"] = True
            await send_event({"type": "skipped", "job_id": job_id,
                              "reason": f"Score {score} below your minimum of {min_score}"})
            return False

        # ── Check Quick Apply availability (now that we know it's worth pursuing) ─
        has_quick = await self._has_quick_apply(page)

        # ── Show to user for review ───────────────────────────────────────────
        await send_event({
            "type": "confirm", "field": "review_job",
            "label": f"Apply to {job['title']} at {job['company']}?",
            "suggestion": "quick_apply" if has_quick else "external_apply",
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
                "has_quick_apply":     has_quick,
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

        if not has_quick:
            job["_skipped"] = True
            await send_event({
                "type": "skipped",
                "job_id": job_id,
                "reason": "Skipped because Seek Quick Apply is not available",
            })
            return False

        # ── Generate tailored documents ───────────────────────────────────────
        await send_event({
            "type": "applying", "job_id": job_id,
            "message": f"Generating tailored cover letter for {job['title']}…",
        })
        documents = await self._generate_documents(job, profile)

        # ── Apply ─────────────────────────────────────────────────────────────
        cancelled = await self._quick_apply(page, job, profile, documents, send_event, reply_queue)

        if cancelled:
            return True

        job["_applied"] = True
        await send_event({
            "type": "applied", "job_id": job_id,
            "message": f"✓ Applied to {job['title']} at {job['company']}",
        })
        await self._log_to_jats(job)
        return False

    # ── Quick Apply form flow ─────────────────────────────────────────────────

    async def _has_quick_apply(self, page) -> bool:
        """Return True if Seek shows a Quick Apply button (in-page form, not external link)."""
        # Try each selector individually so a long timeout on one doesn't block all
        for sel in [
            'button:has-text("Quick apply")',
            'a:has-text("Quick apply")',
            '[data-automation="job-detail-apply"]',
            '[data-automation="detailApply"]',
            'button[aria-label*="quick apply" i]',
            '[class*="QuickApply"]',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    return True
            except Exception:
                pass
        return False

    async def _select_resume(self, page) -> None:
        """Select the first uploaded resume in Seek's Quick Apply panel."""
        for sel in [
            # Radio buttons for uploaded resumes
            '[data-automation*="resume" i] input[type="radio"]',
            'input[type="radio"][name*="resume" i]',
            'input[type="radio"][id*="resume" i]',
            '[class*="Resume" i] input[type="radio"]',
            # Clickable resume cards
            '[data-automation*="resume" i]:first-of-type',
            '[class*="ResumeOption" i]:first-of-type',
            '[class*="resume-card" i]:first-of-type',
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    await el.click()
                    await page.wait_for_timeout(400)
                    logger.debug("Selected resume via: %s", sel)
                    return
            except Exception:
                pass

    async def _quick_apply(
        self, page, job: dict, profile: dict, documents: dict,
        send_event: SendFn, reply_queue: asyncio.Queue,
    ) -> bool:
        """Drive the Quick Apply multi-step form. Returns True if cancelled."""
        from app.services.browser_apply import FieldMapper

        mapper = FieldMapper(
            profile,
            {
                **documents,
                "job_title": job.get("title", ""),
                "job_company": job.get("company", ""),
                "job_description": job.get("description", ""),
            },
        )

        # Click the Quick Apply button
        clicked = False
        for sel in [
            'button:has-text("Quick apply")',
            'a:has-text("Quick apply")',
            '[data-automation="job-detail-apply"]',
            '[data-automation="detailApply"]',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            await send_event({
                "type": "progress", "step": "error",
                "message": "Could not find Quick Apply button — please click it manually in the browser.",
            })
            # Give user a chance to click it themselves
            await send_event({
                "type": "confirm", "field": "manual_step",
                "label": "Please click the Quick Apply button in the browser, then click Confirm.",
                "suggestion": "", "confidence": 0.0,
            })
            reply = await reply_queue.get()
            if reply.get("action") == "cancel":
                return True

        # Wait for the Quick Apply panel / modal to open
        try:
            await page.wait_for_selector(
                '[data-automation="apply-panel"], [class*="QuickApply"], '
                'form[data-automation*="apply"], [role="dialog"]',
                timeout=6000,
            )
        except Exception:
            pass
        await page.wait_for_timeout(1000)
        await self._screenshot(page, send_event)

        # Step through the multi-page form
        for _ in range(15):
            await self._screenshot(page, send_event)

            # Success check
            if await self._is_submitted(page):
                return False

            # Fill contact/personal fields (only empty ones — don't overwrite pre-filled)
            await self._fill_standard_fields(page, profile)

            # Select resume from Seek's resume picker
            await self._select_resume(page)

            # Fill visible application questions from the profile + job context
            cancelled = await self._fill_visible_fields(page, mapper, send_event, reply_queue)
            if cancelled:
                return True

            # Cover letter
            result = await self._handle_cover_letter(
                page, documents.get("cover_letter", ""), send_event, reply_queue
            )
            if result == "cancelled":
                return True

            # Screening questions — pause for user only if fields still need help
            has_questions = await self._has_unanswered_questions(page)
            if has_questions:
                await send_event({
                    "type": "confirm", "field": "screening_questions",
                    "label": (
                        "Some screening questions still need review. "
                        "Please check the browser, adjust anything unclear, then click Confirm."
                    ),
                    "suggestion": "", "confidence": 0.5,
                })
                reply = await reply_queue.get()
                if reply.get("action") == "cancel":
                    return True

            # Find Next / Submit button
            btn_text, action_btn = await self._find_action_button(page)
            if not action_btn:
                await send_event({
                    "type": "confirm", "field": "manual_step",
                    "label": "Please complete this step in the browser, then click Confirm.",
                    "suggestion": "", "confidence": 0.0,
                })
                reply = await reply_queue.get()
                if reply.get("action") == "cancel":
                    return True
                continue

            is_final = any(w in btn_text.lower() for w in ("submit", "send application", "apply now"))
            if is_final:
                await self._screenshot(page, send_event)
                await send_event({
                    "type": "confirm", "field": "final_submit",
                    "label": (
                        f"Ready to submit your application to {job['company']}. "
                        "Review everything in the browser window, then click Submit Application."
                    ),
                    "suggestion": "", "confidence": 1.0,
                })
                reply = await reply_queue.get()
                if reply.get("action") == "cancel":
                    return True

            await action_btn.click()
            await page.wait_for_timeout(2500)

        return False

    async def _is_submitted(self, page) -> bool:
        try:
            for text in ("Application submitted", "You've applied", "applied successfully"):
                el = page.locator(f'text="{text}"').first
                if await el.is_visible(timeout=800):
                    return True
        except Exception:
            pass
        return False

    async def _fill_standard_fields(self, page, profile: dict) -> None:
        name_parts = (profile.get("name") or "").split(" ", 1)
        first = name_parts[0] if name_parts else ""
        last  = name_parts[1] if len(name_parts) > 1 else ""

        fields = {
            'input[name*="first" i], input[placeholder*="first" i]': first,
            'input[name*="last"  i], input[placeholder*="last"  i]': last,
            'input[type="email"],    input[name*="email" i]':        profile.get("email", ""),
            'input[name*="phone" i], input[placeholder*="phone" i]': profile.get("phone", ""),
        }
        for selector, value in fields.items():
            if not value:
                continue
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=600):
                        current = await el.input_value()
                        if not current.strip():
                            await self._clear_and_type_like_human(page, el, value)
            except Exception:
                pass

    async def _handle_cover_letter(
        self, page, cover_letter: str, send_event: SendFn, reply_queue: asyncio.Queue
    ) -> str:
        try:
            ta = page.locator(
                'textarea[name*="cover" i], '
                'textarea[placeholder*="cover" i], '
                'textarea[aria-label*="cover" i]'
            ).first
            if await ta.is_visible(timeout=1000):
                current = await ta.input_value()
                if not current.strip():
                    await send_event({
                        "type": "confirm", "field": "cover_letter",
                        "label": "Cover letter — review and edit, then click Confirm to fill it in:",
                        "suggestion": cover_letter[:1500],
                        "confidence": 0.9,
                    })
                    reply = await reply_queue.get()
                    if reply.get("action") == "cancel":
                        return "cancelled"
                    text = reply.get("value", cover_letter)
                    await self._clear_and_type_like_human(page, ta, text)
        except Exception:
            pass
        return "ok"

    async def _fill_visible_fields(self, page, mapper, send_event: SendFn, reply_queue: asyncio.Queue) -> bool:
        try:
            fields = await page.evaluate("""() => {
                const results = [];
                const nodes = document.querySelectorAll('input:not([type="hidden"]):not([type="file"]):not([type="submit"]):not([type="radio"]):not([type="checkbox"]), textarea, select');
                nodes.forEach(el => {
                    if (!el.offsetParent) return;
                    const tag = el.tagName.toLowerCase();
                    const type = tag === 'select' ? 'select' : (el.getAttribute('type') || 'text');
                    const id = el.getAttribute('id') || '';
                    let label = '';
                    if (id) {
                        const lbl = document.querySelector(`label[for="${id}"]`);
                        if (lbl) label = (lbl.innerText || lbl.textContent || '').trim();
                    }
                    if (!label) {
                        const wrapper = el.closest('label, fieldset, [data-testid*="question"], [class*="question"]');
                        if (wrapper) label = (wrapper.innerText || wrapper.textContent || '').trim().slice(0, 160);
                    }
                    if (!label) label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || '';
                    results.push({
                        selector: id ? `#${id}` : '',
                        name: el.getAttribute('name') || '',
                        label,
                        tag,
                        type,
                        value: el.value || '',
                        required: !!el.required,
                        options: tag === 'select' ? Array.from(el.options).map(opt => (opt.label || opt.textContent || '').trim()).filter(Boolean) : [],
                    });
                });
                return results;
            }""")
            for field in fields:
                label = str(field.get("label") or "").strip()
                if not label:
                    continue
                existing = str(field.get("value") or "").strip()
                if existing:
                    continue
                answer, confidence = mapper.resolve(label, str(field.get("type") or "text"))
                if not answer:
                    continue
                if confidence >= 0.85:
                    await self._fill_dynamic_field(page, field, answer)
                    await send_event({
                        "type": "progress",
                        "step": "fill",
                        "message": f"Filled {label[:60]}{'…' if len(label) > 60 else ''}",
                    })
                else:
                    await send_event({
                        "type": "confirm",
                        "field": field.get("name") or label,
                        "label": f"Please review: {label}",
                        "suggestion": answer,
                        "confidence": confidence,
                    })
                    reply = await reply_queue.get()
                    if reply.get("action") == "cancel":
                        return True
                    final_answer = reply.get("value", answer) if reply.get("action") == "edit" else answer
                    if final_answer:
                        await self._fill_dynamic_field(page, field, final_answer)
            return False
        except Exception:
            return False

    async def _has_unanswered_questions(self, page) -> bool:
        try:
            count = await page.evaluate("""() => {
                const nodes = document.querySelectorAll('input:not([type="hidden"]):not([type="file"]):not([type="submit"]), textarea, select');
                let missing = 0;
                nodes.forEach(el => {
                    if (!el.offsetParent) return;
                    const type = (el.getAttribute('type') || '').toLowerCase();
                    if (type === 'radio' || type === 'checkbox') {
                        const name = el.getAttribute('name');
                        if (!name) return;
                        const group = document.querySelectorAll(`input[name="${name}"]`);
                        const checked = Array.from(group).some(node => node.checked);
                        if (!checked) missing += 1;
                        return;
                    }
                    if (!(el.value || '').trim()) missing += 1;
                });
                return missing;
            }""")
            return int(count) > 0
        except Exception:
            return False

    async def _fill_dynamic_field(self, page, field: dict, answer: str) -> None:
        selector = field.get("selector") or f'[name="{field["name"]}"]'
        tag = str(field.get("tag") or "input")
        try:
            locator = page.locator(selector).first
            if tag == "select":
                options = [str(option).strip() for option in field.get("options") or [] if str(option).strip()]
                best = self._best_option_match(answer, options)
                if best:
                    await locator.select_option(label=best)
                    await page.wait_for_timeout(250)
                return
            await self._clear_and_type_like_human(page, locator, answer)
        except Exception:
            logger.debug("Could not fill dynamic field %s", selector)

    @staticmethod
    def _best_option_match(answer: str, options: list[str]) -> str:
        desired = " ".join(answer.lower().split())
        best = ""
        best_score = -1
        for option in options:
            normalized = " ".join(option.lower().split())
            score = 0
            if normalized == desired:
                score = 100
            elif desired in normalized:
                score = 90
            elif normalized in desired:
                score = 80
            else:
                desired_tokens = set(desired.split())
                option_tokens = set(normalized.split())
                score = len(desired_tokens & option_tokens) * 10
            if score > best_score:
                best = option
                best_score = score
        return best if best_score >= 10 else ""

    async def _find_action_button(self, page):
        for selector in [
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button[type="submit"]',
        ]:
            try:
                btn = page.locator(selector).last
                if await btn.is_visible(timeout=800):
                    text = await btn.inner_text()
                    return text.strip(), btn
            except Exception:
                pass
        return "", None

    # ── description extraction ────────────────────────────────────────────────

    async def _extract_description(self, page) -> str:
        try:
            return await page.evaluate("""() => {
                const el = document.querySelector(
                    '[data-automation="jobAdDetails"], '
                    '[class*="jobDescription"], '
                    '[class*="job-detail"]'
                );
                return el ? el.innerText.trim() : '';
            }""") or ""
        except Exception:
            return ""

    # ── AI scoring ────────────────────────────────────────────────────────────

    async def _score_job(self, job: dict, profile: dict) -> tuple[int, str, list[str], str]:
        return await asyncio.to_thread(_job_hunt_service.score_job, job, profile)

    # ── document generation ───────────────────────────────────────────────────

    async def _generate_documents(self, job: dict, profile: dict) -> dict:
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

            defaults = {
                "candidate_id": "agent", "name": "", "email": "", "skills": [],
                "domains": [], "seniority": "mid", "years_experience": 0,
                "preferred_roles": [], "locations": [], "strengths": [],
                "skill_gaps": [], "summary": "", "raw_cv_text": "",
            }
            c = CandidateProfile(**{k: profile.get(k, v) for k, v in defaults.items()})
            j = JobPosting(
                job_id=job.get("job_id", "seek"),
                title=job["title"], company=job["company"],
                description=job.get("description", ""), location=job.get("location", ""),
            )
            return {
                **base,
                "resume_text":  ResumeTailor().generate(c, j, surgical=True),
                "cover_letter": CoverLetterService().generate(c, j),
            }
        except Exception as exc:
            logger.warning("Document generation failed: %s", exc)
            return {
                **base,
                "resume_text":  profile.get("raw_cv_text", ""),
                "cover_letter": "",
            }

    # ── JATS logging ──────────────────────────────────────────────────────────

    async def _log_to_jats(self, job: dict) -> None:
        try:
            from app.schemas.jats import LogApplicationRequest
            from app.services.jats_service import log_application
            from app.db.jats_db import JATSSessionLocal
            from datetime import date
            req = LogApplicationRequest(
                company=job["company"],
                role_title=job["title"],
                platform="Seek",
                date_applied=date.today().isoformat(),
                status="applied",
                job_url=job.get("url", ""),
                fit_score=job.get("score"),
                notes=f"Auto-applied via Seek Agent. Score: {job.get('score', '?')}",
            )
            db = JATSSessionLocal()
            try:
                log_application(db, req)
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.warning("JATS log failed: %s", exc)

    # ── utils ─────────────────────────────────────────────────────────────────

    async def _screenshot(self, page, send_event: SendFn) -> None:
        try:
            data = await page.screenshot(type="jpeg", quality=65, full_page=False)
            await send_event({
                "type": "screenshot",
                "data": base64.b64encode(data).decode(),
            })
        except Exception:
            pass

    @staticmethod
    async def _is_visible(locator) -> bool:
        try:
            return await locator.is_visible(timeout=1500)
        except Exception:
            return False
