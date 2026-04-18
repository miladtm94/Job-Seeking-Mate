import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  deleteCandidate,
  fetchCandidates,
  generateApplication,
  ingestPdf,
  smartSearchJobs,
} from "../../api/client";
import type {
  ApplicationGenerateResponse,
  CandidateProfile,
  ScoredJob,
} from "../../api/client";
import { AutoApplyPanel } from "../auto-apply/AutoApplyPanel";
import type { JobForApply } from "../auto-apply/AutoApplyPanel";

// ── helpers ─────────────────────────────────────────────────────────────────

const REC_LABEL: Record<string, { label: string; cls: string }> = {
  strong_apply: { label: "Strong Match", cls: "tag tag-strong_apply" },
  apply:        { label: "Good Match",   cls: "tag tag-apply" },
  maybe:        { label: "Possible",     cls: "tag tag-maybe" },
  skip:         { label: "Weak Match",   cls: "tag tag-skip" },
};

function ScoreBar({ score }: { score: number }) {
  const color = score >= 75 ? "var(--green)" : score >= 55 ? "var(--yellow)" : "var(--red)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "var(--border)", borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${score}%`, height: "100%", background: color, borderRadius: 4 }} />
      </div>
      <span style={{ fontWeight: 700, fontSize: "0.88rem", color, minWidth: 32 }}>{score}</span>
    </div>
  );
}

function resumeLabel(p: CandidateProfile) {
  return p.filename || p.name || p.candidate_id.slice(0, 8);
}

// ── Resume Library ───────────────────────────────────────────────────────────

function ResumeLibrary({
  profiles,
  onUploaded,
}: {
  profiles: CandidateProfile[];
  onUploaded: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: deleteCandidate,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["candidates"] }),
  });

  const handleFiles = async (files: FileList | null) => {
    if (!files) return;
    setUploadError(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        if (!file.name.toLowerCase().endsWith(".pdf")) continue;
        await ingestPdf({
          file,
          name: file.name.replace(/\.pdf$/i, "").replace(/[_-]/g, " "),
          email: "me@example.com",
          preferred_roles: "",
          locations: "",
          work_type: "any",
        });
      }
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
      onUploaded();
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <section className="panel">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>Resume Library</h3>
        <button
          className="btn btn-accent"
          style={{ fontSize: "0.82rem", padding: "0.3rem 0.9rem" }}
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? "Uploading…" : "+ Upload PDF"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          multiple
          style={{ display: "none" }}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {uploadError && <p className="text-red" style={{ fontSize: "0.82rem" }}>{uploadError}</p>}

      {profiles.length === 0 ? (
        <div
          className="pdf-drop-zone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
          onClick={() => fileRef.current?.click()}
          style={{ margin: 0 }}
        >
          <span>Drop one or more PDF resumes here, or click to browse</span>
        </div>
      ) : (
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
        >
          {profiles.map((p) => (
            <div
              key={p.candidate_id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "10px 0",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: "0.9rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {resumeLabel(p)}
                </div>
                <div className="muted" style={{ fontSize: "0.78rem" }}>
                  {p.seniority} · {p.years_experience}y · {p.skills.length} skills
                  {p.domains.length > 0 && <> · {p.domains.slice(0, 2).join(", ")}</>}
                </div>
              </div>
              <button
                className="btn"
                style={{ fontSize: "0.75rem", padding: "0.2rem 0.6rem", color: "var(--red)", borderColor: "var(--red)" }}
                onClick={() => deleteMutation.mutate(p.candidate_id)}
                disabled={deleteMutation.isPending}
              >
                Remove
              </button>
            </div>
          ))}
          <p className="muted" style={{ fontSize: "0.75rem", marginTop: 8 }}>
            Drop more PDFs here to add to your library
          </p>
        </div>
      )}
    </section>
  );
}

// ── Search Criteria ──────────────────────────────────────────────────────────

interface Criteria {
  preferredRoles: string;
  locations: string;
  remoteOnly: boolean;
  salaryMin: string;
  maxResults: number;
}

