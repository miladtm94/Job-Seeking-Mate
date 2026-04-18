# Job-Seeking Mate

An AI-powered job application platform — evaluate your CV against any role, generate tailored cover letters, log and track every application, and get data-driven insights on your job search pipeline.

---

## Features

### Job Fit & Cover Letter
Upload your CV (PDF, .docx, or paste text) alongside a job description and get:
- **ATS Match Score** — how well your resume passes automated screening
- **Interview Probability** — likelihood of reaching the next stage
- **Keyword Coverage** — which JD keywords are present, partial, or missing
- **Strengths & Gaps** — specific areas where you stand out or fall short
- **Tailored Cover Letter** — professional body-only text, ready to copy-paste into any application form

### Application Tracker (JATS)
Paste any job description → AI extracts company, role, salary, skills, and location automatically → log the application. Track progress through a full event timeline: Applied → Screening → Interview → Offer / Rejected.

### Analytics
Conversion rates by stage, skill frequency across applications, salary distribution, platform breakdown, and overdue follow-up alerts — all in one dashboard.

### Settings
Switch AI provider and model at runtime via the UI — no restart required. Supports Gemini, Anthropic, OpenAI, LM Studio, and Ollama.

> **Job Hunting** (resume library + smart job search from Adzuna/Indeed + application generator) is currently under active development.

---

## Quick Start

**Prerequisites:** Python 3.11+ and Node.js 20+

```bash
git clone https://github.com/miladtm94/Job-Seeking-Mate.git
cd Job-Seeking-Mate

# Configure environment
cp .env.example backend/.env
# Edit backend/.env — set your AI provider and API key (see AI Setup below)

# Terminal 1 — backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — default login: `admin` / `jobmate` (change in `backend/.env`)

---

## AI Setup

All AI features require at least one provider. Set your choice in `backend/.env`:

### Option 1 — Google Gemini (free tier recommended)

Get a free API key at [aistudio.google.com](https://aistudio.google.com/apikey)

```env
AI_PROVIDER=gemini
AI_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your_key_here
```

### Option 2 — LM Studio (fully local, no API key)

```env
AI_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=your-loaded-model-id
```

Download [LM Studio](https://lmstudio.ai), load any model (Llama, Qwen, Phi), start the local server, and copy the model ID exactly as shown in the server panel.

### Option 3 — Anthropic Claude

```env
AI_PROVIDER=anthropic
AI_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=your_key_here
```

### Option 4 — OpenAI

```env
AI_PROVIDER=openai
AI_MODEL=gpt-4o
OPENAI_API_KEY=your_key_here
```

### Option 5 — Ollama (fully local, no API key)

```env
AI_PROVIDER=ollama
AI_MODEL=llama3.2
OLLAMA_BASE_URL=http://localhost:11434
```

> You can also switch provider and model live from the **Settings** page in the UI — no restart needed.

---

## Job Search APIs (optional)

Required only for the Job Hunting feature (currently in development).

| Provider | Free tier | Key |
|---|---|---|
| Adzuna | 1,000 req/day | [developer.adzuna.com](https://developer.adzuna.com) |
| JSearch (Indeed / LinkedIn) | 200 req/month | [RapidAPI — JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) |

```env
ADZUNA_APP_ID=your_app_id
ADZUNA_API_KEY=your_api_key
JSEARCH_API_KEY=your_rapidapi_key
```

---

## Tech Stack

| Layer | Technologies |
|---|---|
| Backend | FastAPI · Python 3.11 · Pydantic v2 · SQLite · PostgreSQL · SQLAlchemy 2 |
| Frontend | React 19 · TypeScript · Vite · TanStack Query · React Router 7 |
| AI | Gemini · Anthropic · OpenAI · LM Studio · Ollama (runtime-switchable) |
| Auth | JWT (python-jose) |
| Infra | Docker Compose (optional) |

---

## Pages

| Page | Route | Status |
|---|---|---|
| Dashboard | `/` | Working |
| Job Fit & Cover Letter | `/tailor` | Working |
| Log Application | `/log-application` | Working |
| My Applications | `/my-applications` | Working |
| Analytics | `/analytics` | Working |
| Settings | `/settings` | Working |
| Job Hunting | `/find-jobs` | Under development |

Interactive API docs: **http://localhost:8000/docs**

---

## Privacy & Data

- All application data is stored **locally** in `data/` — never sent to any external server except your chosen AI provider for generation tasks
- The `data/` directory is gitignored — your applications and resumes are never committed to version control
- API keys live only in `backend/.env`, which is also gitignored

---

## Roadmap

- [x] ATS match scoring and interview probability evaluation
- [x] Tailored cover letter generation (body-only, copy-paste ready)
- [x] Application tracker with AI-extracted fields and event timeline
- [x] Analytics dashboard with conversion rates and skill insights
- [x] Multi-provider AI support (Gemini, Claude, OpenAI, LM Studio, Ollama)
- [x] JWT authentication
- [ ] Job Hunting — smart search with resume library and application generator
- [ ] Email parsing for automatic status updates
- [ ] Export to CSV / Google Sheets
- [ ] Mobile-responsive layout

---

## License

Apache License 2.0
