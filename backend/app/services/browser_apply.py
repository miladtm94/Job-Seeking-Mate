"""Playwright-based automated job application service.

Architecture
------------
The public entry point is `BrowserApplyService.run_session()`, an async coroutine
that drives a visible Chromium browser through the full application flow while
streaming structured events back to the caller (typically a WebSocket handler).

Event types emitted via `send_event`:
  {"type": "progress",  "step": str, "message": str}
  {"type": "confirm",   "field": str, "label": str, "suggestion": str, "confidence": float}
  {"type": "screenshot","data": str}   # base64-encoded PNG
  {"type": "success",   "message": str}
  {"type": "error",     "message": str}

The caller pushes user responses (confirm / edit / cancel) into `reply_queue`
as dicts: {"action": "confirm"|"edit"|"cancel", "value": str|None}
"""
from __future__ import annotations

import asyncio
import base64
import logging
import random
import re
from pathlib import Path
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

Event = dict[str, Any]
SendFn = Callable[[Event], Coroutine]


def _b64_screenshot(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "indeed.com" in url_lower:
        return "indeed"
    if "linkedin.com" in url_lower:
        return "linkedin"
    if "seek.com" in url_lower:
        return "seek"
    return "generic"


# ── field mapper ─────────────────────────────────────────────────────────────

class FieldMapper:
    """Maps detected HTML form fields to candidate answers using profile data + AI."""

    # High-confidence direct mappings: (label keywords) → answer resolver
    _DIRECT: list[tuple[tuple[str, ...], str]] = [
        (("first name", "given name"),                        "first_name"),
        (("last name", "surname", "family name"),             "last_name"),
        (("full name", "your name"),                          "full_name"),
        (("email",),                                          "email"),
        (("phone", "mobile", "contact number"),               "phone"),
        (("city", "suburb", "location"),                      "city"),
        (("country",),                                        "country"),
        (("linkedin",),                                       "linkedin"),
        (("github", "portfolio"),                             "github"),
        (("years of experience", "how many years"),           "years_experience"),
        (("current salary", "expected salary", "salary"),     "salary"),
        (("industry", "industry category"),                   "industry"),
        (("current title", "current role", "job title"),      "current_role"),
        (("preferred role", "desired role"),                  "desired_role"),
        (("work type", "work arrangement"),                   "work_type"),
        (("work authoris", "work authoriz", "right to work"), "work_auth"),
        (("notice period",),                                  "notice_period"),
        (("cover letter",),                                   "cover_letter"),
    ]

    def __init__(self, profile: dict, documents: dict) -> None:
        self._profile = profile
        self._documents = documents
        self._cache: dict[str, tuple[str, float]] = {}  # field_key → (value, confidence)

    def resolve(self, label: str, field_type: str) -> tuple[str, float]:
        """Return (answer, confidence 0-1) for a detected form field."""
        label_lower = label.lower().strip()
        cache_key = label_lower

        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._direct_lookup(label_lower)
        if result is None and field_type in ("textarea", "text", "select"):
            result = self._ai_lookup(label, field_type)
        if result is None:
            result = ("", 0.0)

        self._cache[cache_key] = result
        return result

    def _direct_lookup(self, label_lower: str) -> tuple[str, float] | None:
        for keywords, resolver in self._DIRECT:
            if any(kw in label_lower for kw in keywords):
                value = self._get_profile_value(resolver)
                if value:
                    return value, 0.95
        return None

    def _get_profile_value(self, key: str) -> str:
        p = self._profile
        name = p.get("name", "")
        parts = name.split() if name else []

        mapping = {
            "first_name":      parts[0] if parts else "",
            "last_name":       parts[-1] if len(parts) > 1 else "",
            "full_name":       name,
            "email":           p.get("email", ""),
            "phone":           p.get("phone", ""),
            "city":            (p.get("locations") or [""])[0],
            "country":         p.get("country", "Australia"),
            "linkedin":        p.get("linkedin_url", ""),
            "github":          p.get("github_url", ""),
            "years_experience": str(p.get("years_experience", "")),
            "salary":          str(p.get("salary_min", "")) if p.get("salary_min") else "",
            "industry":        ", ".join((p.get("industries") or [])[:3]),
            "current_role":    (p.get("target_roles") or p.get("preferred_roles") or [""])[0],
            "desired_role":    (p.get("preferred_roles") or p.get("target_roles") or [""])[0],
            "work_type":       p.get("work_type", "any"),
            "work_auth":       p.get("work_auth", "Yes, I am authorised to work"),
            "notice_period":   p.get("notice_period", "2 weeks"),
            "cover_letter":    self._documents.get("cover_letter", ""),
        }
        return mapping.get(key, "")

    def _ai_lookup(self, label: str, field_type: str) -> tuple[str, float] | None:
        """Use the AI client to answer open-ended questions."""
        try:
            from app.core.ai_client import ai_complete

            system = (
                "You are filling out a job application form on behalf of a candidate. "
                "Answer the field question concisely and professionally. "
                "Use only real information from the candidate profile. "
                "If the question is a selection/dropdown style question, return the single best option label only. "
                "Return ONLY the answer text, nothing else."
            )
            p = self._profile
            prompt = (
                f"Field question: {label}\n\n"
                f"Candidate profile:\n"
                f"Name: {p.get('name', '')}\n"
                f"Seniority: {p.get('seniority', '')}\n"
                f"Experience: {p.get('years_experience', '')} years\n"
                f"Skills: {', '.join((p.get('skills') or [])[:15])}\n"
                f"Industries: {', '.join((p.get('industries') or [])[:5])}\n"
                f"Target roles: {', '.join((p.get('target_roles') or p.get('preferred_roles') or [])[:5])}\n"
                f"Work type: {p.get('work_type', 'any')}\n"
                f"Summary: {p.get('summary', '')}\n\n"
                f"Job context: {self._documents.get('job_title', '')} at "
                f"{self._documents.get('job_company', '')}\n"
                f"Job description excerpt:\n{self._documents.get('job_description', '')[:800]}"
            )
            answer = ai_complete(system, prompt, max_tokens=300, task="generate")
            if answer and len(answer.strip()) > 2:
                confidence = 0.72 if field_type == "select" else 0.65
                return answer.strip(), confidence
        except Exception:
            logger.exception("AI field lookup failed for: %s", label)
        return None


# ── main service ─────────────────────────────────────────────────────────────

class BrowserApplyService:
    """Drives a Playwright browser through the full job application flow."""

    CONFIRM_THRESHOLD = 0.85   # auto-fill above this confidence
    TIMEOUT_MS        = 15_000  # navigation / element wait timeout

    async def _human_pause(self, scope, minimum_ms: int = 120, maximum_ms: int = 420) -> None:
        await scope.wait_for_timeout(random.randint(minimum_ms, maximum_ms))

    async def _type_like_human(self, page, selector: str, value: str) -> None:
        locator = page.locator(selector).first
        await locator.click()
        await self._human_pause(page, 120, 260)
        await page.keyboard.press("Control+a")
        await self._human_pause(page, 60, 140)
        await page.keyboard.press("Delete")
        await self._human_pause(page, 100, 220)
        for index, char in enumerate(value):
            await page.keyboard.type(char, delay=random.randint(55, 135))
            if char in {" ", ",", "-", "/"}:
                await self._human_pause(page, 80, 220)
            elif index and index % random.randint(6, 11) == 0:
                await self._human_pause(page, 90, 260)
        await self._human_pause(page, 140, 320)

    async def run_session(
        self,
        session_id: str,
        job_url: str,
        credentials: dict,   # {email, password}
        profile: dict,
        documents: dict,     # {resume_text, cover_letter, resume_pdf_path, job_title, job_company, job_description}
        send_event: SendFn,
        reply_queue: asyncio.Queue,
    ) -> None:
        platform = _detect_platform(job_url)
        mapper = FieldMapper(profile, documents)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            await send_event({"type": "error", "message": "Playwright not installed. Run: pip install playwright && playwright install chromium"})
            return

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=False,          # visible browser — user can watch
                    slow_mo=120,             # slight delay so actions look human
                    args=["--start-maximized"],
                )
                ctx = await browser.new_context(
                    viewport=None,           # use window size
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
                page = await ctx.new_page()

                # Each apply method returns True on success, False on user cancel
                if platform == "indeed":
                    completed = await self._apply_indeed(page, job_url, credentials, profile, documents, mapper, send_event, reply_queue)
                elif platform == "linkedin":
                    completed = await self._apply_linkedin(page, job_url, credentials, profile, documents, mapper, send_event, reply_queue)
                elif platform == "seek":
                    completed = await self._apply_seek(page, job_url, credentials, profile, documents, mapper, send_event, reply_queue)
                else:
                    completed = await self._apply_generic(page, job_url, credentials, profile, documents, mapper, send_event, reply_queue)

                await browser.close()

                if completed:
                    await send_event({"type": "success", "message": "✓ Application submitted successfully."})
                else:
                    await send_event({"type": "error", "message": "Session was cancelled before submission."})

        except asyncio.CancelledError:
            await send_event({"type": "error", "message": "Session cancelled by user."})
        except Exception as exc:
            logger.exception("Browser apply session failed")
            await send_event({"type": "error", "message": f"Unexpected error: {exc}"})

    # ── Indeed ───────────────────────────────────────────────────────────────

    async def _apply_indeed(self, page, job_url, credentials, profile, documents, mapper, send_event, reply_queue) -> bool:
        # 1. Login (skip if no credentials provided)
        if credentials.get("email") and credentials.get("password"):
            await send_event({"type": "progress", "step": "login", "message": "Opening Indeed login…"})
            await page.goto("https://secure.indeed.com/auth?hl=en_AU&co=AU", wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            # Email step
            email_sel = 'input[name="__email"], input[type="email"], #login-email-input'
            try:
                await page.wait_for_selector(email_sel, timeout=self.TIMEOUT_MS)
                await self._type_like_human(page, email_sel, credentials["email"])
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(500)
                await page.click('button[type="submit"]')
                await page.wait_for_timeout(2000)
            except Exception:
                pass

            # Password step (may be on a new page)
            pwd_sel = 'input[name="__password"], input[type="password"], #login-password-input'
            try:
                await page.wait_for_selector(pwd_sel, timeout=self.TIMEOUT_MS)
                await self._type_like_human(page, pwd_sel, credentials["password"])
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(500)
                await page.click('button[type="submit"]')
                await page.wait_for_load_state("networkidle", timeout=self.TIMEOUT_MS)
            except Exception:
                pass

            # Check for CAPTCHA / verification
            if await self._check_captcha(page):
                await send_event({
                    "type": "confirm",
                    "field": "captcha",
                    "label": "Human verification required — please complete it in the browser window",
                    "suggestion": "Complete the CAPTCHA or email verification, then click Confirm to continue.",
                    "confidence": 0.0,
                })
                reply = await reply_queue.get()
                if reply.get("action") == "cancel":
                    return False

            await send_event({"type": "progress", "step": "login", "message": "✓ Logged in to Indeed"})
            await self._send_screenshot(page, send_event)

        # 2. Navigate to job
        await send_event({"type": "progress", "step": "navigate", "message": "Navigating to job posting…"})
        await page.goto(job_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await send_event({"type": "progress", "step": "navigate", "message": "✓ Job posting loaded"})
        await self._send_screenshot(page, send_event)

        # 3. Click Apply / Easy Apply
        apply_selectors = [
            'button.ia-IndeedApplyButton',
            'button[data-jk]',
            'button:has-text("Apply now")',
            'a:has-text("Apply now")',
            '.jobsearch-IndeedApplyButton',
            'button:has-text("Easy Apply")',
        ]
        clicked = False
        for sel in apply_selectors:
            try:
                btn = page.locator(sel).first
                if await self._is_visible_safe(btn):
                    await btn.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            await send_event({
                "type": "confirm",
                "field": "apply_button",
                "label": "Could not find Apply button automatically",
                "suggestion": "Please click the Apply / Easy Apply button in the browser window, then click Confirm here.",
                "confidence": 0.0,
            })
            reply = await reply_queue.get()
            if reply.get("action") == "cancel":
                return False

        await page.wait_for_timeout(2500)
        await send_event({"type": "progress", "step": "apply", "message": "✓ Application form opened"})
        await self._send_screenshot(page, send_event)

        # 4. Fill multi-step form
        return await self._fill_indeed_form(page, documents, mapper, send_event, reply_queue)

    async def _fill_indeed_form(self, page, documents, mapper, send_event, reply_queue) -> bool:
        """Walk through Indeed Easy Apply steps, filling each field. Returns True on submit."""
        max_steps = 10
        for step_num in range(max_steps):
            await send_event({"type": "progress", "step": f"form_step_{step_num}", "message": f"Filling form — step {step_num + 1}…"})

            # Upload resume if file input present
            resume_input = page.locator('input[type="file"]').first
            try:
                visible = await resume_input.is_visible(timeout=1000)
            except Exception:
                visible = False
            if visible:
                pdf_path = documents.get("resume_pdf_path", "")
                if pdf_path and Path(pdf_path).exists():
                    await resume_input.set_input_files(pdf_path)
                    await send_event({"type": "progress", "step": f"form_step_{step_num}", "message": "✓ Resume PDF uploaded"})
                    await page.wait_for_timeout(1000)

            # Detect and fill all visible fields
            cancelled = await self._fill_visible_fields(page, mapper, send_event, reply_queue)
            if cancelled:
                return False
            await self._send_screenshot(page, send_event)

            # Check for submit button first (last step)
            submit_selectors = [
                'button:has-text("Submit")',
                'button:has-text("Submit application")',
                'button[aria-label*="Submit"]',
            ]
            submitted = False
            for sel in submit_selectors:
                try:
                    btn = page.locator(sel).first
                    if await self._is_visible_safe(btn):
                        await send_event({
                            "type": "confirm",
                            "field": "final_submit",
                            "label": "Ready to submit — please review the completed form in the browser",
                            "suggestion": "Click Confirm to submit, or Cancel to abort.",
                            "confidence": 1.0,
                        })
                        reply = await reply_queue.get()
                        if reply.get("action") == "cancel":
                            return False
                        await btn.click()
                        await page.wait_for_timeout(3000)
                        submitted = True
                        break
                except Exception:
                    continue

            if submitted:
                return True

            # Click Continue/Next
            next_selectors = [
                'button:has-text("Continue")',
                'button:has-text("Next")',
                'button[aria-label*="Continue"]',
            ]
            moved = False
            for sel in next_selectors:
                try:
                    btn = page.locator(sel).first
                    if await self._is_visible_safe(btn):
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        moved = True
                        break
                except Exception:
                    continue

            if not moved:
                break

        return False

    async def _fill_visible_fields(self, page, mapper: FieldMapper, send_event, reply_queue) -> bool:
        """Detect all visible form inputs and fill them. Returns True if user cancelled."""
        try:
            fields = await page.evaluate("""() => {
                const results = [];
                const inputs = document.querySelectorAll('input:not([type="file"]):not([type="hidden"]):not([type="submit"]), textarea, select');
                inputs.forEach(el => {
                    if (!el.offsetParent) return;
                    let label = '';
                    if (el.id) {
                        const lbl = document.querySelector('label[for="' + el.id + '"]');
                        if (lbl) label = lbl.innerText.trim();
                    }
                    if (!label) label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || '';
                    results.push({
                        selector: el.id ? '#' + el.id : null,
                        name: el.getAttribute('name') || '',
                        label: label,
                        type: el.tagName.toLowerCase() === 'select' ? 'select' : (el.getAttribute('type') || 'text'),
                        tag: el.tagName.toLowerCase(),
                        value: el.value || '',
                    });
                });
                return results;
            }""")
        except Exception:
            return False

        for field in fields:
            if not field.get("label"):
                continue
            label = field["label"]
            field_type = field.get("type", "text")
            existing_value = field.get("value", "").strip()

            # Skip already-filled fields
            if existing_value and len(existing_value) > 1:
                continue

            answer, confidence = mapper.resolve(label, field_type)
            if not answer:
                continue

            if confidence >= self.CONFIRM_THRESHOLD:
                await self._fill_field(page, field, answer)
                await send_event({
                    "type": "progress",
                    "step": "fill",
                    "message": f"✓ {label}: {answer[:60]}{'…' if len(answer) > 60 else ''}",
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
                    return True  # cancelled
                final_answer = reply.get("value", answer) if reply.get("action") == "edit" else answer
                if final_answer:
                    await self._fill_field(page, field, final_answer)
                    await send_event({"type": "progress", "step": "fill", "message": f"✓ {label} (confirmed)"})

        return False  # not cancelled

    async def _fill_field(self, page, field: dict, value: str) -> None:
        """Fill a single form field by selector or name."""
        sel = field.get("selector") or f'[name="{field["name"]}"]'
        tag = field.get("tag", "input")
        try:
            if tag == "select":
                await page.select_option(sel, label=value)
            else:
                await self._type_like_human(page, sel, value)
            await self._human_pause(page, 120, 260)
        except Exception:
            logger.debug("Could not fill field %s", sel)

    async def _fill_linkedin_modal(
        self,
        page,
        profile: dict,
        documents: dict,
        mapper: FieldMapper,
        send_event: SendFn,
        reply_queue: asyncio.Queue,
    ) -> bool:
        """Fill the LinkedIn Easy Apply modal already open on the current job page.

        Returns True if the flow was cancelled, False otherwise.
        """
        easy_apply = page.locator('button.jobs-apply-button, button:has-text("Easy Apply")').first
        try:
            if await self._is_visible_safe(easy_apply):
                await easy_apply.click()
                await page.wait_for_timeout(1800)
            else:
                await send_event({
                    "type": "confirm", "field": "apply_button",
                    "label": "Could not find the LinkedIn Easy Apply button automatically",
                    "suggestion": "Click the Easy Apply button in the browser, then Confirm here.",
                    "confidence": 0.0,
                })
                reply = await reply_queue.get()
                if reply.get("action") == "cancel":
                    return True
        except Exception:
            await send_event({
                "type": "confirm", "field": "apply_button",
                "label": "LinkedIn Easy Apply needs manual confirmation in the browser",
                "suggestion": "Open the Easy Apply modal, then click Confirm here.",
                "confidence": 0.0,
            })
            reply = await reply_queue.get()
            if reply.get("action") == "cancel":
                return True

        for step_num in range(12):
            await send_event({"type": "progress", "step": f"form_step_{step_num}", "message": f"Filling LinkedIn step {step_num + 1}…"})
            cancelled = await self._fill_visible_fields(page, mapper, send_event, reply_queue)
            if cancelled:
                return True
            await self._send_screenshot(page, send_event)

            submit_btn = page.locator(
                'button[aria-label="Submit application"], button:has-text("Submit application")'
            ).first
            if await self._is_visible_safe(submit_btn):
                await send_event({
                    "type": "confirm", "field": "final_submit",
                    "label": "Ready to submit to LinkedIn — review the Easy Apply modal in the browser",
                    "suggestion": "Click Confirm to submit, or Cancel to abort.",
                    "confidence": 1.0,
                })
                reply = await reply_queue.get()
                if reply.get("action") == "cancel":
                    return True
                await submit_btn.click()
                await page.wait_for_timeout(2200)
                return False

            next_btn = page.locator(
                'button[aria-label="Continue to next step"], button:has-text("Next"), button:has-text("Review")'
            ).first
            if await self._is_visible_safe(next_btn):
                await next_btn.click()
                await page.wait_for_timeout(1600)
                continue

            dismiss_btn = page.locator('button[aria-label="Dismiss"]').first
            if await self._is_visible_safe(dismiss_btn):
                return False

            break

        return False

    # ── LinkedIn ─────────────────────────────────────────────────────────────

    async def _apply_linkedin(self, page, job_url, credentials, profile, documents, mapper, send_event, reply_queue) -> bool:
        await send_event({"type": "progress", "step": "login", "message": "Opening LinkedIn login…"})
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        try:
            await self._type_like_human(page, '#username', credentials["email"])
            await self._type_like_human(page, '#password', credentials["password"])
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=self.TIMEOUT_MS)
        except Exception:
            pass

        if await self._check_captcha(page):
            await send_event({
                "type": "confirm", "field": "captcha",
                "label": "LinkedIn verification required — complete it in the browser",
                "suggestion": "Complete any verification step, then click Confirm.",
                "confidence": 0.0,
            })
            reply = await reply_queue.get()
            if reply.get("action") == "cancel":
                return False

        await send_event({"type": "progress", "step": "login", "message": "✓ Logged in to LinkedIn"})
        await page.goto(job_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await self._send_screenshot(page, send_event)

        easy_apply = page.locator('button.jobs-apply-button, button:has-text("Easy Apply")').first
        if not await self._is_visible_safe(easy_apply):
            await send_event({
                "type": "confirm", "field": "apply_button",
                "label": "Could not find Easy Apply button — click it in the browser",
                "suggestion": "Click the Easy Apply button, then Confirm here.",
                "confidence": 0.0,
            })
            reply = await reply_queue.get()
            if reply.get("action") == "cancel":
                return False
        else:
            await easy_apply.click()

        await page.wait_for_timeout(2000)

        for step_num in range(10):
            await send_event({"type": "progress", "step": f"form_step_{step_num}", "message": f"Filling step {step_num + 1}…"})
            cancelled = await self._fill_visible_fields(page, mapper, send_event, reply_queue)
            if cancelled:
                return False
            await self._send_screenshot(page, send_event)

            submit_btn = page.locator('button[aria-label="Submit application"]').first
            if await self._is_visible_safe(submit_btn):
                await send_event({
                    "type": "confirm", "field": "final_submit",
                    "label": "Ready to submit to LinkedIn — review the form in the browser",
                    "suggestion": "Click Confirm to submit, or Cancel to abort.",
                    "confidence": 1.0,
                })
                reply = await reply_queue.get()
                if reply.get("action") == "cancel":
                    return False
                await submit_btn.click()
                await page.wait_for_timeout(2000)
                return True

            next_btn = page.locator('button[aria-label="Continue to next step"]').first
            if await self._is_visible_safe(next_btn):
                await next_btn.click()
                await page.wait_for_timeout(1500)
            else:
                break

        return False

    # ── Seek ─────────────────────────────────────────────────────────────────

    async def _apply_seek(self, page, job_url, credentials, profile, documents, mapper, send_event, reply_queue) -> bool:
        await send_event({"type": "progress", "step": "login", "message": "Opening Seek login…"})
        await page.goto("https://www.seek.com.au/oauth/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        try:
            await self._type_like_human(page, 'input[name="email"]', credentials["email"])
            await self._type_like_human(page, 'input[name="password"]', credentials["password"])
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=self.TIMEOUT_MS)
        except Exception:
            await send_event({
                "type": "confirm", "field": "login",
                "label": "Please complete Seek login in the browser",
                "suggestion": "Log in manually, then click Confirm to continue.",
                "confidence": 0.0,
            })
            reply = await reply_queue.get()
            if reply.get("action") == "cancel":
                return False

        await send_event({"type": "progress", "step": "login", "message": "✓ Logged in to Seek"})
        await page.goto(job_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await self._send_screenshot(page, send_event)

        apply_btn = page.locator('a:has-text("Quick apply"), button:has-text("Apply")').first
        if await self._is_visible_safe(apply_btn):
            await apply_btn.click()
            await page.wait_for_timeout(2000)
        else:
            await send_event({
                "type": "confirm", "field": "apply_button",
                "label": "Please click the Apply button in the browser",
                "suggestion": "Then click Confirm here.",
                "confidence": 0.0,
            })
            reply = await reply_queue.get()
            if reply.get("action") == "cancel":
                return False

        cancelled = await self._fill_visible_fields(page, mapper, send_event, reply_queue)
        if cancelled:
            return False
        await self._send_screenshot(page, send_event)

        submit_btn = page.locator('button:has-text("Submit"), button:has-text("Apply")').last
        if await self._is_visible_safe(submit_btn):
            await send_event({
                "type": "confirm", "field": "final_submit",
                "label": "Ready to submit to Seek — review the form in the browser",
                "suggestion": "Click Confirm to submit, or Cancel to abort.",
                "confidence": 1.0,
            })
            reply = await reply_queue.get()
            if reply.get("action") == "cancel":
                return False
            await submit_btn.click()
            await page.wait_for_timeout(2000)
            return True

        return False

    # ── Generic / direct company website ─────────────────────────────────────

    async def _apply_generic(self, page, job_url, credentials, profile, documents, mapper, send_event, reply_queue) -> bool:
        await send_event({"type": "progress", "step": "navigate", "message": "Opening job URL…"})
        await page.goto(job_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await self._send_screenshot(page, send_event)
        await send_event({
            "type": "confirm", "field": "login",
            "label": "Direct company site — log in if required and navigate to the application form",
            "suggestion": "Once the application form is visible on screen, click Confirm and the AI will fill it in.",
            "confidence": 0.0,
        })
        reply = await reply_queue.get()
        if reply.get("action") == "cancel":
            return False

        cancelled = await self._fill_visible_fields(page, mapper, send_event, reply_queue)
        if cancelled:
            return False
        await self._send_screenshot(page, send_event)

        await send_event({
            "type": "confirm", "field": "final_submit",
            "label": "Please review the completed form in the browser, then click Confirm to submit",
            "suggestion": "Check all fields look correct, then confirm.",
            "confidence": 1.0,
        })
        reply = await reply_queue.get()
        if reply.get("action") == "cancel":
            return False
        return True

    # ── utilities ─────────────────────────────────────────────────────────────

    async def _send_screenshot(self, page, send_event: SendFn) -> None:
        try:
            data = await page.screenshot(type="jpeg", quality=70, full_page=False)
            await send_event({"type": "screenshot", "data": _b64_screenshot(data)})
        except Exception:
            pass

    async def _check_captcha(self, page) -> bool:
        """Returns True if a CAPTCHA or verification page is detected."""
        try:
            content = await page.content()
            keywords = ["captcha", "recaptcha", "verify you're human", "challenge", "security check"]
            return any(kw in content.lower() for kw in keywords)
        except Exception:
            return False

    @staticmethod
    async def _is_visible_safe(locator) -> bool:
        try:
            return await locator.is_visible(timeout=1500)
        except Exception:
            return False
