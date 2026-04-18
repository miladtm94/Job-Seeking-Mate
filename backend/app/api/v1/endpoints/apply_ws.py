"""WebSocket endpoint for real-time browser-automation job applications.

Connect: ws://localhost:8000/ws/apply/{session_id}

Protocol
--------
Client → Server (first message):
  {
    "job_url":     "https://au.indeed.com/viewjob?jk=...",
    "platform":    "indeed" | "linkedin" | "seek" | "generic",
    "credentials": {"email": "...", "password": "..."},
    "profile":     {<CandidateProfile fields>},
    "documents": {
      "resume_text":      "...",
      "cover_letter":     "...",
      "resume_pdf_path":  "/abs/path/to/resume.pdf",
      "job_title":        "Senior ML Engineer",
      "job_company":      "Atlassian",
      "job_description":  "..."
    }
  }

Server → Client (streaming events):
  {"type": "progress",  "step": str, "message": str}
  {"type": "confirm",   "field": str, "label": str, "suggestion": str, "confidence": float}
  {"type": "screenshot","data": str}   # base64 JPEG
  {"type": "success",   "message": str}
  {"type": "error",     "message": str}

Client → Server (replies to "confirm" events):
  {"action": "confirm"}                          # accept AI suggestion
  {"action": "edit",    "value": "custom text"}  # override with own value
  {"action": "cancel"}                           # abort the session
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.browser_apply import BrowserApplyService
from app.services.pdf_generator import ResumePDFGenerator
import app.services.jats_service as _jats_svc

logger = logging.getLogger(__name__)
router = APIRouter()

_pdf_gen = ResumePDFGenerator()
_apply_svc = BrowserApplyService()


@router.websocket("/ws/apply/{session_id}")
async def apply_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    logger.info("AutoApply session started: %s", session_id)

    reply_queue: asyncio.Queue[dict] = asyncio.Queue()

    async def send_event(event: dict) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    try:
        # ── Receive configuration ────────────────────────────────────────────
        config = await asyncio.wait_for(websocket.receive_json(), timeout=30)

        job_url   = config["job_url"]
        credentials = config["credentials"]
        profile   = config["profile"]
        documents = config.get("documents", {})

        # ── Generate PDF resume if not already done ──────────────────────────
        resume_pdf_path = documents.get("resume_pdf_path", "")
        if not resume_pdf_path and documents.get("resume_text"):
            await send_event({"type": "progress", "step": "pdf", "message": "Generating resume PDF…"})
            try:
                path = _pdf_gen.generate(
                    resume_text=documents["resume_text"],
                    candidate_name=profile.get("name", "candidate"),
                )
                documents["resume_pdf_path"] = str(path)
                await send_event({"type": "progress", "step": "pdf", "message": f"✓ Resume PDF ready: {path.name}"})
            except Exception as exc:
                await send_event({"type": "progress", "step": "pdf", "message": f"⚠ PDF generation failed ({exc}) — continuing without upload"})

        # ── Start browser task ───────────────────────────────────────────────
        browser_task = asyncio.create_task(
            _apply_svc.run_session(
                session_id=session_id,
                job_url=job_url,
                credentials=credentials,
                profile=profile,
                documents=documents,
                send_event=send_event,
                reply_queue=reply_queue,
            )
        )

        # ── Relay client replies to the browser task ─────────────────────────
        try:
            while not browser_task.done():
                try:
                    msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.2)
                    await reply_queue.put(msg)
                    if msg.get("action") == "cancel":
                        browser_task.cancel()
                        break
                except asyncio.TimeoutError:
                    continue

        except WebSocketDisconnect:
            logger.info("Client disconnected — cancelling session %s", session_id)
            browser_task.cancel()

        # Wait for browser task to finish
        try:
            await browser_task
        except asyncio.CancelledError:
            pass

        # ── Auto-log to JATS tracker on success ──────────────────────────────
        if not browser_task.cancelled():
            try:
                from app.schemas.jats import LogApplicationRequest
                from app.db.jats_db import JATSSessionLocal
                from datetime import date

                req = LogApplicationRequest(
                    company=documents.get("job_company", "Unknown"),
                    role_title=documents.get("job_title", "Unknown"),
                    platform=_detect_platform_label(job_url),
                    date_applied=date.today().isoformat(),
                    status="applied",
                    job_url=job_url,
                    resume_used=documents.get("resume_pdf_path", ""),
                    cover_letter=documents.get("cover_letter", ""),
                    required_skills=profile.get("skills", [])[:10],
                    notes="Auto-applied via AI assistant",
                )
                db = JATSSessionLocal()
                try:
                    _jats_svc.log_application(db, req)
                    db.commit()
                finally:
                    db.close()
                await send_event({"type": "progress", "step": "jats", "message": "✓ Application logged to tracker"})
            except Exception as exc:
                logger.warning("Failed to auto-log to JATS: %s", exc)

    except asyncio.TimeoutError:
        await send_event({"type": "error", "message": "Timed out waiting for configuration."})
    except WebSocketDisconnect:
        logger.info("Session %s disconnected before starting", session_id)
    except Exception as exc:
        logger.exception("WebSocket session error")
        await send_event({"type": "error", "message": str(exc)})


def _detect_platform_label(url: str) -> str:
    url_lower = url.lower()
    if "indeed.com" in url_lower:
        return "Indeed"
    if "linkedin.com" in url_lower:
        return "LinkedIn"
    if "seek.com" in url_lower:
        return "Seek"
    return "Direct"