function SearchCriteria({
  criteria,
  onChange,
  onSearch,
  searching,
  hasResumes,
}: {
  criteria: Criteria;
  onChange: (c: Criteria) => void;
  onSearch: () => void;
  searching: boolean;
  hasResumes: boolean;
}) {
  const set = (patch: Partial<Criteria>) => onChange({ ...criteria, ...patch });

  return (
    <section className="panel">
      <h3 style={{ marginBottom: 12 }}>Search Criteria</h3>
      <div className="form" style={{ gap: 10 }}>
        <label style={{ marginBottom: 0 }}>
          Preferred Roles <span className="muted">(comma-separated)</span>
          <input
            type="text"
            value={criteria.preferredRoles}
            onChange={(e) => set({ preferredRoles: e.target.value })}
            placeholder="Senior ML Engineer, Data Scientist"
          />
        </label>

        <label style={{ marginBottom: 0 }}>
          Locations <span className="muted">(comma-separated, leave blank to use resume locations)</span>
          <input
            type="text"
            value={criteria.locations}
            onChange={(e) => set({ locations: e.target.value })}
            placeholder="Sydney, Remote"
          />
        </label>

        <div className="form-row" style={{ alignItems: "flex-end" }}>
          <label style={{ marginBottom: 0 }}>
            Min Salary
            <input
              type="number"
              value={criteria.salaryMin}
              onChange={(e) => set({ salaryMin: e.target.value })}
              placeholder="120000"
            />
          </label>
          <label style={{ marginBottom: 0 }}>
            Max Results
            <select value={criteria.maxResults} onChange={(e) => set({ maxResults: Number(e.target.value) })}>
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={30}>30</option>
              <option value={50}>50</option>
            </select>
          </label>
          <label className="checkbox-label" style={{ paddingBottom: 6 }}>
            <input
              type="checkbox"
              checked={criteria.remoteOnly}
              onChange={(e) => set({ remoteOnly: e.target.checked })}
            />
            Remote only
          </label>
        </div>

        <button
          className="btn btn-accent"
          onClick={onSearch}
          disabled={searching || !hasResumes}
          style={{ width: "100%" }}
        >
          {searching ? (
            <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
              <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
              Searching & scoring against your resumes…
            </span>
          ) : !hasResumes ? (
            "Upload a resume above to start"
          ) : (
            "Find Matching Jobs"
          )}
        </button>
      </div>
    </section>
  );
}

// ── Application Panel ────────────────────────────────────────────────────────

