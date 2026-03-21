# Product Roadmap

## Milestone 0 - Foundation (Week 1)

Scope:
- monorepo setup
- backend/frontend scaffolding
- Docker + local DX baseline
- CI lint/test/build checks

Exit criteria:
- services boot locally
- health endpoint operational
- frontend can call backend

## Milestone 1 - Candidate + Jobs Core (Weeks 2-3)

Scope:
- CV ingestion and profile extraction pipeline
- job source adapter abstraction + one provider integration
- canonical job model + dedup

Exit criteria:
- candidate profile generated from CV upload
- normalized jobs stored and queryable

## Milestone 2 - Explainable Match Scoring (Weeks 4-5)

Scope:
- weighted scoring engine
- missing-skill and rationale generation
- recommendations (Apply/Maybe/Skip)

Exit criteria:
- stable scoring endpoint with traceable rationale
- regression tests for scoring weights and thresholds

## Milestone 3 - Tailored Artifacts (Weeks 6-7)

Scope:
- resume tailoring pipeline
- role-specific cover letter generation
- artifact approval workflow in UI

Exit criteria:
- generated documents pass format and policy checks
- user can approve/reject per job before application prep

## Milestone 4 - Application Automation (Weeks 8-9)

Scope:
- manual assist mode
- supervised auto-apply mode (approval gate)
- batch queue mode with safe throttling

Exit criteria:
- application preparation works across at least one target board
- no direct submit without explicit user approval

## Milestone 5 - Tracking + Learning Loop (Weeks 10-12)

Scope:
- pipeline tracking and analytics dashboard
- feedback ingestion from outcomes
- recommendation adaptation using signals

Exit criteria:
- dashboard shows conversion metrics
- recommendation quality improves based on feedback policy

## Non-functional roadmap

- Security hardening: secret rotation, encryption strategy, access policy
- Reliability: retries, circuit breakers, queue backpressure controls
- Observability: tracing, alerting, SLOs for API and worker reliability
- Performance: caching, async IO boundaries, batch optimization

## Risks and mitigation

1. Provider policy/rate-limit constraints
- Mitigation: adapter isolation, strict request pacing, cached fallbacks

2. Hallucination in generated artifacts
- Mitigation: factual grounding from candidate profile only, policy validator

3. Matching bias and low precision
- Mitigation: weighted transparency, feedback-driven recalibration, offline eval set

4. Automation safety
- Mitigation: mandatory approval gate, action audit log, dry-run mode

## Prioritization principle

Always favor features that improve interview conversion and reduce manual workload while preserving factual integrity and user control.
