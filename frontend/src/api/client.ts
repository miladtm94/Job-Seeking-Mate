const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

// Health
export function fetchHealth() {
  return request<{ status: string; service: string }>("/health");
}

// Candidates
export interface CandidateIngestRequest {
  name: string;
  email: string;
  raw_cv_text: string;
  preferred_roles: string[];
  locations: string[];
  salary_min?: number;
  salary_max?: number;
  work_type: string;
}

export interface CandidateProfile {
  candidate_id: string;
  name: string;
  email: string;
  skills: string[];
  domains: string[];
  seniority: string;
  years_experience: number;
  preferred_roles: string[];
  locations: string[];
  strengths: string[];
  skill_gaps: string[];
  summary: string;
}

export function ingestCandidate(data: CandidateIngestRequest) {
  return request<CandidateProfile>("/candidates/ingest", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function fetchCandidates() {
  return request<CandidateProfile[]>("/candidates/");
}

export function fetchCandidate(id: string) {
  return request<CandidateProfile>(`/candidates/${id}`);
}

// Jobs
export interface JobSearchRequest {
  query: string;
  locations: string[];
  remote_only: boolean;
  salary_min?: number;
  max_results: number;
}

export interface JobPosting {
  job_id: string;
  title: string;
  company: string;
  source: string;
  location: string;
  description: string;
  url: string;
  salary: string | null;
  match_score: number | null;
}

export interface JobSearchResponse {
  jobs: JobPosting[];
  total: number;
  query: string;
}

export function searchJobs(data: JobSearchRequest) {
  return request<JobSearchResponse>("/jobs/search", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// Matching
export interface MatchScoreResponse {
  job_id: string;
  match_score: number;
  key_matching_skills: string[];
  missing_skills: string[];
  recommendation: string;
  probability_of_success: number;
  explanation: string;
  fit_reasons: string[];
  improvement_suggestions: string[];
  breakdown: {
    skill_score: number;
    experience_score: number;
    domain_score: number;
    location_score: number;
    seniority_score: number;
  };
}

export interface BatchMatchResponse {
  results: MatchScoreResponse[];
  rejected_count: number;
}

// Applications
export interface ApplicationGenerateRequest {
  candidate_profile: {
    name: string;
    skills: string[];
    experience_summary: string;
    raw_cv_text?: string;
    seniority?: string;
  };
  job: {
    job_id?: string;
    title: string;
    company: string;
    description: string;
    location?: string;
    salary?: string;
    url?: string;
  };
  mode: string;
}

export interface ApplicationGenerateResponse {
  application_id: string;
  customized_resume: string;
  tailored_cover_letter: string;
  talking_points: string[];
  readiness_checklist: string[];
  match_score: number | null;
  mode: string;
  status: string;
}

export interface ApplicationRecord {
  application_id: string;
  candidate_id: string;
  job_id: string;
  company: string;
  role: string;
  match_score: number;
  status: string;
  mode: string;
  created_at: string;
  notes: string;
}

export function generateApplication(data: ApplicationGenerateRequest) {
  return request<ApplicationGenerateResponse>("/applications/generate", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function fetchApplications(candidateId?: string, status?: string) {
  const params = new URLSearchParams();
  if (candidateId) params.set("candidate_id", candidateId);
  if (status) params.set("status", status);
  const qs = params.toString();
  return request<{ applications: ApplicationRecord[]; total: number }>(
    `/applications/${qs ? `?${qs}` : ""}`
  );
}

export function fetchApplicationStats(candidateId?: string) {
  const params = candidateId ? `?candidate_id=${candidateId}` : "";
  return request<{ total: number; by_status: Record<string, number>; interview_rate: number; offers: number }>(
    `/applications/stats${params}`
  );
}

export function updateApplicationStatus(applicationId: string, status: string, notes = "") {
  return request<ApplicationRecord>(`/applications/${applicationId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, notes }),
  });
}

// Orchestrator
export interface FullCycleRequest {
  name: string;
  email: string;
  raw_cv_text: string;
  query?: string;
  preferred_roles: string[];
  locations: string[];
  salary_min?: number;
  remote_only: boolean;
  max_results: number;
  mode: string;
}

export function runFullCycle(data: FullCycleRequest) {
  return request<Record<string, unknown>>("/orchestrator/full-cycle", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function searchAndMatch(data: {
  query: string;
  locations: string[];
  remote_only: boolean;
  salary_min?: number;
  max_results: number;
  candidate: Record<string, unknown>;
}) {
  return request<Record<string, unknown>>("/orchestrator/search-match", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
