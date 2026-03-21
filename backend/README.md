# Backend

FastAPI service implementing the job search intelligence pipeline.

## Package structure

```text
app/
├── agents/          # Plan→Act→Evaluate→Refine agent loop
│   ├── base.py      # BaseAgent protocol and AgentTask/AgentResult types
│   ├── specialists.py  # CVAgent, JobDiscoveryAgent, MatchingAgent, ApplicationAgent
│   └── orchestrator.py # Full-cycle and search-match pipeline coordination
├── api/v1/
│   └── endpoints/   # candidates, jobs, matching, applications, orchestrator, health
├── core/
│   ├── config.py    # Pydantic settings (reads .env)
│   ├── logging.py   # Structured logging setup
│   └── ai_client.py # Anthropic SDK wrapper with graceful fallback
├── db/
│   ├── base.py      # SQLAlchemy declarative base
│   ├── models.py    # ORM models (Candidate, Job, MatchScore, Application)
│   ├── session.py   # Engine and session factory
│   └── migrations/  # Alembic environment and version scripts
├── domain/models/   # Dataclasses (CandidateProfile, Job, Application, MatchResult)
├── repositories/    # Data access (CandidateRepository, JobRepository)
├── schemas/         # Pydantic v2 request/response schemas
├── services/
│   ├── cv_parser.py           # AI + heuristic CV analysis
│   ├── job_discovery.py       # Multi-source search with deduplication
│   ├── matcher.py             # 5-dimension scoring with AI explanations
│   ├── resume_tailor.py       # AI-powered resume customization
│   ├── cover_letter.py        # AI-powered cover letter generation
│   ├── application_automation.py  # Full application package builder
│   └── tracker.py             # Application lifecycle state machine
└── workers/
    ├── tasks.py     # Background task entrypoints
    └── queue.py     # Worker loop (Celery-ready)
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
pytest -q
```

## Lint + type-check

```bash
ruff check .
mypy app
```

## Migrations

```bash
alembic upgrade head        # apply all migrations
alembic revision --autogenerate -m "description"  # generate new migration
```

## Environment variables

See `../.env.example` for all options. Key variables:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables AI-powered CV parsing, matching explanations, resume tailoring, cover letters |
| `AI_MODEL` | Anthropic model ID (default: `claude-sonnet-4-20250514`) |
| `ADZUNA_APP_ID` / `ADZUNA_API_KEY` | Real job search results via Adzuna |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |

All AI features degrade gracefully to heuristics when no API key is configured.
