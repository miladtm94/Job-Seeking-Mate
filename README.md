# Job-Seeking Mate

An AI-powered **Job Application Tracking System (JATS)** combined with a smart job search agent. It helps you log, track, and analyse every job application — and optionally automates the search, scoring, and application-material generation pipeline.

---

## What It Does

### Job Application Tracker (JATS)
The core daily-use feature. For every job you apply to:

1. **Paste the job description** → AI extracts company, role, salary, skills, industry, location, and work type automatically
2. **Review / edit** the pre-filled form, then save
3. **Track** each application through its lifecycle (Applied → Interview → Offer / Rejected)
4. **Add timeline events** (phone screen, interview dates, rejection, offer date) with notes
5. **Analytics dashboard** — conversion rates, skill frequency, salary distribution, platform breakdown, weekly activity charts

### AI Job Search Pipeline (optional)
Runs a full Plan → Act → Evaluate loop:
- Parses your CV (PDF or text paste) into a structured profile
- Searches Adzuna / JSearch / Indeed for matching roles
- Scores every job across 5 dimensions with explainable reasoning
- Generates tailored resumes, cover letters, and talking points
- **Hard rule: never applies without explicit user approval**

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Pydantic v2 |
| Application DB | SQLite (JATS tracker — zero-config, file-based) |
| AI Engine | Anthropic / OpenAI / Ollama (graceful fallback to heuristics) |
| Job Sources | Adzuna API · JSearch/RapidAPI (aggregates Indeed, LinkedIn, Glassdoor) |
| Infrastructure DB | PostgreSQL via SQLAlchemy 2.x (optional, used by agent pipeline) |
| Frontend | React 19 + TypeScript + Vite + TanStack Query + React Router |
| Containerisation | Docker Compose (API + worker + frontend + Postgres + Redis) |

---

## Repository Structure

```text
Job-Seeking-Mate/
├── backend/
│   └── app/
│       ├── api/v1/endpoints/   # REST endpoints
│       │   ├── candidates.py   # CV ingestion
│       │   ├── jobs.py         # Job search + smart search
│       │   ├── matching.py     # Candidate–job scoring
│       │   ├── applications.py # Application generation (AI pipeline)
│       │   ├── jats.py         # JATS tracker CRUD + NLP extract
│       │   ├── analytics.py    # Analytics aggregations
│       │   └── orchestrator.py # Full pipeline orchestrator
│       ├── core/               # Config, logging, AI client (Ollama/OpenAI/Anthropic)
│       ├── db/
│       │   ├── jats_db.py      # SQLite engine → data/jats.db
│       │   ├── jats_models.py  # ORM: applications, skills, materials, events
│       │   ├── models.py       # PostgreSQL models (agent pipeline)
│       │   └── migrations/     # Alembic migration scripts
│       ├── schemas/
│       │   ├── jats.py         # JATS request/response schemas
│       │   ├── job.py          # Job search schemas
│       │   ├── candidate.py    # Candidate profile schemas
│       │   └── application.py  # Application generation schemas
│       └── services/
│           ├── jats_service.py       # JATS CRUD + NLP extraction pipeline
│           ├── analytics_service.py  # Analytics queries
│           ├── cv_parser.py          # CV → structured profile
│           ├── matcher.py            # Multi-dimensional job scoring
│           └── job_discovery.py      # Multi-source job search
├── frontend/
│   └── src/
│       ├── api/client.ts             # Typed API client
│       └── features/
│           ├── dashboard/            # Overview + metrics
│           ├── profile/              # CV upload + profile display
│           ├── jobs/                 # Smart job search + application generator
│           ├── tracker/              # Log Application + My Applications pages
│           ├── analytics/            # Charts + insights dashboard
│           └── pipeline/             # Full pipeline orchestrator UI
├── data/                             # Runtime data — gitignored, never committed
│   ├── jats.db                       # SQLite: all your application records (auto-created)
│   ├── profiles.json                 # Your parsed CV profile (auto-created)
│   ├── logs/                         # JSON backup of every logged application
│   ├── resumes/                      # Drop your PDF resumes here
│   └── covers/                       # Drop cover letter drafts here
├── docs/                             # Architecture, module specs, API spec, roadmap
├── infra/docker/                     # Backend and frontend Dockerfiles
├── .env.example                      # All configurable variables with defaults
└── docker-compose.yml
```

