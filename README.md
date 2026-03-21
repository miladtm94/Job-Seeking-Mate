# Job-Seeking Mate

An autonomous, AI-powered job search and application system. It operates as a goal-driven agent pipeline — parsing your CV, discovering relevant jobs, scoring candidate-job fit with explainable reasoning, generating tailored application materials, and tracking your entire job search in one place.

---

## What It Does

The system runs a continuous Plan → Act → Evaluate → Refine loop across seven specialized agents:

| Agent | Responsibility |
|---|---|
| CV Intelligence | Extracts skills, domains, seniority, strengths, and gaps from raw CV text |
| Job Discovery | Searches multiple job boards, deduplicates, and normalizes listings |
| Matching & Scoring | Scores fit across 5 dimensions with explainable reasoning |
| Resume Tailoring | Rewrites resume sections to align with each job's requirements |
| Cover Letter | Generates personalized, role-specific cover letters |
| Application Automation | Packages artifacts and enforces human approval before submission |
| Tracking & Analytics | Manages application lifecycle with status transitions and metrics |

**Hard rule**: the system never applies to a job without explicit user approval.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Pydantic v2 |
| AI Engine | Anthropic API (graceful heuristic fallback when key not set) |
| Job Sources | Adzuna API (extensible to LinkedIn, Indeed, Seek) |
| Database | PostgreSQL via SQLAlchemy 2.x + Alembic migrations |
| Cache / Queue | Redis + Celery-compatible worker layer |
| Frontend | React 19 + TypeScript + Vite + TanStack Query + React Router |
| Containerization | Docker Compose (API + worker + frontend + Postgres + Redis) |
| CI | GitHub Actions (lint, type-check, test, build) |

---

## Repository Structure

```text
Job-Seeking-Mate/
├── backend/
│   ├── app/
│   │   ├── agents/          # Base agent loop + specialists + orchestrator
│   │   ├── api/v1/          # REST endpoints (candidates, jobs, matching, applications, orchestrator)
│   │   ├── core/            # Config, logging, AI client
│   │   ├── db/              # SQLAlchemy models, session, Alembic migrations
│   │   ├── domain/          # Domain dataclasses (candidate, job, application, match)
│   │   ├── repositories/    # Data access layer
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # Business logic (cv_parser, matcher, job_discovery, tracker…)
│   │   └── workers/         # Background task entrypoints
│   ├── tests/               # pytest test suite (29 tests)
│   ├── alembic.ini
│   └── pyproject.toml
├── frontend/
│   └── src/
│       ├── api/             # Typed API client
│       └── features/        # Dashboard, Profile, Jobs, Applications, Pipeline pages
├── infra/docker/            # Backend and frontend Dockerfiles
├── docs/                    # Architecture, module specs, roadmap, API spec
├── scripts/                 # Developer bootstrap
├── .github/workflows/       # CI pipeline
├── docker-compose.yml
└── Makefile
```

---

## Quick Start

### Prerequisites

- Docker + Docker Compose, or
- Python 3.11+ and Node.js 20+ (for local dev without Docker)

### 1. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```bash
# Required for AI features (CV parsing, matching explanations, resume tailoring, cover letters)
ANTHROPIC_API_KEY=your_key_here

# Optional: real job search results via Adzuna (free tier available)
ADZUNA_APP_ID=your_app_id
ADZUNA_API_KEY=your_api_key
```

All AI features fall back to deterministic heuristics if no API key is set, so the system works out of the box.

### 2. Run with Docker (recommended)

```bash
make up
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

### 3. Run locally without Docker

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Database migrations (requires running Postgres):

```bash
cd backend
alembic upgrade head
```

---

## API Reference

All endpoints are prefixed with `/api/v1`.

### Health
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service liveness check |

### Candidates
| Method | Path | Description |
|---|---|---|
| POST | `/candidates/ingest` | Parse CV text, extract profile, store candidate |
| GET | `/candidates/` | List all candidates |
| GET | `/candidates/{id}` | Get candidate by ID |

### Jobs
| Method | Path | Description |
|---|---|---|
| POST | `/jobs/search` | Search jobs across configured providers |
| GET | `/jobs/search` | Search jobs via query parameters |

### Matching
| Method | Path | Description |
|---|---|---|
| POST | `/matching/score` | Score a single candidate-job pair |
| POST | `/matching/batch` | Score a candidate against multiple jobs |

