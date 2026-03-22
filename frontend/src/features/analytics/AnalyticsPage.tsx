import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchAnalytics } from "../../api/client";
import type { AnalyticsData } from "../../api/client";

// ── Chart Primitives ──────────────────────────────────────────────────────────

function HBar({
  data,
  labelKey,
  valueKey,
  color = "var(--accent)",
  limit = 12,
}: {
  data: Record<string, unknown>[];
  labelKey: string;
  valueKey: string;
  color?: string;
  limit?: number;
}) {
  const rows = data.slice(0, limit);
  const max = Math.max(...rows.map((d) => d[valueKey] as number), 1);
  return (
    <div className="hbar-chart">
      {rows.map((item, i) => (
        <div key={i} className="hbar-row">
          <div className="hbar-label capitalize">{String(item[labelKey])}</div>
          <div className="hbar-track">
            <div
              className="hbar-fill"
              style={{ width: `${((item[valueKey] as number) / max) * 100}%`, background: color }}
            />
            <span className="hbar-value">{String(item[valueKey])}</span>
          </div>
        </div>
      ))}
      {data.length === 0 && <p className="muted" style={{ fontSize: "0.85rem" }}>No data yet</p>}
    </div>
  );
}

const STATUS_SEGMENT_COLORS: Record<string, string> = {
  applied: "#2980b9",
  interview: "#d4a017",
  offer: "#2e8b57",
  rejected: "#c0392b",
  saved: "#95a5a6",
  withdrawn: "#7f8c8d",
};

