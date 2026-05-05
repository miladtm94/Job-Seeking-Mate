# Job-Seeking Mate

Job-Seeking Mate is a local-first job search assistant. It helps you evaluate roles, tailor application material, track submissions, and understand your job search pipeline from one dashboard.

## What It Does

- Scores how well a resume matches a job description.
- Highlights matched and missing keywords.
- Generates tailored cover letter text.
- Logs applications with company, role, salary, location, skills, notes, and status.
- Tracks each application from applied through interviews, offers, or rejection.
- Shows analytics for conversion rates, fit scores, salaries, platforms, and follow-ups.
- Supports multiple AI providers, including Gemini, Anthropic, OpenAI, LM Studio, and Ollama.

## Main Pages

| Page | Purpose |
|---|---|
| Dashboard | Overview of your job search activity |
| Job Fit & Cover Letter | Compare a resume with a job description and generate cover letter text |
| Log Application | Save a new application with AI-extracted details |
| My Applications | Review, edit, and update application progress |
| Analytics | Track outcomes, salaries, platforms, skills, and follow-ups |
| Settings | Choose the AI provider and model |
| Job Hunting | Search and review jobs from supported platforms |

## Quick Start

Requirements:

- Docker Desktop or Docker Engine with Docker Compose
- An API key for your chosen AI provider, unless using LM Studio or Ollama locally

```bash
git clone https://github.com/miladtm94/Job-Seeking-Mate.git
cd Job-Seeking-Mate
cp .env.example .env
make up
```

Then open:

- App: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

Default login:

- Username: `admin`
- Password: `jobmate`

Change the default credentials in `.env` before regular use.

## AI Configuration

Set one provider in `.env`.

Gemini:

```env
AI_PROVIDER=gemini
AI_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your_key_here
```

OpenAI:

```env
AI_PROVIDER=openai
AI_MODEL=gpt-4o
OPENAI_API_KEY=your_key_here
```

Anthropic:

```env
AI_PROVIDER=anthropic
AI_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=your_key_here
```

LM Studio:

```env
AI_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1
LMSTUDIO_MODEL=your-loaded-model-id
```

Ollama:

```env
AI_PROVIDER=ollama
AI_MODEL=llama3.2
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

You can also change the active provider and model from the Settings page.

## Common Commands

```bash
make up          # build and start the app
make stop        # stop running containers
make start       # start existing containers
make restart     # restart services
make logs        # follow service logs
make status      # show running services
make down        # remove containers, keeping volume data
make rebuild     # rebuild images and start again
```

## Manual Development

Run the backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

## Tech Stack

| Area | Tools |
|---|---|
| Backend | FastAPI, Python 3.11, Pydantic, SQLAlchemy |
| Frontend | React, TypeScript, Vite, TanStack Query, React Router |
| Data | SQLite for local use, PostgreSQL via Docker |
| AI | Gemini, Anthropic, OpenAI, LM Studio, Ollama |
| Auth | JWT |
| Infra | Docker Compose |

## Privacy

- Application data is stored locally in `data/`.
- API keys are stored in `.env`.
- `data/` and `.env` are ignored by Git.
- AI features send only the requested task content to the selected provider.

## License

Apache License 2.0
