import React from "react";

function formatTime(value) {
  if (!value) return "Time not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Time not recorded" : parsed.toLocaleString();
}

export default function FindingActivityTimeline({ activity = [], loading = false, error = "" }) {
  return (
    <section className="work-activity" aria-labelledby="work-activity-title">
      <header><span className="work-eyebrow">Team record</span><h2 id="work-activity-title">Activity</h2></header>
      {loading ? <p className="work-muted" role="status">Loading activity…</p>
        : error ? <p className="work-error" role="alert">{error}</p>
          : activity.length ? (
            <ol>
              {activity.map((item, index) => (
                <li key={`${item.version ?? index}-${item.recorded_at ?? item.recordedAt ?? index}`}>
                  <span aria-hidden="true" />
                  <div><strong>{item.label || "Finding updated"}</strong><p>{item.summary || "Workflow details were updated."}</p><small>{item.actor || "Neraium"} · {formatTime(item.recorded_at ?? item.recordedAt)}</small></div>
                </li>
              ))}
            </ol>
          ) : <p className="work-empty-note">No activity has been recorded yet.</p>}
    </section>
  );
}