### Applications
| Method | Path | Description |
|---|---|---|
| POST | `/applications/generate` | Generate tailored resume + cover letter + talking points |
| GET | `/applications/` | List applications (filterable by candidate, status) |
| GET | `/applications/stats` | Interview rate, offer count, status breakdown |
| GET | `/applications/{id}` | Get application record |
| PATCH | `/applications/{id}/status` | Transition application status |

### Orchestrator (Full Pipeline)
| Method | Path | Description |
|---|---|---|
| POST | `/orchestrator/full-cycle` | End-to-end: parse CV → search → match → generate applications |
| POST | `/orchestrator/search-match` | Search jobs and score matches (no application generation) |

---

## Match Scoring

Each job is scored across five dimensions:

| Dimension | Weight | Description |
|---|---|---|
| Skill overlap | 50% | Required skills (40%) + preferred skills (10%) |
| Experience | 15% | Years of experience normalized against job seniority |
| Domain relevance | 15% | Candidate domain expertise vs. job description |
| Location | 10% | Location preference match (remote counts as match) |
| Seniority fit | 10% | Seniority level alignment between candidate and role |

Recommendations: `strong_apply` (≥75) · `apply` (≥60) · `maybe` (≥45) · `skip` (<45)

Each result includes a plain-language explanation, fit reasons, and improvement suggestions.

---

## Agent Architecture

Agents follow a **Plan → Act → Evaluate → Refine** loop:

```
AgentOrchestrator
├── CVAgent              → parse CV, extract structured profile
├── JobDiscoveryAgent    → search providers, deduplicate, normalize
├── MatchingAgent        → score all jobs, extract skills from descriptions
└── ApplicationAgent     → generate resume + cover letter + talking points
```

Each agent has:
- A `plan()` step that defines subtasks and success criteria
- An `act()` step that executes with retries
- An `evaluate()` step that checks confidence against a threshold
- A `refine()` step that adjusts the task payload before retrying

The orchestrator tracks all steps, errors, and confidence values across the pipeline.

---

## Application Status Lifecycle

```
saved → prepared → applied → interview → offer
  ↓         ↓          ↓           ↓
withdrawn withdrawn  rejected   rejected
```

Invalid transitions raise a 400 error. Status updates are logged with optional notes.

---

## Development

```bash
make test          # Run backend test suite (pytest)
make lint          # Ruff + mypy + TypeScript type-check
make format        # Auto-format backend code (ruff)
make install       # Install all backend and frontend dependencies
make migrate       # Apply database migrations
make up            # Start full stack with Docker
make down          # Stop and remove containers + volumes
```

### Running tests

```bash
cd backend
source .venv/bin/activate
pytest -q
```

29 tests covering services, agents, API endpoints, and status transitions.

---

## Configuration

All settings are in `.env` (see `.env.example` for all options):

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | _(empty)_ | Anthropic API key for AI features |
| `AI_MODEL` | `claude-sonnet-4-20250514` | Model used for all AI operations |
| `ADZUNA_APP_ID` | _(empty)_ | Adzuna job search app ID |
| `ADZUNA_API_KEY` | _(empty)_ | Adzuna job search API key |
| `DATABASE_URL` | local postgres | PostgreSQL connection string |
| `REDIS_URL` | local redis | Redis connection string |
| `AUTO_APPLY_THRESHOLD` | `75` | Minimum score for auto mode (unused unless explicitly enabled) |
| `MATCH_REJECT_THRESHOLD` | `60` | Below this score, jobs are filtered from results |
| `MAX_JOBS_PER_SEARCH` | `50` | Maximum jobs fetched per search |

---

## Design Principles

- **Truthfulness first** — the system never fabricates qualifications or experience
- **Human in the loop** — no job is applied to without explicit user confirmation
- **Explainability** — every match score has a breakdown and plain-language explanation
- **Graceful degradation** — all AI features have heuristic fallbacks; the system works without API keys
- **Quality over volume** — precision targeting beats mass application

---

## Roadmap

- [ ] LinkedIn and Seek job source adapters
- [ ] Playwright-based browser automation for form pre-fill
- [ ] Persistent DB-backed application tracking (currently in-memory)
- [ ] User authentication (JWT)
- [ ] Email notification on status changes
- [ ] Interview preparation question generator
- [ ] Learning loop: adapt match weights from interview outcomes
- [ ] Mobile-responsive UI polish

See [docs/roadmap.md](./docs/roadmap.md) for detailed milestones.

---

## License

Apache License 2.0

See [LICENSE](./LICENSE) for the full text.

> **Why Apache 2.0?** It provides explicit patent protection, requires attribution in derivatives, and is the standard for serious open-source infrastructure projects. Unlike MIT, it prevents patents from being weaponized against users of this software.
