const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

const TOKEN_KEY = "jsm_token";

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const isFormData = options?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
  if (response.status === 401) {
    if (window.location.pathname !== "/login") {
      localStorage.removeItem(TOKEN_KEY);
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

// Auth
export function loginUser(username: string, password: string) {
  return request<{ access_token: string; token_type: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
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

export interface CandidateSkillClusters {
  programming: string[];
  ml_ai: string[];
  data: string[];
  tools: string[];
}

export interface CandidateProfile {
  candidate_id: string;
  name: string;
  email: string;
  skills: string[];
  skill_clusters: CandidateSkillClusters;
  domains: string[];
  industries: string[];
  seniority: string;
  years_experience: number;
  target_roles: string[];
  preferred_roles: string[];
  keywords: string[];
  search_queries: string[];
  locations: string[];
  salary_min?: number;
  work_type?: string;
  strengths: string[];
  skill_gaps: string[];
  summary: string;
  raw_cv_text?: string;
  filename?: string;
}

export function ingestCandidate(data: CandidateIngestRequest) {
  return request<CandidateProfile>("/candidates/ingest", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function ingestPdf(params: {
  file: File;
  name: string;
  email: string;
  preferred_roles: string;
  locations: string;
  salary_min?: number;
  work_type: string;
}) {
  const form = new FormData();
  form.append("file", params.file);
  const qs = new URLSearchParams({
    name: params.name,
    email: params.email,
    preferred_roles: params.preferred_roles,
    locations: params.locations,
    work_type: params.work_type,
    ...(params.salary_min ? { salary_min: String(params.salary_min) } : {}),
  });
  return request<CandidateProfile>(`/candidates/ingest-pdf?${qs}`, {
    method: "POST",
    headers: {},   // let browser set Content-Type with boundary
    body: form,
  });
}

export function fetchCandidates() {
  return request<CandidateProfile[]>("/candidates/");
}

export function fetchCandidate(id: string) {
  return request<CandidateProfile>(`/candidates/${id}`);
}

export function deleteCandidate(id: string) {
  return request<{ deleted: string }>(`/candidates/${id}`, { method: "DELETE" });
}

export interface SearchPlanResponse {
  queries: string[];
  location: string;
  location_hint: string;
  work_type: string;
  salary_min: number | null;
  max_jobs: number;
  min_score: number;
  date_range: number;
}

export function fetchSearchPlan(candidateId: string, platform: string) {
  return request<SearchPlanResponse>(`/candidates/${candidateId}/search-plan?platform=${platform}`);
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

export interface ScoredJob {
  job: JobPosting;
  match_score: number;
  key_matching_skills: string[];
  missing_skills: string[];
  recommendation: "strong_apply" | "apply" | "maybe" | "skip";
  explanation: string;
  fit_reasons: string[];
  breakdown: {
    skill_score: number;
    experience_score: number;
    domain_score: number;
    location_score: number;
    seniority_score: number;
  };
  best_candidate_id?: string | null;
  best_candidate_name?: string | null;
}

export interface SmartSearchResponse {
  scored_jobs: ScoredJob[];
  total_found: number;
  queries_used: string[];
}

export function smartSearchJobs(data: {
  candidate_id?: string;
  max_results?: number;
  remote_only?: boolean;
  locations?: string[];
  preferred_roles?: string[];
  salary_min?: number;
}) {
  return request<SmartSearchResponse>("/jobs/smart-search", {
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
  // Expert recruiter fields
  early_rejection?: boolean;
  rejection_reason?: string | null;
  technical_fit?: number;
  experience_fit?: number;
  ats_match?: number;
  shortlisting_probability?: "Low" | "Medium" | "High";
  ats_keywords?: Record<string, "present" | "partial" | "missing">;
  recruiter_risks?: string[];
  strategic_positioning?: string[];
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
  match_score?: number | null;
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
  // Expert recruiter workflow fields
  decision: "use_as_is" | "improve" | "new_resume_needed" | "do_not_apply";
  shortlisting_probability: "Low" | "Medium" | "High";
  strategic_positioning: string[];
  recruiter_risks: string[];
  ats_keywords: Record<string, "present" | "partial" | "missing">;
  resume_improvements: string[];
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

// ── JATS: Job Application Tracking System ────────────────────────────────────

export interface ExtractedJobData {
  role_title: string;
  company: string;
  location_city: string | null;
  location_country: string | null;
  remote_type: "remote" | "hybrid" | "onsite" | null;
  salary_min: number | null;
  salary_max: number | null;
  currency: string | null;
  required_skills: string[];
  preferred_skills: string[];
  seniority: string | null;
  employment_type: string | null;
  industry: string | null;
  // Extra fields from structured tracking-form paste
  platform: string | null;
  date_applied: string | null;
  contact_name: string | null;
  contact_email: string | null;
  job_url: string | null;
  notes: string | null;
  fit_score: number | null;
}

export interface LogApplicationRequest {
  company: string;
  role_title: string;
  platform: string;
  date_applied: string;
  status: string;
  location_city?: string | null;
  location_country?: string | null;
  remote_type?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  currency?: string;
  industry?: string | null;
  seniority?: string | null;
  employment_type?: string | null;
  description_raw?: string;
  resume_used?: string;
  cover_letter?: string;
  answers_text?: string;
  notes?: string;
  required_skills?: string[];
  preferred_skills?: string[];
  job_url?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  follow_up_date?: string | null;
  fit_score?: number | null;
}

export interface JATSSkill {
  skill_name: string;
  skill_type: string;
}

export interface JATSEvent {
  id: number;
  application_id: string;
  event_type: string;
  event_date: string;
  notes: string;
}

export interface JATSApplicationSummary {
  id: string;
  company: string;
  role_title: string;
  platform: string;
  date_applied: string;
  status: string;
  location_city: string | null;
  location_country: string | null;
  remote_type: string | null;
  salary_min: number | null;
  salary_max: number | null;
  currency: string;
  industry: string | null;
  seniority: string | null;
  employment_type: string | null;
  created_at: string;
  required_skills: string[];
  job_url: string | null;
  contact_name: string | null;
  follow_up_date: string | null;
  fit_score: number | null;
}

export interface JATSApplicationDetail extends JATSApplicationSummary {
  description_raw: string;
  notes: string;
  skills: JATSSkill[];
  events: JATSEvent[];
  resume_used: string;
  cover_letter: string;
  answers_text: string;
  contact_email: string | null;
}

export interface JATSListResponse {
  applications: JATSApplicationSummary[];
  total: number;
}

export function extractJobData(description: string) {
  return request<ExtractedJobData>("/jats/extract", {
    method: "POST",
    body: JSON.stringify({ job_description: description }),
  });
}

export function logApplication(data: LogApplicationRequest) {
  return request<JATSApplicationDetail>("/jats/applications", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function fetchJATSApplications(filters?: {
  status?: string;
  platform?: string;
  industry?: string;
  search?: string;
}) {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.platform) params.set("platform", filters.platform);
  if (filters?.industry) params.set("industry", filters.industry);
  if (filters?.search) params.set("search", filters.search);
  const qs = params.toString();
  return request<JATSListResponse>(`/jats/applications${qs ? `?${qs}` : ""}`);
}

export function fetchJATSApplication(id: string) {
  return request<JATSApplicationDetail>(`/jats/applications/${id}`);
}

export function updateJATSApplication(
  id: string,
  data: Partial<{
    company: string;
    role_title: string;
    date_applied: string;
    status: string;
    platform: string;
    location_city: string | null;
    location_country: string | null;
    remote_type: string | null;
    salary_min: number | null;
    salary_max: number | null;
    currency: string;
    industry: string | null;
    seniority: string | null;
    employment_type: string | null;
    notes: string;
    job_url: string | null;
    contact_name: string | null;
    contact_email: string | null;
    follow_up_date: string | null;
    fit_score: number | null;
    required_skills: string[];
    preferred_skills: string[];
  }>
) {
  return request<JATSApplicationDetail>(`/jats/applications/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteJATSApplication(id: string) {
  return request<{ deleted: string }>(`/jats/applications/${id}`, {
    method: "DELETE",
  });
}

export function addJATSEvent(
  id: string,
  data: { event_type: string; event_date: string; notes?: string }
) {
  return request<JATSEvent>(`/jats/applications/${id}/events`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateJATSEvent(
  id: string,
  eventId: number,
  data: { event_type: string; event_date: string; notes?: string }
) {
  return request<JATSEvent>(`/jats/applications/${id}/events/${eventId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteJATSEvent(id: string, eventId: number) {
  return request<{ deleted: number }>(`/jats/applications/${id}/events/${eventId}`, {
    method: "DELETE",
  });
}

export function checkDuplicate(company: string, role: string) {
  const qs = new URLSearchParams({ company, role });
  return request<{ exists: boolean; id?: string; status?: string; date_applied?: string }>(
    `/jats/check-duplicate?${qs}`
  );
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export interface AnalyticsOverview {
  total: number;
  by_status: Record<string, number>;
  applied_count: number;
  interview_count: number;
  offer_count: number;
  rejected_count: number;
  interview_rate: number;
  offer_rate: number;
  rejection_rate: number;
  response_rate: number;
  avg_response_days: number | null;
}

export interface AnalyticsData {
  overview: AnalyticsOverview;
  by_platform: { platform: string; count: number }[];
  by_industry: { industry: string; count: number }[];
  by_status: { status: string; count: number }[];
  by_remote_type: { remote_type: string; count: number }[];
  timeline: { date: string; count: number }[];
  skills_frequency: { skill: string; count: number }[];
  salary: {
    buckets: { range: string; count: number }[];
    avg_min: number | null;
    avg_max: number | null;
    currency: string | null;
  };
  seniority: { seniority: string; count: number }[];
  overdue_followups: {
    id: string;
    company: string;
    role_title: string;
    status: string;
    follow_up_date: string;
    days_overdue: number;
  }[];
  skills_by_outcome: {
    interviewed: { skill: string; count: number }[];
    applied_only: { skill: string; count: number }[];
    rejected: { skill: string; count: number }[];
  };
  fit_score: {
    avg: number | null;
    count: number;
    distribution: { range: string; count: number }[];
    by_status: { status: string; avg_score: number; count: number }[];
  };
}

export function fetchAnalytics() {
  return request<AnalyticsData>("/analytics/all");
}

// Saved credentials
export interface SavedCredential { platform: string; email: string; }

export function listCredentials() {
  return request<SavedCredential[]>("/credentials/");
}
export function getCredential(platform: string) {
  return request<SavedCredential>(`/credentials/${platform}`);
}
export function saveCredential(platform: string, email: string, password: string) {
  return request<SavedCredential>(`/credentials/${platform}`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}
export function deleteCredential(platform: string) {
  return request<{ deleted: boolean }>(`/credentials/${platform}`, { method: "DELETE" });
}
// Returns full credentials including password — used to pre-fill the apply form
export function getCredentialFull(platform: string) {
  return request<{ email: string; password: string }>(`/credentials/${platform}/full`);
}

// ── Settings ──────────────────────────────────────────────────────────────

export interface AppSettings {
  ai_provider:             string;
  ai_model:                string;
  ai_score_model:          string;
  lmstudio_base_url:       string;
  lmstudio_model:          string;
  ollama_base_url:         string;
  auto_apply_threshold:    number;
  match_reject_threshold:  number;
  has_anthropic:           boolean;
  has_openai:              boolean;
  has_gemini:              boolean;
  providers_available:     string[];
}

export function fetchSettings() {
  return request<AppSettings>("/settings");
}

export function updateSettings(data: Partial<Omit<AppSettings, "has_anthropic" | "has_openai" | "has_gemini" | "providers_available">>) {
  return request<{ ok: boolean; saved: string[] }>("/settings", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function pingAIProvider(provider?: string) {
  const path = provider ? `/settings/ping?provider=${provider}` : "/settings/ping";
  return request<{ ok: boolean; provider: string; model: string; error: string | null }>(path, {
    method: "POST",
  });
}

export function resetSettings() {
  return request<{ ok: boolean; message: string }>("/settings", { method: "DELETE" });
}

// ── Tailor (CV + JD → tailored resume & cover letter) ─────────────────────

export interface TailorRequest {
  cv_text: string;
  job_description: string;
  key_achievements?: string;
  target_industry?: string;
  career_narrative?: string;
  portfolio_links?: string;
  constraints?: string;
}

export interface TailorResponse {
  resume: string;
  cover_letter: string;
  strategic_notes: string;
}

export function generateTailored(data: TailorRequest) {
  return request<TailorResponse>("/tailor/generate", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export interface EvaluateResponse {
  ats_score: number;
  interview_probability: number;
  strengths: string[];
  gaps: string[];
  keyword_matches: Record<string, "present" | "partial" | "missing">;
  summary: string;
  recommendation: string;
}

export function parseTailorFile(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<{ text: string }>("/tailor/parse-file", {
    method: "POST",
    body: form,
  });
}

export function evaluateTailor(data: { cv_text: string; job_description: string }) {
  return request<EvaluateResponse>("/tailor/evaluate", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function generateCoverLetter(data: { cv_text: string; job_description: string }) {
  return request<{ cover_letter: string }>("/tailor/cover-letter", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
