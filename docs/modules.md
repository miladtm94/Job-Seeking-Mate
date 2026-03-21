# Module Specification

This document defines production module boundaries and ownership.

## Backend modules

### 1. `candidate_intelligence`
Responsibilities:
- parse CVs (PDF/DOCX/TXT)
- normalize skills, tools, domains, achievements
- infer seniority and transferable strengths
- produce `CandidateProfile` vector payload

Interfaces:
- `POST /candidates/ingest`
- service: `CVParserService.parse()`

Dependencies:
- document parsers
- optional embedding provider

### 2. `job_discovery`
Responsibilities:
- source jobs from adapters (LinkedIn/Indeed/SEEK)
- query expansion with related role graph
- dedup and normalize records

Interfaces:
- `POST /jobs/search`
- service: `JobDiscoveryService.search()`

Dependencies:
- provider adapters
- cache + normalization pipeline

### 3. `job_matching`
Responsibilities:
- compute 0-100 fit score
- score rationale (matching + missing signals)
- probability estimate and apply recommendation

Interfaces:
- `POST /matching/score`
- service: `MatchingService.score()`

Dependencies:
- candidate/job schemas
- scoring config and weights

### 4. `artifact_generation`
Responsibilities:
- generate tailored resume structure
- generate role-specific cover letter
- enforce truthfulness and ATS-safe formatting

Interfaces:
- `POST /applications/generate`
- services: `ResumeTailoringService`, `CoverLetterService`

Dependencies:
- templates, prompt policies, section-ranking logic

### 5. `application_automation`
Responsibilities:
- prepare application payloads
- support manual assist, supervised auto-apply, batch queue
- track completion state transitions

Interfaces:
- future: `/applications/prepare`, `/applications/submit`, `/applications/batch`
- service: `ApplicationAutomationService`

Dependencies:
- browser automation adapters
- approval state machine

### 6. `tracking_analytics`
Responsibilities:
- maintain pipeline states (Saved/Applied/Interview/Rejected)
- compute metrics (conversion, interview rate, velocity)
- emit learning signals

Interfaces:
- future: `/dashboard/summary`, `/analytics/*`

Dependencies:
- event store, scheduled aggregation jobs

### 7. `agent_orchestration`
Responsibilities:
- coordinate specialized agents
- manage confidence and human approval boundaries
- execute orchestration plans for job cycles

Interfaces:
- internal orchestrator API
- optional external task API

Dependencies:
- worker queue
- model provider abstraction

## Frontend modules

### 1. `dashboard`
- pipeline overview
- KPIs and trend charts
- recent recommendations

### 2. `jobs`
- ranked job feed
- explainability panel (match/missing)
- save/ignore/apply actions

### 3. `applications`
- artifact preview and edit
- readiness checklist
- approval + submit controls

### 4. `settings`
- role/location/salary constraints
- provider credentials and limits
- automation mode controls

## Cross-cutting modules

### `auth`
- identity, session, permission model

### `audit`
- generation provenance
- operator approvals
- action timeline

### `observability`
- logs, metrics, traces
- alert boundaries

## Definition of done per module

- API contract documented
- unit tests for core logic
- integration tests for boundaries
- structured logs and typed errors
- security/privacy checks for PII-bearing paths
