"""WebSocket endpoints for agentic job-hunt loops.

LinkedIn  → /ws/agent/linkedin/{session_id}
Seek      → /ws/agent/seek/{session_id}
Indeed    → /ws/agent/indeed/{session_id}

──────────────────────────────────────────────────────────────────────────────
LinkedIn initial message (JSON):
{
  "credentials": {"email": "...", "password": "..."},
  "use_saved":   true,          // load from encrypted store instead
  "profile":     {<CandidateProfile fields>},
  "criteria":    {"keywords": "...", "location": "...", "max_jobs": 10, "min_score": 60}
}

Seek / Indeed initial message (JSON):
{
  "profile":  {<CandidateProfile fields>},
  "criteria": {"keywords": "...", "location": "...", "max_jobs": 10, "min_score": 60, "date_range": 7}
}
──────────────────────────────────────────────────────────────────────────────

Reply messages from client during a session:
  {"action": "confirm"}                – approve / proceed
  {"action": "edit",    "value": "…"} – confirm with edited text (cover letter, etc.)
  {"action": "skip"}                   – skip this job, move to next
  {"action": "cancel"}                 – stop the agent immediately
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.linkedin_agent import LinkedInAgent
from app.services.seek_agent     import SeekAgent
from app.services.indeed_agent   import IndeedAgent
from app.services import credential_store

logger = logging.getLogger(__name__)
router = APIRouter()

_linkedin_agent = LinkedInAgent()
_seek_agent     = SeekAgent()
_indeed_agent   = IndeedAgent()


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_sender(ws: WebSocket):
    async def send_event(event: dict) -> None:
        try:
            await ws.send_json(event)
        except Exception:
            pass
    return send_event


async def _run_agent_session(
    websocket: WebSocket,
    session_id: str,
    agent_coro,          # coroutine that runs the agent
) -> None:
    """Generic WebSocket session driver — shared by all three platforms."""
    await websocket.accept()
    send_event   = _make_sender(websocket)
    reply_queue: asyncio.Queue[dict] = asyncio.Queue()

    try:
        config = await asyncio.wait_for(websocket.receive_json(), timeout=30)

        agent_task = asyncio.create_task(agent_coro(config, send_event, reply_queue))

        try:
            while not agent_task.done():
                try:
                    msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.2)
                    await reply_queue.put(msg)
                    if msg.get("action") == "cancel":
                        agent_task.cancel()
                        break
                except asyncio.TimeoutError:
                    continue
        except WebSocketDisconnect:
            logger.info("Client disconnected — cancelling agent %s", session_id)
            agent_task.cancel()

        try:
            await agent_task
        except asyncio.CancelledError:
            pass

    except asyncio.TimeoutError:
        await send_event({"type": "error", "message": "Timed out waiting for configuration."})
    except WebSocketDisconnect:
        logger.info("Agent session %s disconnected before starting", session_id)
    except Exception as exc:
        logger.exception("Agent WebSocket error in session %s", session_id)
        await send_event({"type": "error", "message": str(exc)})


# ── LinkedIn ──────────────────────────────────────────────────────────────────

@router.websocket("/ws/agent/linkedin/{session_id}")
async def linkedin_agent_ws(websocket: WebSocket, session_id: str) -> None:
    logger.info("LinkedIn agent session: %s", session_id)

    async def _run(config: dict, send_event, reply_queue):
        credentials = config.get("credentials", {})
        if config.get("use_saved"):
            saved = credential_store.load("linkedin")
            if saved:
                credentials = saved
            else:
                await send_event({
                    "type": "error",
                    "message": "No saved LinkedIn credentials. Please enter them manually.",
                })
                return

        await _linkedin_agent.run(
            session_id=session_id,
            credentials=credentials,
            profile=config.get("profile", {}),
            criteria=config.get("criteria", {}),
            send_event=send_event,
            reply_queue=reply_queue,
        )

    await _run_agent_session(websocket, session_id, _run)


# ── Seek ──────────────────────────────────────────────────────────────────────

@router.websocket("/ws/agent/seek/{session_id}")
async def seek_agent_ws(websocket: WebSocket, session_id: str) -> None:
    logger.info("Seek agent session: %s", session_id)

    async def _run(config: dict, send_event, reply_queue):
        await _seek_agent.run(
            session_id=session_id,
            profile=config.get("profile", {}),
            criteria=config.get("criteria", {}),
            send_event=send_event,
            reply_queue=reply_queue,
        )

    await _run_agent_session(websocket, session_id, _run)


# ── Indeed ────────────────────────────────────────────────────────────────────

@router.websocket("/ws/agent/indeed/{session_id}")
async def indeed_agent_ws(websocket: WebSocket, session_id: str) -> None:
    logger.info("Indeed agent session: %s", session_id)

    async def _run(config: dict, send_event, reply_queue):
        await _indeed_agent.run(
            session_id=session_id,
            profile=config.get("profile", {}),
            criteria=config.get("criteria", {}),
            send_event=send_event,
            reply_queue=reply_queue,
        )

    await _run_agent_session(websocket, session_id, _run)
