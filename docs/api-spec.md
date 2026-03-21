# API Specification (v1)

Base path: `/api/v1`

## Health

### `GET /health`
Response:
```json
{
  "status": "ok",
  "service": "job-seeking-mate-api"
}
```

## Candidate Ingestion

### `POST /candidates/ingest`
Request:
```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "raw_cv_text": "...",
  "preferred_roles": ["ML Engineer", "AI Engineer"],
  "locations": ["Sydney", "Remote"]
}
```

Response:
```json
{
  "candidate_id": "cand_123",
  "skills": ["Python", "FastAPI", "TensorFlow"],
  "domains": ["Machine Learning", "Signal Processing"],
  "seniority": "senior",
  "strengths": ["Model deployment", "Cross-functional collaboration"],
  "skill_gaps": ["Kubernetes"]
}
```

## Job Search

### `POST /jobs/search`
Request:
```json
{
  "query": "ML Engineer",
  "locations": ["Sydney", "Remote"],
  "sources": ["linkedin", "indeed", "seek"],
  "remote_only": false
}
```

Response:
```json
{
  "jobs": [
    {
      "job_id": "job_123",
      "title": "Machine Learning Engineer",
      "company": "Acme AI",
      "source": "linkedin",
      "location": "Sydney",
      "description": "...",
      "url": "https://example.com/job"
    }
  ]
}
```

## Match Scoring

### `POST /matching/score`
Request:
```json
{
  "candidate": {
    "skills": ["Python", "FastAPI", "TensorFlow"],
    "years_experience": 7,
    "locations": ["Sydney", "Remote"]
  },
  "job": {
    "title": "ML Engineer",
    "required_skills": ["Python", "TensorFlow", "SQL"],
    "preferred_skills": ["AWS"],
    "location": "Sydney"
  }
}
```

Response:
```json
{
  "match_score": 82,
  "key_matching_skills": ["Python", "TensorFlow"],
  "missing_skills": ["SQL"],
  "recommendation": "apply",
  "probability_of_success": 0.67,
  "explanation": "Strong core skill overlap and location match."
}
```

## Artifact Generation

### `POST /applications/generate`
Request:
```json
{
  "candidate_profile": {
    "name": "Jane Doe",
    "skills": ["Python", "FastAPI", "TensorFlow"],
    "experience_summary": "..."
  },
  "job": {
    "title": "ML Engineer",
    "company": "Acme AI",
    "description": "..."
  }
}
```

Response:
```json
{
  "customized_resume": "...",
  "tailored_cover_letter": "...",
  "readiness_checklist": [
    "Facts verified against source CV",
    "Role-specific keywords included",
    "Human approval required before submission"
  ]
}
```
