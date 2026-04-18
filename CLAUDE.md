# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Job-Seeking Mate** is a full-stack AI-powered job search platform. Core capabilities:
- **Resume Library**: Upload PDFs; system auto-selects the best match per job
- **Smart Job Search**: Aggregates from Adzuna and Indeed, scored 0–100 using an expert recruiter workflow
- **Application Generation**: Produces tailored resume, cover letter, and interview talking points
- **JATS Tracker**: Paste a JD → AI extracts fields → log application with event timeline and analytics

## Common Commands

All high-level commands are in the `Makefile`:

```bash
make install      # pip install -e .[dev] + npm install
make backend      # uvicorn app.main:app --reload --port 8000
make frontend     # vite dev server on :5173
make test         # cd backend && pytest -q
make lint         # ruff check + mypy (backend) + tsc noEmit (frontend)
make format       # ruff format .
make up           # docker compose up --build (all services)
make migrate      # alembic upgrade head
```

Run a single backend test:
```bash
cd backend && pytest tests/test_matching.py::test_match_score_strong_apply_threshold -v
```

The frontend has no independent test suite — linting is via `npm run lint` (TypeScript `noEmit` check).

## Environment Configuration

Copy `.env.example` to `.env`. Set exactly one AI provider:

| Provider | Key variable | Notes |
|---|---|---|
| Anthropic (recommended) | `ANTHROPIC_API_KEY` | Model: `claude-sonnet-4-20250514` |
| Google Gemini | `GEMINI_API_KEY` | Free tier available |
| OpenAI | `OPENAI_API_KEY` | |
| LM Studio / Ollama | _(no key)_ | Local, set endpoint URL |

Job APIs (`ADZUNA_APP_ID`/`ADZUNA_API_KEY`, `JSEARCH_API_KEY`) are optional.

User-selected provider/model settings persist in `data/user_settings.json` (survives container restarts and overrides `.env` values).

## Architecture

### Backend (`backend/app/`)

**Request flow**: FastAPI → `api/v1/router.py` → endpoint → service → AI/DB

Key layers:
- **`api/v1/endpoints/`** – Thin HTTP handlers; delegate all logic to services
- **`services/`** – All business logic lives here
- **`agents/`** – Multi-step orchestration using a Plan→Act→Evaluate→Refine loop (`base.py` defines `BaseAgent`)
- **`core/config.py`** – Single `Settings` Pydantic BaseSettings object; user overrides in `data/user_settings.json`
- **`core/ai_client.py`** – Pluggable AI abstraction; selects provider at runtime based on config

**Expert recruiter scoring bands** (used throughout services):
- `≥65` → apply with cover letter, resume as-is
- `50–64` → surgical resume improvements + cover letter
- `41–49` → full new resume + cover letter
- `≤40` → do not apply

**AI scoring** uses two models: `ai_model` for generation tasks, `ai_score_model` for scoring (can differ for cost/speed tradeoffs).

### Databases

**PostgreSQL** (primary, via SQLAlchemy 2.0): Candidates, Jobs, MatchScores.

**SQLite** (JATS tracker, at `data/jats_tracker.db`): Three tables:
- `jats_applications` – Application entries (company, role, status, fit_score, follow_up_date, …)
- `jats_application_skills` – M2M pivot for skills per application
- `jats_application_events` – Timeline events per application

### Frontend (`frontend/src/`)

**Framework**: React 19 + TypeScript, Vite, React Router 7, TanStack Query 5 for all server state.

**Key files**:
- `App.tsx` – Route definitions and sidebar nav
- `api/client.ts` – Typed API client; all backend calls go through here; handles JWT from `localStorage`, auto-redirects on 401
- `contexts/AuthContext.tsx` – `useAuth()` hook for login/logout/token management
- `styles/global.css` – CSS variables–based design system

**Route → page mapping**:
- `/` → DashboardPage
- `/find-jobs` → HuntPage (resume upload + job search)
- `/my-applications` → MyApplicationsPage (JATS list)
- `/log-application` → LogApplicationPage (JATS entry)
- `/analytics` → AnalyticsPage
- `/settings` → SettingsPage (AI provider config)

### Background Services

- **Celery + Redis** (`worker` service in Docker): handles async automation tasks
- **WebSocket endpoints**: `apply_ws` and `agent_ws` for real-time browser automation status (not under `/api/v1` prefix)
- **Playwright + Camoufox** (`browser_apply.py`): browser automation for auto-filling job applications; runs blocking (not async)

## Key Service Responsibilities

| Service | Responsibility |
|---|---|
| `matcher.py` | 5-dimension scoring: skill 40%, experience 15%, domain 15%, location 10%, seniority 10% |
| `cv_parser.py` | Extracts skill clusters (programming, ml_ai, data, tools) from raw CV text |
| `resume_tailor.py` | Surgical vs. full resume rewrite based on match score |
| `cover_letter.py` | 250–350 word evidence-based cover letters |
| `application_automation.py` | Orchestrates recruiter workflow: decides which services to invoke |
| `jats_service.py` | AI-extracts fields from pasted JDs; duplicate detection |
| `analytics_service.py` | Aggregates metrics: conversion rates, skill frequency, salary distribution, overdue follow-ups |
| `credential_store.py` | Encrypted storage of job platform login credentials |

## Data Directory

`data/` (gitignored) stores:
- Uploaded resumes and parsed profiles
- `jats_tracker.db` (SQLite)
- `user_settings.json` (AI provider overrides)
- Browser profiles for automation (`browser-profiles/`)
