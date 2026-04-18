"""Indeed.com.au automated job search + Easy Apply agent.

Human-in-the-loop design — identical philosophy to seek_agent.py:
* Visible browser, manual login, you approve every application.

Indeed-specific notes
---------------------
* Search filter `&iafc=1` restricts to Easy Apply jobs only (no external redirects).
* Indeed's Easy Apply runs inside an <iframe> widget on the same page.
  Playwright can address it with `page.frame_locator(...)`.
* The iframe has multiple pages; we advance through them detecting Next/Submit.
* Indeed asks for a resume — we rely on your stored Indeed profile resume.
  If it prompts an upload, we pause and ask you to handle it.

Events / messages: same protocol as seek_agent.py (see docstring there).
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

INTER_APPLY_DELAY = 30
SKIP_THRESHOLD    = 35

# CDP debug port — dedicated to Indeed (different from Seek's 9222)
_CDP_PORT = 9223

_job_hunt_service = JobHuntIntelligenceService()


class IndeedAgent:
    """Playwright-driven agent for Indeed.com.au Easy Apply jobs."""

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
            "label": "Review the Indeed search plan. Edit the JSON if needed, then click Confirm to start scraping.",
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
                # Launch real Chrome via CDP — no automation banner, no bot detection
                ctx, page, cleanup = await launch_for_agent(pw, "indeed", _CDP_PORT)

                try:
                    # ── 1. Login (skipped if session cookie exists) ───────────
                    if not await self._wait_for_login(page, send_event, reply_queue):
                        return

                    runtime_criteria = dict(criteria)
                    if runtime_criteria.get("queries"):
                        runtime_queries = list(runtime_criteria["queries"])
                        runtime_location = str(runtime_criteria.get("location", "Australia")).strip() or "Australia"
                    else:
                        plan = build_platform_queries(profile, "indeed", max_queries=6)
                        runtime_queries = plan["queries"]
                        runtime_location = str(runtime_criteria.get("location") or plan["location"] or "Australia").strip()
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
                            "message": f"Running query {idx}/{len(runtime_queries)} on Indeed: {query}",
                        })
                        jobs.extend(
                            await self._search_jobs(
                                page, query, runtime_location, date_range, remaining, send_event
                            )
                        )
                    if not jobs:
                        await send_event({
                            "type": "error",
                            "message": "No Easy Apply jobs found on Indeed for your search.",
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
                            logger.exception("Error processing Indeed job %s", job.get("title"))
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
            logger.exception("Indeed agent unexpected error")
            await send_event({"type": "error", "message": f"Unexpected error: {exc}"})

    # ── login ─────────────────────────────────────────────────────────────────

    async def _wait_for_login(self, page, send_event: SendFn, reply_queue) -> bool:
        await send_event({
            "type": "progress", "step": "login",
            "message": "Opening Indeed.com.au…",
        })
        await page.goto("https://au.indeed.com", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        await self._screenshot(page, send_event)

        # Already logged in from a saved session?
        if await self._is_logged_in_indeed(page):
            await send_event({
                "type": "progress", "step": "login",
                "message": "✓ Already logged in to Indeed (saved session)",
            })
            return True

        # Navigate to sign-in and wait for user
        await send_event({
            "type": "progress", "step": "login",
            "message": "Not logged in — opening Indeed sign-in page…",
        })
        try:
            sign_in = page.locator(
                'a[href*="/account/login"], a[href*="login"], a:has-text("Sign in")'
            ).first
            if await sign_in.is_visible(timeout=3000):
                await sign_in.click()
                await page.wait_for_timeout(2000)
            else:
                await page.goto("https://au.indeed.com/account/login", wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
        except Exception:
            await page.goto("https://au.indeed.com/account/login", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

        await self._screenshot(page, send_event)

        await send_event({
            "type": "confirm", "field": "login",
            "label": (
                "Please log in to Indeed in the browser window "
                "(including any 2FA), then click Confirm here."
            ),
            "suggestion": "", "confidence": 0.0,
        })
        reply = await reply_queue.get()
        if reply.get("action") == "cancel":
            return False

        await self._screenshot(page, send_event)
        await send_event({"type": "progress", "step": "login", "message": "✓ Logged in to Indeed"})
        return True

    async def _is_logged_in_indeed(self, page) -> bool:
        """Return True if Indeed shows a logged-in user indicator."""
        try:
            el = page.locator(
                'a[href*="/my-jobs"], '
                'a[href*="/account/view"], '
                'button[aria-label*="account" i], '
                '[data-testid="UserDropdown"], '
                'a:has-text("My Jobs")'
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
        then optionally select the first suggestion from the dropdown.

        `.type()` fires keydown/keypress/input/keyup per character so that
        React/Vue autocomplete handlers respond.  `.fill()` bypasses them.
        """
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if not await el.is_visible(timeout=2000):
                    continue
                await self._clear_and_type_like_human(page, el, value)
                await page.wait_for_timeout(700)

                if suggestion_sels:
                    if await self._click_best_suggestion(page, suggestion_sels, value):
                        return True
                    await el.press("Tab")
                else:
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
            "message": f"Searching Indeed (Easy Apply only): {keywords!r} in {location!r} (last {date_range} days)…",
        })

        # ── Build Indeed search URL directly (reliable, no fragile form-filling)
        # iafc=1 restricts to Indeed Easy Apply jobs only.
        # fromage=N limits to jobs posted within N days.
        params: dict[str, str] = {
            "q": keywords,
            "l": location,
            "iafc": "1",
            "sort": "date",
        }
        if date_range < 30:
            params["fromage"] = str(date_range)

        search_url = "https://au.indeed.com/jobs?" + urllib.parse.urlencode(params)
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
                    'a[data-testid="pagination-page-next"], '
                    'a[aria-label="Next Page"], '
                    'a[aria-label="Next"]'
                ).first
                if await nxt.is_visible(timeout=2000):
                    await nxt.click()
                    await page.wait_for_timeout(2500)
                else:
                    break
            except Exception:
                break

        await send_event({
            "type": "progress", "step": "search",
            "message": f"✓ Found {len(jobs)} Easy Apply jobs — scoring now…",
        })
        return jobs

    async def _extract_job_cards(self, page) -> list[dict]:
        """Three-strategy extraction — always returns what it can find."""
        try:
            return await page.evaluate("""() => {
                const getT = (el, sels) => {
                    for (const s of sels) {
                        const f = el.querySelector(s);
                        if (f) return (f.innerText || f.textContent || f.getAttribute('title') || '').trim();
                    }
                    return '';
                };
                const getJobKey = el => {
                    if (el.dataset.jk) return el.dataset.jk;
                    const inner = el.querySelector('[data-jk]');
                    if (inner) return inner.dataset.jk;
                    // Extract from viewjob URL
                    const link = el.querySelector('a[href*="jk="]');
                    if (link) {
                        const m = (link.href || '').match(/[?&]jk=([a-f0-9]+)/);
                        if (m) return m[1];
                    }
                    return '';
                };

                const results = [];
                const seen = new Set();

                // ── Strategy 1: standard job card elements ───────────────────
                const s1 = document.querySelectorAll(
                    '.job_seen_beacon, [data-jk], li[class*="job"], [class*="jobCard"]'
                );
                s1.forEach(card => {
                    const jobKey = getJobKey(card);
                    if (!jobKey || seen.has(jobKey)) return;
                    const title = getT(card, [
                        'h2.jobTitle a span[title]', 'h2.jobTitle a', 'h2 a span',
                        '[data-testid="jobsearch-JobInfoHeader-title"]',
                        'h2', 'h3', '[class*="title"]'
                    ]);
                    if (!title) return;
                    seen.add(jobKey);
                    results.push({
                        job_id:     jobKey,
                        title,
                        company:    getT(card, ['[data-testid="company-name"]', '.companyName', '[class*="company"]']),
                        location:   getT(card, ['[data-testid="text-location"]', '.companyLocation', '[class*="location"]']),
                        salary:     getT(card, ['[data-testid="attribute_snippet_testid"]', '.salary-snippet', '[class*="salary"]']),
                        url:        'https://au.indeed.com/viewjob?jk=' + jobKey,
                        easy_apply: !!card.querySelector(
                            '.ia-IndeedApplyButton, [class*="IndeedApplyButton"], ' +
                            'button[data-tn-element="applyButton"]'
                        ),
                    });
                });
                if (results.length) return results;

                // ── Strategy 2: any element with data-jk attribute ───────────
                document.querySelectorAll('[data-jk]').forEach(card => {
                    const jobKey = card.dataset.jk;
                    if (!jobKey || seen.has(jobKey)) return;
                    const title = getT(card, ['h2', 'h3', '[class*="title"]', 'a']);
                    if (!title) return;
                    seen.add(jobKey);
                    results.push({
                        job_id: jobKey, title,
                        company: getT(card, ['[class*="company"]']),
                        location: '', salary: '',
                        url: 'https://au.indeed.com/viewjob?jk=' + jobKey,
                        easy_apply: false,
                    });
                });
                if (results.length) return results;

                // ── Strategy 3: grab every viewjob link on the page ──────────
                document.querySelectorAll('a[href*="jk="]').forEach(link => {
                    const m = (link.href || '').match(/[?&]jk=([a-f0-9]+)/);
                    if (!m) return;
                    const jobKey = m[1];
                    if (seen.has(jobKey)) return;
                    const title = (link.innerText || link.textContent || '').trim();
                    if (!title || title.length < 4) return;
                    seen.add(jobKey);
                    results.push({
                        job_id: jobKey, title,
                        company: '', location: '', salary: '',
                        url: 'https://au.indeed.com/viewjob?jk=' + jobKey,
                        easy_apply: false,
                    });
                });
                return results;
            }""")
        except Exception as exc:
            logger.debug("Indeed extraction error: %s", exc)
            return []

    # ── process one job ───────────────────────────────────────────────────────

    async def _process_job(
        self, page, job: dict, profile: dict, criteria: dict, min_score: int,
        send_event: SendFn, reply_queue: asyncio.Queue,
    ) -> bool:
        job_id = job["job_id"]

        # Open job detail
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

        # ── Score first — skip checking Easy Apply until we know the job is worth it ─
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

        # Check Easy Apply availability (after confirming it's a good fit)
        has_easy = await self._has_easy_apply(page)

        # Show to user for review
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

        if not has_easy:
            job["_skipped"] = True
            await send_event({
                "type": "skipped",
                "job_id": job_id,
                "reason": "Skipped because Indeed Easy Apply is not available",
            })
            return False

        # Generate tailored documents
        await send_event({
            "type": "applying", "job_id": job_id,
            "message": f"Generating tailored cover letter for {job['title']}…",
        })
        documents = await self._generate_documents(job, profile)

        cancelled = await self._easy_apply(page, job, profile, documents, send_event, reply_queue)

        if cancelled:
            return True

        job["_applied"] = True
        await send_event({
            "type": "applied", "job_id": job_id,
            "message": f"✓ Applied to {job['title']} at {job['company']}",
        })
        await self._log_to_jats(job)
        return False

    # ── Indeed Easy Apply (iframe) ────────────────────────────────────────────

    async def _has_easy_apply(self, page) -> bool:
        """Return True if Indeed shows an Easy Apply / Apply Now button."""
        for sel in [
            'button:has-text("Apply now")',
            'button:has-text("Easy Apply")',
            '.ia-IndeedApplyButton',
            '[class*="IndeedApplyButton"]',
            'button[data-tn-element="applyButton"]',
            '[class*="ApplyButton" i]',
            'button[aria-label*="apply" i]',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    return True
            except Exception:
                pass
        return False

    async def _easy_apply(
        self, page, job: dict, profile: dict, documents: dict,
        send_event: SendFn, reply_queue: asyncio.Queue,
    ) -> bool:
        """Drive the Indeed Easy Apply iframe flow. Returns True if cancelled."""
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

        # Click the Apply button
        try:
            btn = page.locator(
                '.ia-IndeedApplyButton, '
                '[class*="IndeedApplyButton"], '
                'button[data-tn-element="applyButton"], '
                'button:has-text("Apply now")'
            ).first
            await btn.click()
            await page.wait_for_timeout(2500)
            await self._screenshot(page, send_event)
        except Exception as exc:
            await send_event({
                "type": "progress", "step": "error",
                "message": f"Could not open Easy Apply: {exc}",
            })
            return False

        for _step in range(15):
            await self._screenshot(page, send_event)

            # Check submission success (outside iframe)
            if await self._is_submitted_indeed(page):
                return False

            # Work inside the iframe
            try:
                frame = await self._get_apply_frame(page)
                if frame is None:
                    raise RuntimeError("Could not locate Indeed Apply iframe")

                # Check success inside iframe too
                try:
                    done = frame.locator('text="Your application has been submitted"').first
                    if await done.is_visible(timeout=800):
                        return False
                except Exception:
                    pass

                # Fill contact fields inside iframe
                await self._fill_iframe_fields(frame, profile)

                # Fill visible application questions from the profile + job context
                cancelled = await self._fill_visible_fields(frame, mapper, send_event, reply_queue)
                if cancelled:
                    return True

                # Handle resume selection — Indeed usually pre-selects stored resume
                await self._handle_resume_in_iframe(frame, send_event, reply_queue)

                # Cover letter inside iframe
                result = await self._handle_cover_letter_iframe(
                    frame, documents.get("cover_letter", ""), send_event, reply_queue
                )
                if result == "cancelled":
                    return True

                # Screening questions → pause for user
                has_q = await self._iframe_has_unanswered_questions(frame)
                if has_q:
                    await send_event({
                        "type": "confirm", "field": "screening_questions",
                        "label": (
                            "Some Indeed application questions still need review. "
                            "Please check them in the browser, then click Confirm."
                        ),
                        "suggestion": "", "confidence": 0.5,
                    })
                    reply = await reply_queue.get()
                    if reply.get("action") == "cancel":
                        return True

                # Find Next / Submit button inside iframe
                btn_text, action_btn = await self._find_iframe_button(frame)
                if not action_btn:
                    # Fallback: ask user to advance manually
                    await send_event({
                        "type": "confirm", "field": "manual_step",
                        "label": "Please advance this step in the browser, then click Confirm.",
                        "suggestion": "", "confidence": 0.0,
                    })
                    reply = await reply_queue.get()
                    if reply.get("action") == "cancel":
                        return True
                    continue

                is_final = any(w in btn_text.lower() for w in ("submit", "send application"))
                if is_final:
                    await self._screenshot(page, send_event)
                    await send_event({
                        "type": "confirm", "field": "final_submit",
                        "label": (
                            f"Ready to submit your application to {job['company']}. "
                            "Review the form in the browser, then click Submit Application."
                        ),
                        "suggestion": "", "confidence": 1.0,
                    })
                    reply = await reply_queue.get()
                    if reply.get("action") == "cancel":
                        return True

                await action_btn.click()
                await page.wait_for_timeout(2500)

            except Exception as exc:
                logger.debug("iframe step error: %s", exc)
                # If iframe is gone, application may be submitted
                await self._screenshot(page, send_event)
                if await self._is_submitted_indeed(page):
                    return False
                # Otherwise ask user
                await send_event({
                    "type": "confirm", "field": "manual_step",
                    "label": "Please complete this step manually, then click Confirm.",
                    "suggestion": "", "confidence": 0.0,
                })
                reply = await reply_queue.get()
                if reply.get("action") == "cancel":
                    return True

        return False

    async def _is_submitted_indeed(self, page) -> bool:
        try:
            for text in ("application has been submitted", "You've applied", "Application submitted"):
                el = page.locator(f'text="{text}"').first
                if await el.is_visible(timeout=800):
                    return True
        except Exception:
            pass
        return False

    async def _fill_iframe_fields(self, frame, profile: dict) -> None:
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
                el = frame.locator(selector).first
                if await el.is_visible(timeout=600):
                    current = await el.input_value()
                    if not current.strip():
                        await self._clear_and_type_like_human(frame, el, value)
            except Exception:
                pass

    async def _fill_visible_fields(self, frame, mapper, send_event: SendFn, reply_queue: asyncio.Queue) -> bool:
        try:
            fields = await frame.evaluate("""() => {
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
                    await self._fill_dynamic_field(frame, field, answer)
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
                        await self._fill_dynamic_field(frame, field, final_answer)
            return False
        except Exception:
            return False

    async def _iframe_has_unanswered_questions(self, frame) -> bool:
        try:
            count = await frame.evaluate("""() => {
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

    async def _fill_dynamic_field(self, frame, field: dict, answer: str) -> None:
        selector = field.get("selector") or f'[name="{field["name"]}"]'
        tag = str(field.get("tag") or "input")
        try:
            locator = frame.locator(selector).first
            if tag == "select":
                options = [str(option).strip() for option in field.get("options") or [] if str(option).strip()]
                best = self._best_option_match(answer, options)
                if best:
                    await locator.select_option(label=best)
                    await frame.wait_for_timeout(250)
                return
            await self._clear_and_type_like_human(frame, locator, answer)
        except Exception:
            logger.debug("Could not fill iframe field %s", selector)

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

    async def _handle_resume_in_iframe(self, frame, send_event: SendFn, reply_queue) -> None:
        """If Indeed asks to upload a resume, pause for user to handle it."""
        try:
            upload = frame.locator('input[type="file"], button:has-text("Upload resume")').first
            if await upload.is_visible(timeout=1000):
                await send_event({
                    "type": "confirm", "field": "resume_upload",
                    "label": (
                        "Indeed is asking for a resume upload. "
                        "Please select your resume in the browser, then click Confirm."
                    ),
                    "suggestion": "", "confidence": 0.0,
                })
                await reply_queue.get()  # wait for user
        except Exception:
            pass

    async def _handle_cover_letter_iframe(
        self, frame, cover_letter: str, send_event: SendFn, reply_queue: asyncio.Queue
    ) -> str:
        try:
            ta = frame.locator(
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
                    await self._clear_and_type_like_human(frame, ta, text)
        except Exception:
            pass
        return "ok"

    async def _get_apply_frame(self, page):
        selectors = [
            'iframe[title*="Apply"]',
            'iframe[src*="indeedapply"]',
            'iframe[src*="indeed.com/apply"]',
        ]
        for selector in selectors:
            try:
                handle = await page.locator(selector).first.element_handle(timeout=1000)
                if handle:
                    frame = await handle.content_frame()
                    if frame:
                        return frame
            except Exception:
                pass
        for frame in page.frames:
            url = (frame.url or "").lower()
            if "indeedapply" in url or "indeed.com/apply" in url:
                return frame
        return None

    async def _find_iframe_button(self, frame):
        for selector in [
            'button:has-text("Submit your application")',
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
            'button:has-text("Continue")',
            'button:has-text("Next")',
            'button[type="submit"]',
        ]:
            try:
                btn = frame.locator(selector).last
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
                    '#jobDescriptionText, '
                    '[data-testid="jobsearch-JobComponent-description"], '
                    '.jobsearch-jobDescriptionText'
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
                job_id=job.get("job_id", "indeed"),
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
                platform="Indeed",
                date_applied=date.today().isoformat(),
                status="applied",
                job_url=job.get("url", ""),
                fit_score=job.get("score"),
                notes=f"Auto-applied via Indeed Agent. Score: {job.get('score', '?')}",
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
