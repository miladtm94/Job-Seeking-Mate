import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchCandidates,
  smartSearchJobs,
  generateApplication,
} from "../../api/client";
import type {
  ScoredJob,
  ApplicationGenerateResponse,
} from "../../api/client";

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
      <div style={{
        flex: 1, height: 6, background: "var(--border)", borderRadius: 4, overflow: "hidden",
      }}>
        <div style={{ width: `${score}%`, height: "100%", background: color, borderRadius: 4 }} />
      </div>
      <span style={{ fontWeight: 700, fontSize: "0.88rem", color, minWidth: 32 }}>{score}</span>
    </div>
  );
}

export function JobsPage() {
  const candidates = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });
  const profile = candidates.data?.at(-1);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeJob, setActiveJob] = useState<ScoredJob | null>(null);
  const [appResults, setAppResults] = useState<Record<string, ApplicationGenerateResponse>>({});
  const [remoteOnly, setRemoteOnly] = useState(false);

  const searchMutation = useMutation({ mutationFn: smartSearchJobs });

  const applyMutation = useMutation({
    mutationFn: generateApplication,
    onSuccess: (data, variables) => {
      const jobId = variables.job.job_id ?? "";
      setAppResults((prev) => ({ ...prev, [jobId]: data }));
    },
  });

  const handleSearch = () => {
    if (!profile) return;
    setSelected(new Set());
    setActiveJob(null);
    searchMutation.mutate({
      candidate_id: profile.candidate_id,
      max_results: 20,
      remote_only: remoteOnly,
    });
  };

  const toggleSelect = (jobId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(jobId) ? next.delete(jobId) : next.add(jobId);
      return next;
    });
  };

  const handleGenerateForJob = (sj: ScoredJob) => {
    if (!profile) return;
    applyMutation.mutate({
      candidate_profile: {
        name: profile.name,
        skills: profile.skills,
        experience_summary: profile.summary,
        seniority: profile.seniority,
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
    });
  };

  const handleGenerateSelected = () => {
    const results = searchMutation.data?.scored_jobs ?? [];
    results
      .filter((sj) => selected.has(sj.job.job_id) && !appResults[sj.job.job_id])
      .forEach((sj) => handleGenerateForJob(sj));
  };

  const results = searchMutation.data;

  return (
    <div className="page">
      <h2>Smart Job Search</h2>
      <p className="muted">
        Searches roles matching your profile and scores each job for alignment
      </p>

      {/* Control bar */}
      <section className="panel" style={{ marginTop: 16 }}>
        {profile ? (
          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <div>
              <strong>{profile.name}</strong>
              <span className="muted" style={{ marginLeft: 8 }}>
                {profile.preferred_roles.slice(0, 2).join(" · ") || profile.skills.slice(0, 3).join(", ")}
              </span>
            </div>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={remoteOnly}
                onChange={(e) => setRemoteOnly(e.target.checked)}
              />
              Remote only
            </label>
            <button
              className="btn btn-accent"
              onClick={handleSearch}
              disabled={searchMutation.isPending}
              style={{ marginLeft: "auto" }}
            >
              {searchMutation.isPending ? (
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                  Searching & scoring…
                </span>
              ) : (
                "Find Matching Jobs"
              )}
            </button>
          </div>
        ) : (
          <p className="muted">
            <a href="/profile" className="link">Upload your resume</a> first to enable smart search.
          </p>
        )}
      </section>

      {searchMutation.isError && (
        <p className="text-red panel" style={{ marginTop: 8 }}>
          Error: {(searchMutation.error as Error).message}
        </p>
      )}

      {/* Results */}
      {results && (
        <>
          {/* Summary bar */}
          <div style={{ display: "flex", alignItems: "center", gap: 16, margin: "16px 0 8px" }}>
            <span className="muted">
              {results.total_found} jobs found · searched for{" "}
              <strong>{results.queries_used.join(", ")}</strong>
            </span>
            {selected.size > 0 && (
              <button
                className="btn btn-accent"
                style={{ marginLeft: "auto" }}
                onClick={handleGenerateSelected}
                disabled={applyMutation.isPending}
              >
                Generate Applications ({selected.size} selected)
              </button>
            )}
          </div>

          <div className="grid two-col" style={{ marginTop: 0 }}>
            {/* Job list */}
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ overflowY: "auto", maxHeight: 680 }}>
                {results.scored_jobs.map((sj, i) => {
                  const rec = REC_LABEL[sj.recommendation] ?? REC_LABEL.maybe;
                  const isActive = activeJob?.job.job_id === sj.job.job_id;
                  const isSelected = selected.has(sj.job.job_id);
                  const hasApp = !!appResults[sj.job.job_id];
                  return (
                    <div
                      key={sj.job.job_id}
                      onClick={() => setActiveJob(sj)}
                      style={{
                        padding: "14px 16px",
                        borderBottom: "1px solid var(--border)",
                        cursor: "pointer",
                        background: isActive
                          ? "rgba(203,95,54,0.06)"
                          : isSelected
                          ? "rgba(46,139,87,0.05)"
                          : "transparent",
                        display: "flex",
                        gap: 12,
                        alignItems: "flex-start",
                      }}
                    >
                      {/* Rank + checkbox */}
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, paddingTop: 2 }}>
                        <span className="muted" style={{ fontSize: "0.75rem", fontWeight: 700 }}>#{i + 1}</span>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(sj.job.job_id)}
                          onClick={(e) => e.stopPropagation()}
                          style={{ cursor: "pointer" }}
                        />
                      </div>

                      {/* Content */}
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

            {/* Detail panel */}
            <section className="panel">
              {activeJob ? (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <h3 style={{ marginBottom: 2 }}>{activeJob.job.title}</h3>
                      <p className="muted">{activeJob.job.company} · {activeJob.job.location}</p>
                    </div>
                    <span className={REC_LABEL[activeJob.recommendation]?.cls ?? "tag"}>
                      {REC_LABEL[activeJob.recommendation]?.label}
                    </span>
                  </div>

                  {/* Score breakdown */}
                  <div style={{ margin: "14px 0", padding: "12px", background: "#f8f9fa", borderRadius: 8 }}>
                    <div style={{ marginBottom: 8 }}>
                      <strong style={{ fontSize: "1.1rem" }}>{activeJob.match_score}</strong>
                      <span className="muted"> / 100 match score</span>
                    </div>
                    <ScoreBar score={activeJob.match_score} />
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px", marginTop: 10, fontSize: "0.82rem" }}>
                      {Object.entries(activeJob.breakdown).map(([k, v]) => (
                        <div key={k} style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="muted">{k.replace("_score", "").replace("_", " ")}</span>
                          <strong>{typeof v === "number" ? v.toFixed(1) : v}</strong>
                        </div>
                      ))}
                    </div>
                  </div>

                  <p className="muted" style={{ fontSize: "0.88rem", lineHeight: 1.6, marginBottom: 12 }}>
                    {activeJob.explanation}
                  </p>

                  {activeJob.key_matching_skills.length > 0 && (
                    <>
                      <h4>Matching Skills</h4>
                      <div className="tag-list">
                        {activeJob.key_matching_skills.map((s) => (
                          <span key={s} className="tag tag-skill">{s}</span>
                        ))}
                      </div>
                    </>
                  )}

                  {activeJob.missing_skills.length > 0 && (
                    <>
                      <h4>Gaps</h4>
                      <div className="tag-list">
                        {activeJob.missing_skills.map((s) => (
                          <span key={s} className="tag tag-gap">{s}</span>
                        ))}
                      </div>
                    </>
                  )}

                  {activeJob.fit_reasons.length > 0 && (
                    <>
                      <h4>Fit Reasons</h4>
                      <ul>
                        {activeJob.fit_reasons.map((r, i) => <li key={i}>{r}</li>)}
                      </ul>
                    </>
                  )}

                  <h4>Description</h4>
                  <p className="description-text" style={{ maxHeight: 200, overflowY: "auto" }}>
                    {activeJob.job.description}
                  </p>

                  <div className="button-row" style={{ marginTop: 16 }}>
                    <button
                      className={`btn ${selected.has(activeJob.job.job_id) ? "" : "btn-accent"}`}
                      onClick={() => toggleSelect(activeJob.job.job_id)}
                    >
                      {selected.has(activeJob.job.job_id) ? "Deselect" : "Select for Application"}
                    </button>
                    {activeJob.job.url && (
                      <a href={activeJob.job.url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">
                        View Posting
                      </a>
                    )}
                  </div>

                  {/* Application result for this job */}
                  {appResults[activeJob.job.job_id] && (() => {
                    const app = appResults[activeJob.job.job_id];
                    return (
                      <div className="app-result">
                        <h4>Application Package</h4>
                        <details><summary>Tailored Resume</summary>
                          <pre className="artifact-text">{app.customized_resume}</pre>
                        </details>
                        <details><summary>Cover Letter</summary>
                          <pre className="artifact-text">{app.tailored_cover_letter}</pre>
                        </details>
                        {app.talking_points.length > 0 && (
                          <details><summary>Talking Points</summary>
                            <ul>{app.talking_points.map((t, i) => <li key={i}>{t}</li>)}</ul>
                          </details>
                        )}
                        <h4>Readiness Checklist</h4>
                        <ul className="checklist">
                          {app.readiness_checklist.map((c, i) => <li key={i}>{c}</li>)}
                        </ul>
                      </div>
                    );
                  })()}

                  {/* Generate for this specific job */}
                  {!appResults[activeJob.job.job_id] && profile && (
                    <button
                      className="btn btn-accent"
                      style={{ marginTop: 12 }}
                      onClick={() => handleGenerateForJob(activeJob)}
                      disabled={applyMutation.isPending}
                    >
                      {applyMutation.isPending ? "Generating…" : "Generate Application Now"}
                    </button>
                  )}
                </>
              ) : (
                <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--muted)" }}>
                  <p style={{ fontSize: "2rem", marginBottom: 8 }}>←</p>
                  <p>Select a job to see the match breakdown and generate your application materials</p>
                </div>
              )}
            </section>
          </div>
        </>
      )}

      {!results && !searchMutation.isPending && profile && (
        <div className="panel" style={{ marginTop: 16, textAlign: "center", padding: "40px 20px" }}>
          <p className="muted" style={{ marginBottom: 16 }}>
            Ready to search for roles matching your profile as{" "}
            <strong>{profile.preferred_roles[0] || profile.seniority + " " + (profile.domains[0] || "professional")}</strong>
          </p>
          <button className="btn btn-accent" onClick={handleSearch}>
            Find Matching Jobs
          </button>
        </div>
      )}
    </div>
  );
}
