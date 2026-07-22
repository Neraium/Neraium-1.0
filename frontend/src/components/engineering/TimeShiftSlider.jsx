import React, { useEffect, useMemo, useState } from "react";
import DataGapBand from "./DataGapBand";

const QUICK_WINDOWS = [
  { id: "baseline", label: "Now vs learned baseline", offset: 0 },
  { id: "24h", label: "24 hours ago", offset: 24 },
  { id: "3d", label: "3 days ago", offset: 72 },
  { id: "7d", label: "7 days ago", offset: 168 },
];

function timeForOffset(offset) {
  const date = new Date(Date.now() - offset * 60 * 60 * 1000);
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function TimeShiftSlider({ frames = [], gaps = [], value = 0, onChange }) {
  const availableHours = useMemo(() => {
    if (frames.length < 2) return 0;
    const stamps = frames.map((frame) => new Date(frame?.timestamp ?? frame?.timestamp_start ?? "").getTime()).filter(Number.isFinite);
    if (stamps.length >= 2) return Math.max(1, Math.round((Math.max(...stamps) - Math.min(...stamps)) / 3600000));
    return Math.max(1, frames.length - 1);
  }, [frames]);
  const max = availableHours;
  const [liveText, setLiveText] = useState("");
  const selectedFrame = frames.length ? frames[Math.min(frames.length - 1, Math.round((value / max) * (frames.length - 1)))] : null;
  const selectedLabel = useMemo(() => selectedFrame?.timestamp ?? selectedFrame?.timestamp_start ?? (max ? timeForOffset(value) : "Historical range not supplied"), [max, selectedFrame, value]);
  useEffect(() => setLiveText(`Comparison window changed to ${selectedLabel}`), [selectedLabel]);
  function update(next) {
    onChange?.(Math.max(0, Math.min(max, Number(next))));
  }
  return (
    <section className="time-shift" aria-labelledby="time-shift-title">
      <header><div><span className="forensic-kicker">Time shift</span><h2 id="time-shift-title">Compare relationship behavior</h2></div><output htmlFor="relationship-time-slider">{selectedLabel}</output></header>
      <div className="time-shift__quick" role="group" aria-label="Quick comparison windows">
        {QUICK_WINDOWS.filter((item) => item.offset === 0 || item.offset <= max).map((item) => <button type="button" key={item.id} className={value === item.offset ? "is-active" : ""} aria-pressed={value === item.offset} onClick={() => update(item.offset)}>{item.label}</button>)}
        {max ? <button type="button" onClick={() => document.getElementById("relationship-time-slider")?.focus()}>Custom window</button> : null}
      </div>
      <div className="time-shift__track">
        {gaps.map((gap, index) => <span key={gap.id} className="time-shift__gap" style={{ left: `${18 + (index * 23) % 58}%`, width: "9%" }} title={`Data Gap: ${gap.source}`} aria-hidden="true" />)}
        {frames.slice(0, 5).map((frame, index) => <span key={frame.id ?? frame.timestamp ?? index} className="time-shift__change" style={{ left: `${10 + (index * 19) % 80}%` }} title="Important change point" aria-hidden="true" />)}
        <input id="relationship-time-slider" type="range" min="0" max={max || 1} step="1" value={value} disabled={!max} onChange={(event) => update(event.target.value)} aria-label="Relationship comparison time, hours before now" aria-valuetext={selectedLabel} />
      </div>
      <div className="time-shift__axis"><span>Now</span><span>{max ? `${max} hours available` : "History unavailable"}</span></div>
      {gaps.length ? <div className="time-shift__gaps">{gaps.map((gap) => <DataGapBand key={gap.id} gap={gap} compact />)}</div> : null}
      <span className="sr-only" aria-live="polite">{liveText}</span>
    </section>
  );
}
