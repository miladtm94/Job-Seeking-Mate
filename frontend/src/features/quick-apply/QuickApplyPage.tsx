/**
 * Quick Apply — paste any job URL you found yourself (Indeed AU, Seek, LinkedIn, company site)
 * and let the AI fill the application using your tailored resume and cover letter.
 *
 * Flow:
 *   1. Paste job URL  → platform auto-detected
 *   2. Fill job title + company + description (paste from the posting)
 *   3. Pick which resume to use from your library
 *   4. Generate tailored resume + cover letter
 *   5. Review docs → click "Apply with AI"
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchCandidates, generateApplication } from "../../api/client";
import type { ApplicationGenerateResponse, CandidateProfile } from "../../api/client";
import { AutoApplyPanel } from "../auto-apply/AutoApplyPanel";
import type { JobForApply } from "../auto-apply/AutoApplyPanel";

// ── platform detection (mirrors AutoApplyPanel) ───────────────────────────────

function detectPlatformLabel(url: string): string {
  if (url.includes("indeed"))   return "Indeed";
  if (url.includes("linkedin")) return "LinkedIn";
  if (url.includes("seek"))     return "Seek";
  try { return new URL(url).hostname; }
  catch { return "Company website"; }
}

function platformIcon(url: string): string {
  if (url.includes("indeed"))   return "🔵";
  if (url.includes("linkedin")) return "🔗";
  if (url.includes("seek"))     return "🟢";
  return "🏢";
}

// ── resume selector ───────────────────────────────────────────────────────────

function ResumeSelector({
  profiles,
  selectedId,
  onSelect,
}: {
  profiles: CandidateProfile[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  if (profiles.length === 0) {
    return (
      <div style={{ padding: "14px 16px", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)", borderRadius: 8, fontSize: "0.88rem", color: "var(--red)" }}>
        No resumes uploaded yet. Go to <strong>Find Jobs</strong> to upload your PDF resume first.
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {profiles.map((p) => {
        const label = p.filename || p.name || p.candidate_id.slice(0, 8);
        const active = p.candidate_id === selectedId;
        return (
          <div
            key={p.candidate_id}
            onClick={() => onSelect(p.candidate_id)}
            style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "12px 14px",
              borderRadius: 8,
              border: `2px solid ${active ? "var(--accent)" : "var(--border)"}`,
              background: active ? "rgba(203,95,54,0.07)" : "transparent",
              cursor: "pointer",
              transition: "border-color 0.15s, background 0.15s",
            }}
          >
            <div style={{
              width: 18, height: 18, borderRadius: "50%",
              border: `2px solid ${active ? "var(--accent)" : "var(--border)"}`,
              background: active ? "var(--accent)" : "transparent",
              flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              {active && <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#fff" }} />}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: "0.9rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {label}
              </div>
              <div className="muted" style={{ fontSize: "0.78rem" }}>
                {p.seniority} · {p.years_experience}y exp · {p.skills.slice(0, 4).join(", ")}
                {p.skills.length > 4 && ` +${p.skills.length - 4}`}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── generated docs preview ────────────────────────────────────────────────────

function DocsPreview({ result }: { result: ApplicationGenerateResponse }) {
  const decisionLabel =
    result.decision === "use_as_is"        ? { text: "Resume: Use As-Is",            cls: "tag-strong_apply" }
    : result.decision === "improve"        ? { text: "Resume: Surgical Improvements", cls: "tag-apply"        }
    : result.decision === "new_resume_needed" ? { text: "Full New Resume Generated",  cls: "tag-maybe"        }
    : { text: "Do Not Apply", cls: "tag-skip" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className={`tag ${decisionLabel.cls}`}>{decisionLabel.text}</span>
        <span className={`tag ${result.shortlisting_probability === "High" ? "tag-strong_apply" : result.shortlisting_probability === "Medium" ? "tag-apply" : "tag-maybe"}`}>
          Shortlisting: {result.shortlisting_probability}
        </span>
      </div>

      {result.strategic_positioning.length > 0 && (
        <details open>
          <summary style={{ fontWeight: 600, cursor: "pointer", fontSize: "0.9rem" }}>Strategic Positioning</summary>
          <ul style={{ marginTop: 8, paddingLeft: 20 }}>
            {result.strategic_positioning.map((s, i) => <li key={i} style={{ fontSize: "0.88rem", marginBottom: 4 }}>{s}</li>)}
          </ul>
        </details>
      )}

      {result.customized_resume && (
        <details>
          <summary style={{ fontWeight: 600, cursor: "pointer", fontSize: "0.9rem" }}>
            {result.decision === "improve" ? "Resume Surgical Improvements" : "Tailored Resume"}
          </summary>
          <pre style={{ marginTop: 8, whiteSpace: "pre-wrap", fontSize: "0.8rem", lineHeight: 1.6, maxHeight: 300, overflowY: "auto", background: "rgba(0,0,0,0.15)", padding: 12, borderRadius: 8 }}>
            {result.customized_resume}
          </pre>
        </details>
      )}

      <details open>
        <summary style={{ fontWeight: 600, cursor: "pointer", fontSize: "0.9rem" }}>Cover Letter</summary>
        <pre style={{ marginTop: 8, whiteSpace: "pre-wrap", fontSize: "0.85rem", lineHeight: 1.7, maxHeight: 280, overflowY: "auto", background: "rgba(0,0,0,0.15)", padding: 12, borderRadius: 8 }}>
          {result.tailored_cover_letter}
        </pre>
      </details>

      {result.talking_points.length > 0 && (
        <details>
          <summary style={{ fontWeight: 600, cursor: "pointer", fontSize: "0.9rem" }}>Interview Talking Points</summary>
          <ul style={{ marginTop: 8, paddingLeft: 20 }}>
            {result.talking_points.map((t, i) => <li key={i} style={{ fontSize: "0.88rem", marginBottom: 4 }}>{t}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}

// ── step indicator ────────────────────────────────────────────────────────────

const STEP_LABELS = ["Job details", "Choose resume", "Generate docs", "Apply"];

function Steps({ active }: { active: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: 28 }}>
      {STEP_LABELS.map((label, i) => {
        const done    = i < active;
        const current = i === active;
        return (
          <div key={label} style={{ display: "flex", alignItems: "center", flex: i < STEP_LABELS.length - 1 ? 1 : 0 }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}>
              <div style={{
                width: 30, height: 30, borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 700, fontSize: "0.8rem",
                background: done ? "var(--green)" : current ? "var(--accent)" : "var(--border)",
                color: done || current ? "#fff" : "var(--muted)",
              }}>
                {done ? "✓" : i + 1}
              </div>
              <span style={{ fontSize: "0.72rem", fontWeight: current ? 700 : 400, color: current ? "var(--accent)" : done ? "var(--green)" : "var(--muted)", whiteSpace: "nowrap" }}>
                {label}
              </span>
            </div>
            {i < STEP_LABELS.length - 1 && (
              <div style={{ flex: 1, height: 2, background: done ? "var(--green)" : "var(--border)", margin: "0 8px", marginBottom: 18 }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export function QuickApplyPage() {
  const candidatesQuery = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });
  const profiles = candidatesQuery.data ?? [];

  // Step 1 — job details
  const [jobUrl, setJobUrl]           = useState("");
  const [jobTitle, setJobTitle]       = useState("");
  const [jobCompany, setJobCompany]   = useState("");
  const [jobDesc, setJobDesc]         = useState("");

  // Step 2 — resume
  const [selectedId, setSelectedId]   = useState("");

  // Step 3 — generated docs
  const [appResult, setAppResult]     = useState<ApplicationGenerateResponse | null>(null);

  // Step 4 — apply panel
  const [showApply, setShowApply]     = useState(false);

  const selectedProfile = profiles.find(p => p.candidate_id === selectedId) ?? profiles[0];

  // Auto-select first profile
  if (profiles.length > 0 && !selectedId) setSelectedId(profiles[0].candidate_id);

  const generateMutation = useMutation({
    mutationFn: generateApplication,
    onSuccess: (data) => setAppResult(data),
  });

  const handleGenerate = () => {
    if (!selectedProfile || !jobUrl || !jobTitle) return;
    setAppResult(null);
    generateMutation.mutate({
      candidate_profile: {
        name:               selectedProfile.name,
        skills:             selectedProfile.skills,
        experience_summary: selectedProfile.summary,
        seniority:          selectedProfile.seniority,
        raw_cv_text:        selectedProfile.raw_cv_text ?? "",
      },
      job: {
        job_id:      `manual_${Date.now()}`,
        title:       jobTitle,
        company:     jobCompany || "Unknown",
        description: jobDesc,
        location:    "",
        url:         jobUrl,
      },
      mode: "manual",
      match_score: null,
    });
  };

  const urlOk    = jobUrl.startsWith("http");
  const titleOk  = jobTitle.trim().length > 0;
  const profileOk = !!selectedProfile;
  const step     = !urlOk || !titleOk ? 0 : !profileOk ? 1 : !appResult ? 2 : 3;

  const jobForApply: JobForApply = {
    url:         jobUrl,
    title:       jobTitle,
    company:     jobCompany,
    description: jobDesc,
  };

  return (
    <div className="page">
      <h2>Quick Apply</h2>
      <p className="muted" style={{ maxWidth: 680, lineHeight: 1.7 }}>
        Found a job on Indeed AU, Seek, LinkedIn, or a company's own careers page?
        Paste the URL here — no need to go through the job search tool.
        The AI will open the page in a real browser, fill the form using your tailored resume, and only ask when it needs your input.
      </p>

      <div className="grid two-col" style={{ marginTop: 24, alignItems: "flex-start", gap: 24 }}>

        {/* Left column: inputs */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Steps active={step} />

          {/* Step 1: Job URL + details */}
          <section className="panel">
            <h3 style={{ marginBottom: 4 }}>Step 1 — Job details</h3>
            <p className="muted" style={{ fontSize: "0.85rem", marginBottom: 16 }}>
              Copy the URL from your browser's address bar while viewing the job posting.
            </p>

            <div className="form" style={{ gap: 14 }}>
              <label>
                Job URL <span style={{ color: "var(--red)" }}>*</span>
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                  <input
                    type="url"
                    value={jobUrl}
                    onChange={(e) => setJobUrl(e.target.value.trim())}
                    placeholder="https://au.indeed.com/viewjob?jk=… or https://seek.com.au/job/…"
                    style={{ flex: 1 }}
                  />
                  {urlOk && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 12px", background: "rgba(0,0,0,0.15)", borderRadius: 6, whiteSpace: "nowrap", fontSize: "0.82rem" }}>
                      <span>{platformIcon(jobUrl)}</span>
                      <span className="muted">{detectPlatformLabel(jobUrl)}</span>
                    </div>
                  )}
                </div>
              </label>

              <div className="form-row">
                <label style={{ flex: 2 }}>
                  Job title <span style={{ color: "var(--red)" }}>*</span>
                  <input
                    type="text"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    placeholder="Senior Software Engineer"
                    style={{ marginTop: 6 }}
                  />
                </label>
                <label style={{ flex: 1 }}>
                  Company
                  <input
                    type="text"
                    value={jobCompany}
                    onChange={(e) => setJobCompany(e.target.value)}
                    placeholder="Atlassian"
                    style={{ marginTop: 6 }}
                  />
                </label>
              </div>

              <label>
                Job description
                <span className="muted" style={{ fontWeight: 400, marginLeft: 6 }}>(paste from the posting — improves tailoring quality)</span>
                <textarea
                  value={jobDesc}
                  onChange={(e) => setJobDesc(e.target.value)}
                  rows={7}
                  placeholder="Paste the full job description here…"
                  style={{ marginTop: 6, resize: "vertical" }}
                />
              </label>
            </div>
          </section>

          {/* Step 2: Resume */}
          <section className="panel">
            <h3 style={{ marginBottom: 4 }}>Step 2 — Choose your resume</h3>
            <p className="muted" style={{ fontSize: "0.85rem", marginBottom: 14 }}>
              Select which resume to tailor for this role.
            </p>
            <ResumeSelector profiles={profiles} selectedId={selectedId} onSelect={setSelectedId} />
          </section>

          {/* Step 3: Generate */}
          <section className="panel">
            <h3 style={{ marginBottom: 4 }}>Step 3 — Generate tailored application</h3>
            <p className="muted" style={{ fontSize: "0.85rem", marginBottom: 14 }}>
              The AI will tailor your resume and write a cover letter targeted at this specific role.
            </p>
            <button
              className="btn btn-accent"
              style={{ width: "100%", fontSize: "0.95rem", padding: "0.65rem" }}
              onClick={handleGenerate}
              disabled={!urlOk || !titleOk || !profileOk || generateMutation.isPending}
            >
              {generateMutation.isPending
                ? <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
                    <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2, display: "inline-block" }} />
                    Generating tailored resume &amp; cover letter…
                  </span>
                : !urlOk || !titleOk
                ? "Fill in URL and job title above first"
                : "Generate Tailored Resume & Cover Letter"}
            </button>
            {generateMutation.isError && (
              <p style={{ color: "var(--red)", fontSize: "0.85rem", marginTop: 10 }}>
                Error: {(generateMutation.error as Error).message}
              </p>
            )}
          </section>
        </div>

        {/* Right column: generated docs + apply */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {!appResult && !generateMutation.isPending && (
            <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--muted)" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: 12 }}>📄</div>
              <p style={{ fontSize: "0.9rem" }}>
                Your tailored resume and cover letter will appear here after you click Generate.
              </p>
            </div>
          )}

          {generateMutation.isPending && (
            <div className="panel" style={{ textAlign: "center", padding: "40px 20px" }}>
              <span className="spinner" style={{ width: 32, height: 32, borderWidth: 3, display: "inline-block", marginBottom: 12 }} />
              <p className="muted" style={{ fontSize: "0.9rem" }}>Analysing job and tailoring your application…</p>
            </div>
          )}

          {appResult && (
            <>
              <section className="panel">
                <h3 style={{ marginBottom: 14 }}>Application Package</h3>
                <DocsPreview result={appResult} />
              </section>

              {appResult.decision !== "do_not_apply" && (
                <section className="panel" style={{ background: "rgba(203,95,54,0.05)", border: "1px solid rgba(203,95,54,0.3)" }}>
                  <h3 style={{ marginBottom: 6 }}>Step 4 — Apply with AI</h3>
                  <p className="muted" style={{ fontSize: "0.85rem", marginBottom: 14, lineHeight: 1.6 }}>
                    A real browser will open on your screen. The AI will log in, navigate to the job, and fill in the application form using your tailored documents. You confirm before it submits.
                  </p>
                  <button
                    className="btn btn-accent"
                    style={{ width: "100%", fontSize: "1rem", padding: "0.75rem", fontWeight: 700 }}
                    onClick={() => setShowApply(true)}
                  >
                    Apply with AI → {detectPlatformLabel(jobUrl)}
                  </button>
                </section>
              )}

              {appResult.decision === "do_not_apply" && (
                <div style={{ padding: "14px 16px", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, fontSize: "0.88rem", color: "var(--red)" }}>
                  <strong>Not recommended to apply</strong> — the AI evaluated your profile as a poor fit for this role (score ≤ 40). Consider updating your resume or targeting a better-matched position.
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Auto-apply modal */}
      {showApply && selectedProfile && appResult && (
        <AutoApplyPanel
          job={jobForApply}
          bestProfile={selectedProfile}
          appResult={appResult}
          onClose={() => setShowApply(false)}
        />
      )}
    </div>
  );
}
