import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { runFullCycle } from "../../api/client";

interface PipelineResult {
  candidate?: Record<string, unknown>;
  jobs_found?: number;
  matches?: Array<{
    job_id: string;
    match_score: number;
    recommendation: string;
    explanation: string;
    key_matching_skills: string[];
    missing_skills: string[];
    fit_reasons: string[];
  }>;
  applications?: Array<{
    application_id: string;
    customized_resume: string;
    tailored_cover_letter: string;
    talking_points: string[];
    match_score: number;
  }>;
  steps?: Array<{ agent: string; success: boolean }>;
  errors?: string[];
}

export function PipelinePage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [cvText, setCvText] = useState("");
  const [query, setQuery] = useState("");
  const [roles, setRoles] = useState("");
  const [locations, setLocations] = useState("");
  const [salaryMin, setSalaryMin] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [selectedApp, setSelectedApp] = useState<number | null>(null);

  const mutation = useMutation({
    mutationFn: runFullCycle,
    onSuccess: () => setSelectedApp(null),
  });

  const result = mutation.data as PipelineResult | undefined;

  const handleRun = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      name,
      email,
      raw_cv_text: cvText,
      query: query || roles.split(",")[0]?.trim() || "",
      preferred_roles: roles
        .split(",")
        .map((r) => r.trim())
        .filter(Boolean),
      locations: locations
        .split(",")
        .map((l) => l.trim())
        .filter(Boolean),
      salary_min: salaryMin ? parseInt(salaryMin, 10) : undefined,
      remote_only: remoteOnly,
      max_results: 15,
      mode: "manual",
    });
  };

  return (
    <div className="page">
      <h2>Full Pipeline</h2>
      <p className="muted">
        Run the complete agent pipeline: Parse CV, Search Jobs, Score Matches, Generate Applications
      </p>

      {/* Input Form */}
      <section className="panel">
        <h3>Pipeline Configuration</h3>
        <form onSubmit={handleRun} className="form">
          <div className="form-row">
            <label>
              Full Name
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
          </div>

          <label>
            CV / Resume Text
            <textarea
              value={cvText}
              onChange={(e) => setCvText(e.target.value)}
              rows={6}
              required
              minLength={50}
              placeholder="Paste your CV here..."
            />
          </label>

          <div className="form-row">
            <label>
              Search Query
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. Data Scientist"
              />
            </label>
            <label>
              Preferred Roles
              <input
                type="text"
                value={roles}
                onChange={(e) => setRoles(e.target.value)}
                placeholder="Data Scientist, ML Engineer"
              />
            </label>
          </div>

          <div className="form-row">
            <label>
              Locations
              <input
                type="text"
                value={locations}
                onChange={(e) => setLocations(e.target.value)}
                placeholder="Sydney, Remote"
              />
            </label>
            <label>
              Min Salary
              <input
                type="number"
                value={salaryMin}
                onChange={(e) => setSalaryMin(e.target.value)}
                placeholder="120000"
              />
            </label>
          </div>

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={remoteOnly}
              onChange={(e) => setRemoteOnly(e.target.checked)}
            />
            Remote only
          </label>

          <button type="submit" className="btn btn-accent" disabled={mutation.isPending}>
            {mutation.isPending ? "Running Pipeline..." : "Run Full Pipeline"}
          </button>
        </form>
      </section>

      {/* Loading */}
      {mutation.isPending && (
        <section className="panel">
          <div className="pipeline-loading">
            <div className="spinner" />
            <p>Running agent pipeline... This may take a moment.</p>
          </div>
        </section>
      )}

      {mutation.isError && (
        <section className="panel">
          <p className="text-red">Error: {(mutation.error as Error).message}</p>
        </section>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Pipeline Steps */}
          <section className="panel">
            <h3>Pipeline Steps</h3>
            <div className="pipeline-steps">
              {(result.steps ?? []).map((step, i) => (
                <div key={i} className={`pipeline-step ${step.success ? "success" : "failed"}`}>
                  <span className="step-icon">{step.success ? "\u2713" : "\u2717"}</span>
                  <span className="capitalize">{step.agent}</span>
                </div>
              ))}
            </div>
            {result.errors && result.errors.length > 0 && (
              <div className="errors">
                {result.errors.map((err, i) => (
                  <p key={i} className="text-red">
                    {err}
                  </p>
                ))}
              </div>
            )}
          </section>

          {/* Matches */}
          {result.matches && result.matches.length > 0 && (
            <section className="panel">
              <h3>Job Matches ({result.matches.length} of {result.jobs_found} jobs)</h3>
              <div className="match-list">
                {result.matches.map((match, i) => (
                  <div key={match.job_id || i} className="match-card">
                    <div className="match-header">
                      <span className={`score score-${scoreClass(match.match_score)}`}>
                        {match.match_score}
                      </span>
                      <span className={`tag tag-${match.recommendation}`}>
                        {match.recommendation}
                      </span>
                    </div>
                    <p className="match-explanation">{match.explanation}</p>
                    {match.key_matching_skills.length > 0 && (
                      <div className="tag-list">
                        {match.key_matching_skills.map((s) => (
                          <span key={s} className="tag tag-skill">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                    {match.missing_skills.length > 0 && (
                      <div className="tag-list">
                        {match.missing_skills.map((s) => (
                          <span key={s} className="tag tag-gap">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Generated Applications */}
          {result.applications && result.applications.length > 0 && (
            <section className="panel">
              <h3>Generated Applications ({result.applications.length})</h3>
              <div className="app-tabs">
                {result.applications.map((app, i) => (
                  <button
                    key={app.application_id}
                    className={`tab ${selectedApp === i ? "active" : ""}`}
                    onClick={() => setSelectedApp(selectedApp === i ? null : i)}
                  >
                    App #{i + 1} (Score: {app.match_score})
                  </button>
                ))}
              </div>

              {selectedApp !== null && result.applications[selectedApp] && (
                <div className="app-detail">
                  <details open>
                    <summary>Tailored Resume</summary>
                    <pre className="artifact-text">
                      {result.applications[selectedApp].customized_resume}
                    </pre>
                  </details>
                  <details>
                    <summary>Cover Letter</summary>
                    <pre className="artifact-text">
                      {result.applications[selectedApp].tailored_cover_letter}
                    </pre>
                  </details>
                  {result.applications[selectedApp].talking_points.length > 0 && (
                    <details>
                      <summary>Talking Points</summary>
                      <ul>
                        {result.applications[selectedApp].talking_points.map((tp, j) => (
                          <li key={j}>{tp}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}

function scoreClass(score: number): string {
  if (score >= 75) return "high";
  if (score >= 55) return "medium";
  return "low";
}
