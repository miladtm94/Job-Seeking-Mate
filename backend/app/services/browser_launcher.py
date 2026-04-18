"""Launch a browser for agents with bot-detection avoidance.

Priority order
--------------
1. **Camoufox** (patched Firefox) — best stealth, no `navigator.webdriver`,
   realistic fingerprint; works without Chrome installed.
2. **Chrome via CDP** — attaches to your real Chrome (no automation flags).
   Requires Google Chrome to be installed.
3. **Playwright Chromium** (fallback) — adds stealth patches but still
   less reliable against Cloudflare than the options above.

Profile isolation
-----------------
Each platform gets its own profile directory under data/browser-profiles/.
Sessions (cookies, localStorage) persist between runs so you only log in once.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Callable, Coroutine

logger = logging.getLogger(__name__)

_PROFILES_ROOT = Path(__file__).resolve().parents[3] / "data" / "browser-profiles"

# Common macOS / Linux Chrome paths (used for CDP fallback)
_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]

# Stealth JS injected when using Playwright Chromium fallback
_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins',   {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-AU', 'en']});
window.chrome = {runtime: {}};
try { delete window.__playwright; } catch(e) {}
"""


def find_chrome() -> str | None:
    """Return path to the system Chrome / Chromium, or None if not found."""
    for p in _CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    return None


async def launch_for_agent(
    pw,
    platform: str,
    debug_port: int,
) -> tuple[object, object, Callable[[], Coroutine]]:
    """Launch (or reconnect to) a browser for the given platform.

    Returns
    -------
    (context, page, cleanup_fn)
        context    – BrowserContext (or Browser acting as context)
        page       – a fresh Page
        cleanup_fn – async function to call when the agent finishes
    """
    profile_dir = _PROFILES_ROOT / platform
    profile_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Camoufox (patched Firefox, best anti-detection) ───────────────────
    try:
        from camoufox.async_api import AsyncCamoufox  # type: ignore[import]

        logger.info("Launching Camoufox (anti-detection Firefox) for %s", platform)
        _cm = AsyncCamoufox(
            headless=False,
            persistent_context=True,
            user_data_dir=str(profile_dir),
        )
        ctx = await _cm.__aenter__()
        page = await ctx.new_page()
        try:
            await page.bring_to_front()
        except Exception:
            pass

        async def _cleanup_camoufox() -> None:
            try:
                await page.close()
            except Exception:
                pass
            try:
                await _cm.__aexit__(None, None, None)
            except Exception:
                pass

        return ctx, page, _cleanup_camoufox

    except ImportError:
        logger.info("Camoufox not installed — trying Chrome CDP (run: pip install 'camoufox[geoip]' && python -m camoufox fetch)")
    except Exception as exc:
        logger.warning("Camoufox failed (%s) — trying Chrome CDP", exc)

    # ── 2. Chrome via CDP (real Chrome, no --enable-automation) ──────────────
    chrome = find_chrome()
    if chrome:
        # Try to reconnect to an already-running Chrome on this port
        try:
            browser = await pw.chromium.connect_over_cdp(
                f"http://localhost:{debug_port}"
            )
            logger.info("Re-attached to existing Chrome (port %d) for %s", debug_port, platform)
            ctx  = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await ctx.new_page()
            await page.bring_to_front()

            async def _cleanup_reattach() -> None:
                try:
                    await page.close()
                except Exception:
                    pass

            return ctx, page, _cleanup_reattach
        except Exception:
            pass  # Chrome not running on this port — launch it

        logger.info("Launching %s (port %d, profile %s)", chrome, debug_port, profile_dir)
        proc = subprocess.Popen(
            [
                chrome,
                f"--remote-debugging-port={debug_port}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-sandbox",
                "--window-size=1440,900",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        browser = None
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                browser = await pw.chromium.connect_over_cdp(
                    f"http://localhost:{debug_port}"
                )
                break
            except Exception:
                continue

        if browser is None:
            proc.terminate()
            raise RuntimeError(
                f"Chrome launched but did not accept CDP on port {debug_port}. "
                "Try running the agent again."
            )

        ctx  = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()
        await page.bring_to_front()

        async def _cleanup_chrome() -> None:
            try:
                await browser.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass

        return ctx, page, _cleanup_chrome

    # ── 3. Playwright Chromium + stealth patches (last resort) ───────────────
    logger.warning(
        "Neither Camoufox nor Google Chrome found. "
        "Falling back to Playwright Chromium with stealth patches. "
        "Install Camoufox for best results: pip install 'camoufox[geoip]' && python -m camoufox fetch"
    )
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        slow_mo=80,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
        ],
    )
    await ctx.add_init_script(_STEALTH_SCRIPT)
    page = await ctx.new_page()

    async def _cleanup_ctx() -> None:
        try:
            await ctx.close()
        except Exception:
            pass

    return ctx, page, _cleanup_ctx