function StatusSegmentBar({ data }: { data: { status: string; count: number }[] }) {
  const total = data.reduce((s, d) => s + d.count, 0);
  if (total === 0) return <p className="muted" style={{ fontSize: "0.85rem" }}>No data yet</p>;
  return (
    <div>
      <div style={{ display: "flex", height: 28, borderRadius: 8, overflow: "hidden", gap: 1 }}>
        {data.map((d) => (
          <div
            key={d.status}
            style={{
              width: `${(d.count / total) * 100}%`,
              background: STATUS_SEGMENT_COLORS[d.status] ?? "#bbb",
              minWidth: d.count > 0 ? 2 : 0,
              transition: "width 300ms",
            }}
            title={`${d.status}: ${d.count}`}
          />
        ))}
      </div>
      <div style={{ display: "flex", gap: 14, marginTop: 10, flexWrap: "wrap" }}>
        {data.map((d) => (
          <div key={d.status} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: "0.82rem" }}>
            <div
              style={{
                width: 10, height: 10, borderRadius: 2,
                background: STATUS_SEGMENT_COLORS[d.status] ?? "#bbb",
              }}
            />
            <span className="capitalize">{d.status}</span>
            <strong>{d.count}</strong>
            <span className="muted">({((d.count / total) * 100).toFixed(0)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TimelineChart({ data }: { data: { date: string; count: number }[] }) {
  if (data.length === 0) return <p className="muted" style={{ fontSize: "0.85rem" }}>No data yet</p>;

  const W = 600, H = 180;
  const PAD = { top: 12, right: 16, bottom: 36, left: 32 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const maxCount = Math.max(...data.map((d) => d.count), 1);
  const xStep = data.length > 1 ? plotW / (data.length - 1) : plotW;

  const pts = data.map((d, i) => ({
    x: PAD.left + i * xStep,
    y: PAD.top + plotH - (d.count / maxCount) * plotH,
    label: d.date.slice(5),
    count: d.count,
  }));

  const polyPoints = pts.map((p) => `${p.x},${p.y}`).join(" ");
  const areaPoints = `${pts[0]?.x},${PAD.top + plotH} ${polyPoints} ${pts[pts.length - 1]?.x},${PAD.top + plotH}`;

  // Show max 7 x-axis labels
  const labelStep = Math.ceil(pts.length / 7);

  // Y-axis ticks
  const yTicks = [0, Math.ceil(maxCount / 2), maxCount].filter((v, i, arr) => arr.indexOf(v) === i);

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: "visible" }}>
      {/* Grid lines */}
      {yTicks.map((v) => {
        const y = PAD.top + plotH - (v / maxCount) * plotH;
        return (
          <line key={v} x1={PAD.left} y1={y} x2={PAD.left + plotW} y2={y}
            stroke="var(--border)" strokeDasharray="4,3" />
        );
      })}

      {/* Area fill */}
      {pts.length > 1 && (
        <polygon points={areaPoints} fill="var(--accent)" fillOpacity="0.1" />
      )}

      {/* Line */}
      {pts.length > 1 && (
        <polyline points={polyPoints} fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinejoin="round" />
      )}

      {/* Axes */}
      <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={PAD.top + plotH} stroke="var(--border)" />
      <line x1={PAD.left} y1={PAD.top + plotH} x2={PAD.left + plotW} y2={PAD.top + plotH} stroke="var(--border)" />

      {/* Y labels */}
      {yTicks.map((v) => (
        <text key={v}
          x={PAD.left - 6}
          y={PAD.top + plotH - (v / maxCount) * plotH + 4}
          textAnchor="end" fontSize="10" fill="var(--muted)"
        >
          {v}
        </text>
      ))}

      {/* Data points + X labels */}
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r="4" fill="var(--accent)" />
          {i % labelStep === 0 && (
            <text x={p.x} y={PAD.top + plotH + 14} textAnchor="middle" fontSize="10" fill="var(--muted)">
              {p.label}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

function StatCard({ value, label, color }: { value: string | number; label: string; color?: string }) {
  return (
    <div className="stat-card">
      <span className="stat-card-value" style={{ color: color ?? "var(--ink)" }}>
        {value}
      </span>
      <span className="stat-card-label">{label}</span>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export function AnalyticsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["analytics"],
    queryFn: fetchAnalytics,
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div className="page">
        <h2>Analytics</h2>
        <div className="panel" style={{ marginTop: 16, textAlign: "center", padding: 40 }}>
          <span className="spinner" style={{ display: "inline-block" }} />
          <p className="muted" style={{ marginTop: 12 }}>Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="page">
        <h2>Analytics</h2>
        <div className="panel" style={{ marginTop: 16, textAlign: "center", padding: 40 }}>
          <p className="text-red">Failed to load analytics data.</p>
        </div>
      </div>
    );
  }

  const ov = data.overview;

  if (ov.total === 0) {
    return (
      <div className="page">
        <h2>Analytics</h2>
        <p className="muted">Data-driven insights across all your tracked applications</p>
        <div className="panel" style={{ marginTop: 16, textAlign: "center", padding: "48px 24px" }}>
          <p className="muted" style={{ marginBottom: 20 }}>
            No applications tracked yet. Start logging to unlock insights.
          </p>
          <Link to="/log-application" className="btn btn-accent">
            Log Your First Application
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h2>Analytics</h2>
      <p className="muted">Data-driven insights across {ov.total} tracked application{ov.total !== 1 ? "s" : ""}</p>

      {/* Overview stat cards */}
      <div className="stat-cards" style={{ marginTop: 16 }}>
        <StatCard value={ov.total} label="Total Applications" />
        <StatCard value={`${ov.interview_rate}%`} label="Interview Rate" color="var(--blue)" />
        <StatCard value={`${ov.offer_rate}%`} label="Offer Rate" color="var(--green)" />
        <StatCard value={ov.offer_count} label="Offers" color="var(--green)" />
        <StatCard value={ov.interview_count} label="Interviews" color="var(--blue)" />
        <StatCard value={ov.rejected_count} label="Rejected" color="var(--red)" />
      </div>

      {/* Status distribution */}
      <section className="panel" style={{ marginTop: 16 }}>
        <h3>Status Distribution</h3>
        <StatusSegmentBar data={data.by_status} />
      </section>

      {/* Timeline + Platform */}
      <div className="grid two-col" style={{ marginTop: 16 }}>
        <section className="panel">
          <h3>Applications Over Time</h3>
          <p className="muted" style={{ fontSize: "0.82rem", marginBottom: 12 }}>Grouped by week</p>
          <TimelineChart data={data.timeline} />
        </section>

        <section className="panel">
          <h3>By Platform</h3>
          <HBar
            data={data.by_platform as Record<string, unknown>[]}
            labelKey="platform"
            valueKey="count"
            color="var(--blue)"
          />
        </section>
      </div>

      {/* Industry + Seniority */}
      <div className="grid two-col" style={{ marginTop: 16 }}>
        <section className="panel">
          <h3>By Industry</h3>
          <HBar
            data={data.by_industry as Record<string, unknown>[]}
            labelKey="industry"
            valueKey="count"
            color="var(--accent)"
          />
          {data.by_industry.length === 0 && (
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              Industry data appears when you set the industry field on applications.
            </p>
          )}
        </section>

        <section className="panel">
          <h3>By Work Type</h3>
          <HBar
            data={data.by_remote_type as Record<string, unknown>[]}
            labelKey="remote_type"
            valueKey="count"
            color="#8e44ad"
          />
          {data.by_remote_type.length === 0 && (
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              Work type data appears when you set remote type on applications.
            </p>
          )}
        </section>
      </div>

      {/* Skills Intelligence */}
      {data.skills_frequency.length > 0 && (
        <section className="panel" style={{ marginTop: 16 }}>
          <h3>Most Required Skills</h3>
          <p className="muted" style={{ fontSize: "0.82rem", marginBottom: 12 }}>
            Skills extracted from job descriptions you've logged
          </p>
          <HBar
            data={data.skills_frequency as Record<string, unknown>[]}
            labelKey="skill"
            valueKey="count"
            color="var(--green)"
            limit={15}
          />
        </section>
      )}

      {/* Salary Insights */}
      {(data.salary.avg_min || data.salary.avg_max) && (
        <section className="panel" style={{ marginTop: 16 }}>
          <h3>Salary Insights</h3>
          <div style={{ display: "flex", gap: 24, marginBottom: 16, flexWrap: "wrap" }}>
            {data.salary.avg_min != null && (
              <div>
                <span className="muted" style={{ fontSize: "0.82rem" }}>Avg. Salary Min</span>
                <div style={{ fontWeight: 700, fontSize: "1.3rem", color: "var(--green)" }}>
                  {data.salary.currency} {data.salary.avg_min.toLocaleString()}
                </div>
              </div>
            )}
            {data.salary.avg_max != null && (
              <div>
                <span className="muted" style={{ fontSize: "0.82rem" }}>Avg. Salary Max</span>
                <div style={{ fontWeight: 700, fontSize: "1.3rem", color: "var(--green)" }}>
                  {data.salary.currency} {data.salary.avg_max.toLocaleString()}
                </div>
              </div>
            )}
          </div>
          {data.salary.buckets.length > 0 && (
            <HBar
              data={data.salary.buckets as Record<string, unknown>[]}
              labelKey="range"
              valueKey="count"
              color="var(--green)"
            />
          )}
        </section>
      )}

      {/* Seniority distribution */}
      {data.seniority.length > 0 && (
        <section className="panel" style={{ marginTop: 16 }}>
          <h3>By Seniority Level</h3>
          <HBar
            data={data.seniority as Record<string, unknown>[]}
            labelKey="seniority"
            valueKey="count"
            color="var(--yellow)"
          />
        </section>
      )}
    </div>
  );
}