---

## Data Persistence

> **Your application data is saved locally and survives restarts.**

| What | Where | Backed up |
|---|---|---|
| All application records | `data/jats.db` (SQLite) | Yes — auto |
| Your CV profile | `data/profiles.json` | Yes — auto |
| Per-application JSON backup | `data/logs/jats_<id>.json` | Yes — auto |

The SQLite database (`data/jats.db`) is created automatically the first time the backend starts. Every time you log an application through the UI or API, it is written to this file **immediately and permanently** — restarting the server does not lose any data.

**None of these files are ever pushed to GitHub.** The `data/` folder is gitignored to protect your personal data. The `.gitkeep` placeholder files in each subdirectory simply ensure the folder structure exists when you clone a fresh copy.

### Backing up your data
```bash
# Copy your database to a safe location
cp data/jats.db ~/Backups/jats-$(date +%Y%m%d).db

# Or export all applications as JSON
curl -s http://localhost:8000/api/v1/jats/applications | python3 -m json.tool > my_applications.json
```

---

## Quick Start

### Prerequisites

- Python 3.11+ and Node.js 20+

### 1. Clone and configure

```bash
git clone git@github.com:miladtm94/Job-Seeking-Mate.git
cd Job-Seeking-Mate
cp .env.example .env
```

Edit `.env` — set at minimum one AI provider:

```bash
# Option A: Anthropic (recommended)
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
AI_MODEL=claude-haiku-4-5-20251001   # cheapest, fast enough

# Option B: OpenAI
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini

# Option C: Local Ollama (free, no API key)
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
AI_MODEL=llama3.2
```

> All AI features fall back gracefully to heuristics if no provider is configured — you can use the tracker without any AI key.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

The SQLite database is created automatically at `data/jats.db` on first start.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

---

## Navigation

| Page | URL | What it does |
|---|---|---|
| Dashboard | `/` | System status, profile summary, application metrics |
| Profile | `/profile` | Upload PDF or paste CV text for AI parsing |
| Job Search | `/jobs` | AI-powered smart search + application material generator |
| **Log Application** | `/log-application` | Paste a job description → AI extracts fields → save to tracker |
| **My Applications** | `/my-applications` | Full tracker: filter, update status, event timeline |
| **Analytics** | `/analytics` | Charts: conversion rates, platform, skills, salary, timeline |
| Pipeline | `/pipeline` | Full automated pipeline (parse → search → score → generate) |

---

## API Reference

All endpoints are prefixed with `/api/v1`. Interactive docs at **http://localhost:8000/docs**.

### JATS Tracker

| Method | Path | Description |
|---|---|---|
| POST | `/jats/extract` | NLP-extract structured fields from a raw job description |
| POST | `/jats/applications` | Log a new application with full metadata |
| GET | `/jats/applications` | List applications (filter: `status`, `platform`, `industry`, `search`) |
| GET | `/jats/applications/{id}` | Get full application detail including skills + events |
| PATCH | `/jats/applications/{id}` | Update status, salary, notes, and other fields |
| DELETE | `/jats/applications/{id}` | Delete an application record |
| POST | `/jats/applications/{id}/events` | Add a timeline event (interview, rejection, offer…) |
| GET | `/jats/applications/{id}/events` | Get all events for an application |

### Analytics

| Method | Path | Description |
|---|---|---|
| GET | `/analytics/all` | Full analytics payload (single request — use this) |
| GET | `/analytics/overview` | Total, conversion rates, funnel counts |
| GET | `/analytics/platforms` | Applications by platform |
| GET | `/analytics/industries` | Applications by industry |
| GET | `/analytics/statuses` | Applications by status |
| GET | `/analytics/timeline` | Applications per week/month |
| GET | `/analytics/skills` | Most required skills frequency |
| GET | `/analytics/salary` | Salary distribution and averages |