function ApplicationPanel({
  job,
  bestProfile,
  appResult,
  onGenerate,
  generating,
  onAutoApply,
}: {
  job: ScoredJob;
  bestProfile: CandidateProfile | undefined;
  appResult: ApplicationGenerateResponse | undefined;
  onGenerate: () => void;
  generating: boolean;
  onAutoApply: () => void;
}) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h3 style={{ marginBottom: 2 }}>{job.job.title}</h3>
          <p className="muted">{job.job.company} · {job.job.location}</p>
          {job.job.salary && <p className="text-green" style={{ fontSize: "0.88rem" }}>{job.job.salary}</p>}
        </div>
        <span className={REC_LABEL[job.recommendation]?.cls ?? "tag"}>
          {REC_LABEL[job.recommendation]?.label}
        </span>
      </div>

      {/* Score breakdown */}
      <div style={{ margin: "14px 0", padding: "12px", background: "rgba(0,0,0,0.15)", borderRadius: 8 }}>
        <div style={{ marginBottom: 8 }}>
          <strong style={{ fontSize: "1.1rem" }}>{job.match_score}</strong>
          <span className="muted"> / 100 match score</span>
          {bestProfile && (
            <span className="muted" style={{ marginLeft: 8, fontSize: "0.8rem" }}>
              — best from <strong>{resumeLabel(bestProfile)}</strong>
            </span>
          )}
        </div>
        <ScoreBar score={job.match_score} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px", marginTop: 10, fontSize: "0.82rem" }}>
          {Object.entries(job.breakdown).map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between" }}>
              <span className="muted">{k.replace("_score", "").replace("_", " ")}</span>
              <strong>{typeof v === "number" ? v.toFixed(1) : v}</strong>
            </div>
          ))}
        </div>
      </div>

      <p className="muted" style={{ fontSize: "0.88rem", lineHeight: 1.6, marginBottom: 12 }}>
        {job.explanation}
      </p>

      {job.key_matching_skills.length > 0 && (
        <>
          <h4>Matching Skills</h4>
          <div className="tag-list">
            {job.key_matching_skills.map((s) => <span key={s} className="tag tag-skill">{s}</span>)}
          </div>
        </>
      )}

      {job.missing_skills.length > 0 && (
        <>
          <h4>Gaps</h4>
          <div className="tag-list">
            {job.missing_skills.map((s) => <span key={s} className="tag tag-gap">{s}</span>)}
          </div>
        </>
      )}

      {job.fit_reasons.length > 0 && (
        <>
          <h4>Fit Reasons</h4>
          <ul>{job.fit_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </>
      )}

      <h4>Description</h4>
      <p className="description-text" style={{ maxHeight: 180, overflowY: "auto" }}>
        {job.job.description}
      </p>

      <div className="button-row" style={{ marginTop: 16 }}>
        {job.job.url && (
          <a href={job.job.url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">
            View Posting
          </a>
        )}
      </div>

      {/* Application package */}
      {appResult ? (
        <div className="app-result" style={{ marginTop: 16 }}>
          {/* Decision banner */}
          {appResult.decision === "do_not_apply" ? (
            <div style={{ background: "rgba(239,68,68,0.12)", border: "1px solid var(--red)", borderRadius: 8, padding: "12px 16px", marginBottom: 12 }}>
              <strong style={{ color: "var(--red)" }}>Do Not Apply</strong>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: "0.85rem" }}>
                Score ≤ 40 — this role is a poor fit based on the expert evaluation.
              </p>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
              <span className={`tag ${appResult.decision === "use_as_is" ? "tag-strong_apply" : appResult.decision === "improve" ? "tag-apply" : "tag-maybe"}`}>
                {appResult.decision === "use_as_is" ? "Resume: Use As-Is" : appResult.decision === "improve" ? "Resume: Surgical Improvements" : "New Resume Generated"}
              </span>
              <span className={`tag ${appResult.shortlisting_probability === "High" ? "tag-strong_apply" : appResult.shortlisting_probability === "Medium" ? "tag-apply" : "tag-maybe"}`}>
                Shortlisting: {appResult.shortlisting_probability}
              </span>
            </div>
          )}

          {/* Strategic positioning */}
          {appResult.strategic_positioning.length > 0 && (
            <details open>
              <summary><strong>Strategic Positioning</strong></summary>
              <ul style={{ marginTop: 8 }}>{appResult.strategic_positioning.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </details>
          )}

          {/* Recruiter risks */}
          {appResult.recruiter_risks.length > 0 && (
            <details>
              <summary><strong>Recruiter Objections to Address</strong></summary>
              <ul style={{ marginTop: 8 }}>{appResult.recruiter_risks.map((r, i) => <li key={i} style={{ color: "var(--yellow)" }}>{r}</li>)}</ul>
            </details>
          )}

          {/* ATS keywords */}
          {Object.keys(appResult.ats_keywords).length > 0 && (
            <details>
              <summary><strong>ATS Keywords</strong></summary>
              <div className="tag-list" style={{ marginTop: 8 }}>
                {Object.entries(appResult.ats_keywords).map(([kw, status]) => (
                  <span key={kw} className={`tag ${status === "present" ? "tag-skill" : status === "partial" ? "tag-apply" : "tag-gap"}`} style={{ fontSize: "0.75rem" }}>
                    {status === "present" ? "✓" : status === "partial" ? "~" : "✗"} {kw}
                  </span>
                ))}
              </div>
            </details>
          )}

          {/* Resume artifacts */}
          <h4>Application Package</h4>
          {appResult.customized_resume && (
            <details>
              <summary>{appResult.decision === "improve" ? "Resume Surgical Improvements" : "Tailored Resume"}</summary>
              <pre className="artifact-text">{appResult.customized_resume}</pre>
            </details>
          )}
          {appResult.resume_improvements.length > 0 && (
            <details>
              <summary>Additional Resume Tweaks</summary>
              <ul>{appResult.resume_improvements.map((r, i) => <li key={i}>{r}</li>)}</ul>
            </details>
          )}
          <details>
            <summary>Cover Letter</summary>
            <pre className="artifact-text">{appResult.tailored_cover_letter}</pre>
          </details>
          {appResult.talking_points.length > 0 && (
            <details>
              <summary>Interview Talking Points</summary>
              <ul>{appResult.talking_points.map((t, i) => <li key={i}>{t}</li>)}</ul>
            </details>
          )}
          <h4>Readiness Checklist</h4>
          <ul className="checklist">
            {appResult.readiness_checklist.map((c, i) => <li key={i}>{c}</li>)}
          </ul>

          {appResult.decision !== "do_not_apply" && job.job.url && bestProfile && (
            <button
              className="btn btn-accent"
              style={{ marginTop: 16, width: "100%" }}
              onClick={onAutoApply}
            >
              Apply with AI ›
            </button>
          )}
        </div>
      ) : (
        <button
          className="btn btn-accent"
          style={{ marginTop: 16, width: "100%" }}
          onClick={onGenerate}
          disabled={generating || !bestProfile}
          title={!bestProfile ? "No matching resume found" : undefined}
        >
          {generating
            ? "Generating application…"
            : bestProfile
            ? `Tailor Resume & Generate Cover Letter (from ${resumeLabel(bestProfile)})`
            : "No matching resume"}
        </button>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export function FindJobsPage() {
  const queryClient = useQueryClient();

  const candidatesQuery = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });
  const profiles = candidatesQuery.data ?? [];

  const [criteria, setCriteria] = useState<Criteria>({
    preferredRoles: "",
    locations: "",
    remoteOnly: false,
    salaryMin: "",
    maxResults: 20,
  });

  const [activeJob, setActiveJob] = useState<ScoredJob | null>(null);
  const [appResults, setAppResults] = useState<Record<string, ApplicationGenerateResponse>>({});
  const [showAutoApply, setShowAutoApply] = useState(false);

  const searchMutation = useMutation({ mutationFn: smartSearchJobs });

  const applyMutation = useMutation({
    mutationFn: generateApplication,
    onSuccess: (data, variables) => {
      const jobId = variables.job.job_id ?? "";
      setAppResults((prev) => ({ ...prev, [jobId]: data }));
    },
  });

  const handleSearch = () => {
    setActiveJob(null);
    const roles = criteria.preferredRoles
      .split(",")
      .map((r) => r.trim())
      .filter(Boolean);
    const locs = criteria.locations
      .split(",")
      .map((l) => l.trim())
      .filter(Boolean);
    searchMutation.mutate({
      preferred_roles: roles.length ? roles : undefined,
      locations: locs.length ? locs : undefined,
      remote_only: criteria.remoteOnly,
      salary_min: criteria.salaryMin ? parseInt(criteria.salaryMin, 10) : undefined,
      max_results: criteria.maxResults,
    });
  };

  const getBestProfile = (sj: ScoredJob): CandidateProfile | undefined =>
    sj.best_candidate_id
      ? profiles.find((p) => p.candidate_id === sj.best_candidate_id)
      : profiles[0];

  const handleGenerate = (sj: ScoredJob) => {
    const best = getBestProfile(sj);
    if (!best) return;
    applyMutation.mutate({
      candidate_profile: {
        name: best.name,
        skills: best.skills,
        experience_summary: best.summary,
        seniority: best.seniority,
        raw_cv_text: best.raw_cv_text,
      },
      job: {
        job_id: sj.job.job_id,
        title: sj.job.title,
        company: sj.job.company,
        description: sj.job.description,
        location: sj.job.location,
        salary: sj.job.salary ?? undefined,
        url: sj.job.url,
      },
      mode: "manual",
      match_score: sj.match_score,
    });
  };

  const results = searchMutation.data;

  return (
    <div className="page">
      <h2>Find Matching Jobs</h2>
      <p className="muted">
        Upload your resumes, set criteria, and let the system score every job against your best matching resume.
      </p>

      {/* Top section: library + criteria side by side */}
      <div className="grid two-col" style={{ marginTop: 16, alignItems: "flex-start" }}>
        <ResumeLibrary
          profiles={profiles}
          onUploaded={() => queryClient.invalidateQueries({ queryKey: ["candidates"] })}
        />
        <SearchCriteria
          criteria={criteria}
          onChange={setCriteria}
          onSearch={handleSearch}
          searching={searchMutation.isPending}
          hasResumes={profiles.length > 0}
        />
      </div>

      {searchMutation.isError && (
        <p className="text-red panel" style={{ marginTop: 8 }}>
          Error: {(searchMutation.error as Error).message}
        </p>
      )}

      {/* Results */}
      {results && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 16, margin: "16px 0 8px" }}>
            <span className="muted">
              {results.total_found} jobs found · searched for{" "}
              <strong>{results.queries_used.join(", ")}</strong>
            </span>
          </div>

          <div className="grid two-col" style={{ marginTop: 0 }}>
            {/* Job list */}
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ overflowY: "auto", maxHeight: 720 }}>
                {results.scored_jobs.map((sj, i) => {
                  const rec = REC_LABEL[sj.recommendation] ?? REC_LABEL.maybe;
                  const isActive = activeJob?.job.job_id === sj.job.job_id;
                  const hasApp = !!appResults[sj.job.job_id];
                  return (
                    <div
                      key={sj.job.job_id}
                      onClick={() => setActiveJob(sj)}
                      style={{
                        padding: "14px 16px",
                        borderBottom: "1px solid var(--border)",
                        cursor: "pointer",
                        background: isActive ? "rgba(203,95,54,0.06)" : "transparent",
                        display: "flex",
                        gap: 12,
                        alignItems: "flex-start",
                      }}
                    >
                      <span className="muted" style={{ fontSize: "0.75rem", fontWeight: 700, paddingTop: 2, minWidth: 24 }}>
                        #{i + 1}
                      </span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                          <span style={{ fontWeight: 600, fontSize: "0.92rem" }}>{sj.job.title}</span>
                          <span className={rec.cls} style={{ whiteSpace: "nowrap", flexShrink: 0 }}>{rec.label}</span>
                        </div>
                        <div className="muted" style={{ fontSize: "0.82rem", margin: "2px 0 6px" }}>
                          {sj.job.company} · {sj.job.location}
                          {sj.job.salary && <span className="text-green"> · {sj.job.salary}</span>}
                        </div>
                        <ScoreBar score={sj.match_score} />
                        {sj.best_candidate_name && profiles.length > 1 && (
                          <div className="muted" style={{ fontSize: "0.72rem", marginTop: 4 }}>
                            Best resume: {sj.best_candidate_name}
                          </div>
                        )}
                        {sj.key_matching_skills.length > 0 && (
                          <div className="tag-list" style={{ marginTop: 6 }}>
                            {sj.key_matching_skills.slice(0, 5).map((s) => (
                              <span key={s} className="tag tag-skill" style={{ fontSize: "0.72rem" }}>{s}</span>
                            ))}
                          </div>
                        )}
                        {hasApp && (
                          <span className="tag tag-success" style={{ marginTop: 6, fontSize: "0.72rem" }}>
                            Application ready
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Detail + application panel */}
            <section className="panel">
              {activeJob ? (
                <ApplicationPanel
                  job={activeJob}
                  bestProfile={getBestProfile(activeJob)}
                  appResult={appResults[activeJob.job.job_id]}
                  onGenerate={() => handleGenerate(activeJob)}
                  generating={applyMutation.isPending}
                  onAutoApply={() => setShowAutoApply(true)}
                />
              ) : (
                <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--muted)" }}>
                  <p style={{ fontSize: "2rem", marginBottom: 8 }}>←</p>
                  <p>Select a job to see the full match breakdown and generate your tailored application</p>
                </div>
              )}
            </section>
          </div>
        </>
      )}

      {!results && !searchMutation.isPending && profiles.length > 0 && (
        <div className="panel" style={{ marginTop: 16, textAlign: "center", padding: "40px 20px" }}>
          <p className="muted" style={{ marginBottom: 16 }}>
            {profiles.length} resume{profiles.length > 1 ? "s" : ""} loaded — set your criteria above and search
          </p>
          <button className="btn btn-accent" onClick={handleSearch}>
            Find Matching Jobs
          </button>
        </div>
      )}

      {showAutoApply && activeJob && getBestProfile(activeJob) && (
        <AutoApplyPanel
          job={{
            url:         activeJob.job.url,
            title:       activeJob.job.title,
            company:     activeJob.job.company,
            description: activeJob.job.description,
          } satisfies JobForApply}
          bestProfile={getBestProfile(activeJob)!}
          appResult={appResults[activeJob.job.job_id]}
          onClose={() => setShowAutoApply(false)}
        />
      )}
    </div>
  );
}
