import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  searchJobs,
  fetchCandidates,
  generateApplication,
} from "../../api/client";
import type {
  JobPosting,
  JobSearchResponse,
  CandidateProfile,
  ApplicationGenerateResponse,
} from "../../api/client";

export function JobsPage() {
  const candidates = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });
  const profile: CandidateProfile | undefined = candidates.data?.[0];

  const [query, setQuery] = useState("");
  const [location, setLocation] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [salaryMin, setSalaryMin] = useState("");
  const [results, setResults] = useState<JobSearchResponse | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobPosting | null>(null);
  const [appResult, setAppResult] = useState<ApplicationGenerateResponse | null>(null);

  const searchMutation = useMutation({
    mutationFn: searchJobs,
    onSuccess: (data) => {
      setResults(data);
      setSelectedJob(null);
      setAppResult(null);
    },
  });

  const applyMutation = useMutation({
    mutationFn: generateApplication,
    onSuccess: (data) => setAppResult(data),
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    searchMutation.mutate({
      query,
      locations: location ? [location] : [],
      remote_only: remoteOnly,
      salary_min: salaryMin ? parseInt(salaryMin, 10) : undefined,
      max_results: 25,
    });
  };

  const handleGenerateApp = (job: JobPosting) => {
    if (!profile) return;
    applyMutation.mutate({
      candidate_profile: {
        name: profile.name,
        skills: profile.skills,
        experience_summary: profile.summary,
        seniority: profile.seniority,
      },
      job: {
        job_id: job.job_id,
        title: job.title,
        company: job.company,
        description: job.description,
        location: job.location,
        salary: job.salary ?? undefined,
        url: job.url,
      },
      mode: "manual",
    });
  };

  return (
    <div className="page">
      <h2>Job Search</h2>
      <p className="muted">Discover and evaluate job opportunities</p>

      {/* Search Form */}
      <section className="panel">
        <form onSubmit={handleSearch} className="search-form">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Job title, skills, or keywords..."
            className="search-input"
            required
          />
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Location"
            className="search-location"
          />
          <input
            type="number"
            value={salaryMin}
            onChange={(e) => setSalaryMin(e.target.value)}
            placeholder="Min salary"
            className="search-salary"
          />
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={remoteOnly}
              onChange={(e) => setRemoteOnly(e.target.checked)}
            />
            Remote only
          </label>
          <button type="submit" className="btn btn-accent" disabled={searchMutation.isPending}>
            {searchMutation.isPending ? "Searching..." : "Search"}
          </button>
        </form>
      </section>

      {searchMutation.isError && (
        <p className="text-red panel">Error: {(searchMutation.error as Error).message}</p>
      )}

      {/* Results */}
      {results && (
        <div className="grid two-col">
          <section className="panel">
            <h3>
              Results ({results.total} found{results.query ? ` for "${results.query}"` : ""})
            </h3>
            <div className="job-list">
              {results.jobs.map((job) => (
                <div
                  key={job.job_id}
                  className={`job-card${selectedJob?.job_id === job.job_id ? " selected" : ""}`}
                  onClick={() => {
                    setSelectedJob(job);
                    setAppResult(null);
                  }}
                >
                  <div className="job-card-header">
                    <strong>{job.title}</strong>
                    <span className="tag tag-source">{job.source}</span>
                  </div>
                  <div className="job-card-meta">
                    <span>{job.company}</span>
                    <span>{job.location}</span>
                    {job.salary && <span className="text-green">{job.salary}</span>}
                  </div>
                  <p className="job-card-desc">{job.description.slice(0, 120)}...</p>
                </div>
              ))}
            </div>
          </section>

          {/* Job Detail + Apply */}
          <section className="panel">
            {selectedJob ? (
              <>
                <h3>{selectedJob.title}</h3>
                <div className="status-row">
                  <span>Company</span>
                  <strong>{selectedJob.company}</strong>
                </div>
                <div className="status-row">
                  <span>Location</span>
                  <strong>{selectedJob.location}</strong>
                </div>
                {selectedJob.salary && (
                  <div className="status-row">
                    <span>Salary</span>
                    <strong className="text-green">{selectedJob.salary}</strong>
                  </div>
                )}
                <div className="status-row">
                  <span>Source</span>
                  <strong>{selectedJob.source}</strong>
                </div>

                <h4>Description</h4>
                <p className="description-text">{selectedJob.description}</p>

                <div className="button-row" style={{ marginTop: 16 }}>
                  {selectedJob.url && (
                    <a
                      href={selectedJob.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-secondary"
                    >
                      View Original
                    </a>
                  )}
                  {profile && (
                    <button
                      className="btn btn-accent"
                      onClick={() => handleGenerateApp(selectedJob)}
                      disabled={applyMutation.isPending}
                    >
                      {applyMutation.isPending ? "Generating..." : "Generate Application"}
                    </button>
                  )}
                </div>

                {!profile && (
                  <p className="muted" style={{ marginTop: 8 }}>
                    <a href="/profile" className="link">
                      Create a profile
                    </a>{" "}
                    to generate applications
                  </p>
                )}

                {/* Application Result */}
                {appResult && (
                  <div className="app-result">
                    <h4>Application Package Ready</h4>
                    <div className="status-row">
                      <span>Status</span>
                      <strong className="capitalize">{appResult.status}</strong>
                    </div>

                    <details>
                      <summary>Tailored Resume</summary>
                      <pre className="artifact-text">{appResult.customized_resume}</pre>
                    </details>

                    <details>
                      <summary>Cover Letter</summary>
                      <pre className="artifact-text">{appResult.tailored_cover_letter}</pre>
                    </details>

                    {appResult.talking_points.length > 0 && (
                      <details>
                        <summary>Talking Points</summary>
                        <ul>
                          {appResult.talking_points.map((tp, i) => (
                            <li key={i}>{tp}</li>
                          ))}
                        </ul>
                      </details>
                    )}

                    <h4>Readiness Checklist</h4>
                    <ul className="checklist">
                      {appResult.readiness_checklist.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <p className="muted">Select a job to see details and generate application materials</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