### Job Search & Matching

| Method | Path | Description |
|---|---|---|
| POST | `/jobs/search` | Search jobs across configured providers |
| POST | `/jobs/smart-search` | Profile-driven search: auto-queries + scores every result |
| POST | `/matching/score` | Score a single candidate–job pair |
| POST | `/matching/batch` | Score a candidate against multiple jobs |

### Candidates & Applications

| Method | Path | Description |
|---|---|---|
| POST | `/candidates/ingest` | Parse CV text → structured profile |
| POST | `/candidates/ingest-pdf` | Upload PDF resume → structured profile |
| GET | `/candidates/` | List profiles |
| POST | `/applications/generate` | Generate tailored resume + cover letter + talking points |
| GET | `/applications/stats` | Interview rate, offer count, status breakdown |
| PATCH | `/applications/{id}/status` | Transition application status |

---

## Application Status Lifecycle

```
saved ──→ applied ──→ interview ──→ offer
  │           │            │
  └──→ withdrawn    rejected    rejected
```

Status transitions are enforced — invalid moves return a 400 error. Every status change is automatically logged as a timeline event.

---

## Match Scoring

Each job is scored across five dimensions (100-point scale):

| Dimension | Weight | How |
|---|---|---|
| Skill overlap | 50% | Required skills (40%) + preferred (10%) |
| Experience | 15% | Years normalised against role seniority |
| Domain relevance | 15% | Candidate domains vs. job description keywords |
| Location | 10% | Location preference (remote = always match) |
| Seniority fit | 10% | Level alignment |

Recommendations: `strong_apply` (≥75) · `apply` (≥60) · `maybe` (≥45) · `skip` (<45)

---

## Configuration

All settings live in `.env`. See `.env.example` for the full list.

| Variable | Default | Description |
|---|---|---|
| `AI_PROVIDER` | `ollama` | `anthropic` / `openai` / `ollama` |
| `ANTHROPIC_API_KEY` | _(empty)_ | Required if using Anthropic |
| `OPENAI_API_KEY` | _(empty)_ | Required if using OpenAI |
| `AI_MODEL` | `llama3.2` | Model name for the selected provider |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `ADZUNA_APP_ID` / `ADZUNA_API_KEY` | _(empty)_ | Real job results via Adzuna (free tier available) |
| `JSEARCH_API_KEY` | _(empty)_ | RapidAPI key — aggregates Indeed, LinkedIn, Glassdoor |
| `DATABASE_URL` | local postgres | Only needed for the agent pipeline (not JATS tracker) |
| `AUTO_APPLY_THRESHOLD` | `75` | Minimum match score for auto-mode (pipeline only) |

---

## Roadmap

- [x] Persistent, file-based application tracking (SQLite JATS database)
- [x] NLP extraction from job descriptions
- [x] Analytics dashboard with charts
- [x] Manual application logging with event timeline
- [x] JSON backup for every logged application
- [ ] LinkedIn and Seek job source adapters
- [ ] Resume file management (upload + version tracking)
- [ ] Email parsing for automatic status updates (interview invites, rejections)
- [ ] Resume–job match scoring from within the tracker
- [ ] Interview preparation question generator
- [ ] Export applications to CSV / Google Sheets
- [ ] User authentication (multi-user support)
- [ ] Mobile-responsive UI polish

---

## Design Principles

- **Your data stays local** — application records never leave your machine unless you choose
- **Human in the loop** — no job is applied to without explicit user confirmation
- **Graceful degradation** — all AI features have heuristic fallbacks; tracker works without any API key
- **Explainability** — every match score has a breakdown and plain-language explanation
- **Zero-config storage** — SQLite, no database server required for the tracker

---

## License

Apache License 2.0
