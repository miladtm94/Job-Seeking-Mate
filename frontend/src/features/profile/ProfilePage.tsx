import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchCandidates, ingestCandidate } from "../../api/client";
import type { CandidateProfile } from "../../api/client";

export function ProfilePage() {
  const queryClient = useQueryClient();
  const candidates = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });
  const profile: CandidateProfile | undefined = candidates.data?.[0];

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [cvText, setCvText] = useState("");
  const [roles, setRoles] = useState("");
  const [locations, setLocations] = useState("");
  const [salaryMin, setSalaryMin] = useState("");
  const [workType, setWorkType] = useState("any");

  const mutation = useMutation({
    mutationFn: ingestCandidate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      name,
      email,
      raw_cv_text: cvText,
      preferred_roles: roles
        .split(",")
        .map((r) => r.trim())
        .filter(Boolean),
      locations: locations
        .split(",")
        .map((l) => l.trim())
        .filter(Boolean),
      salary_min: salaryMin ? parseInt(salaryMin, 10) : undefined,
      work_type: workType,
    });
  };

  return (
    <div className="page">
      <h2>Candidate Profile</h2>
      <p className="muted">Upload your CV and preferences to get started</p>

      <div className="grid two-col">
        {/* Form */}
        <section className="panel">
          <h3>{profile ? "Update Profile" : "Create Profile"}</h3>
          <form onSubmit={handleSubmit} className="form">
            <label>
              Full Name
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jane Smith"
                required
              />
            </label>

            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="jane@example.com"
                required
              />
            </label>

            <label>
              CV / Resume Text
              <textarea
                value={cvText}
                onChange={(e) => setCvText(e.target.value)}
                placeholder="Paste your full CV/resume text here (min 50 characters)..."
                rows={8}
                required
                minLength={50}
              />
            </label>

            <label>
              Preferred Roles (comma-separated)
              <input
                type="text"
                value={roles}
                onChange={(e) => setRoles(e.target.value)}
                placeholder="Data Scientist, ML Engineer, Backend Developer"
              />
            </label>

            <label>
              Preferred Locations (comma-separated)
              <input
                type="text"
                value={locations}
                onChange={(e) => setLocations(e.target.value)}
                placeholder="Sydney, Melbourne, Remote"
              />
            </label>

            <div className="form-row">
              <label>
                Minimum Salary
                <input
                  type="number"
                  value={salaryMin}
                  onChange={(e) => setSalaryMin(e.target.value)}
                  placeholder="120000"
                />
              </label>

              <label>
                Work Type
                <select value={workType} onChange={(e) => setWorkType(e.target.value)}>
                  <option value="any">Any</option>
                  <option value="remote">Remote</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="onsite">On-site</option>
                </select>
              </label>
            </div>

            <button type="submit" className="btn btn-accent" disabled={mutation.isPending}>
              {mutation.isPending ? "Analyzing..." : "Analyze Profile"}
            </button>

            {mutation.isError && (
              <p className="text-red">Error: {(mutation.error as Error).message}</p>
            )}
          </form>
        </section>

        {/* Profile Display */}
        <section className="panel">
          <h3>Analyzed Profile</h3>
          {profile ? (
            <div className="profile-details">
              <div className="status-row">
                <span>ID</span>
                <code>{profile.candidate_id}</code>
              </div>
              <div className="status-row">
                <span>Name</span>
                <strong>{profile.name}</strong>
              </div>
              <div className="status-row">
                <span>Seniority</span>
                <strong className="capitalize">{profile.seniority}</strong>
              </div>
              <div className="status-row">
                <span>Experience</span>
                <strong>{profile.years_experience} years</strong>
              </div>

              <h4>Skills</h4>
              <div className="tag-list">
                {profile.skills.map((s) => (
                  <span key={s} className="tag">
                    {s}
                  </span>
                ))}
              </div>

              <h4>Domains</h4>
              <div className="tag-list">
                {profile.domains.map((d) => (
                  <span key={d} className="tag tag-domain">
                    {d}
                  </span>
                ))}
              </div>

              <h4>Strengths</h4>
              <ul>
                {profile.strengths.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>

              <h4>Skill Gaps</h4>
              <div className="tag-list">
                {profile.skill_gaps.map((g) => (
                  <span key={g} className="tag tag-gap">
                    {g}
                  </span>
                ))}
              </div>

              {profile.summary && (
                <>
                  <h4>Summary</h4>
                  <p className="summary-text">{profile.summary}</p>
                </>
              )}
            </div>
          ) : (
            <p className="muted">Submit your CV to see your analyzed profile</p>
          )}
        </section>
      </div>
    </div>
  );
}
