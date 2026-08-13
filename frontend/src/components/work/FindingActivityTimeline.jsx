import React from "react";

function formatTime(value) {
  if (!value) return "Time not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Time not recorded" : parsed.toLocaleString();
}

function ActivityContent({ activity, loading, error }) {
  if (loading) return <p className="work-muted" role="status">Loading activity…</p>;
  if (error) return <p className="work-error" role="alert">{error}</p>;
  if (!activity.length) return <p className="work-empty-note">No activity has been recorded yet.</p>;
  return (
    <ol>
      {activity.map((item, index) => (
        <li key={`${item.version ?? index}-${item.recorded_at ?? item.recordedAt ?? index}`}>
          <span aria-hidden="true" />
          <div><strong>{item.label || "Finding updated"}</strong><p>{item.summary || "Workflow details were updated."}</p><small>{item.actor || "Neraium"} · {formatTime(item.recorded_at ?? item.recordedAt)}</small></div>
        </li>
      ))}
    </ol>
  );
}

export default function FindingActivityTimeline({ activity = [], loading = false, error = "", collapsed = false }) {
  if (collapsed) {
    return (
      <details className="work-activity work-progressive-section">
        <summary><span><span className="work-eyebrow">Team record</span><strong>Activity history</strong></span><small>{loading ? "Loading" : `${activity.length} ${activity.length === 1 ? "update" : "updates"}`}</small></summary>
        <div className="work-progressive-section__content"><ActivityContent activity={activity} loading={loading} error={error} /></div>
      </details>
    );
  }
  return (
    <section className="work-activity" aria-labelledby="work-activity-title">
      <header><span className="work-eyebrow">Team record</span><h2 id="work-activity-title">Activity</h2></header>
      <ActivityContent activity={activity} loading={loading} error={error} />
    </section>
  );
}
