import { useMemo, useState } from "react";

export const ANALYSIS_RECORD_PREVIEW_LIMITS = Object.freeze({
  maxPreviewCharacters: 5000,
  maxDepth: 4,
  maxObjectKeys: 100,
  maxArrayItems: 100,
  maxStringLength: 600,
});

const DEFAULT_FILENAME = "neraium-analysis-record.json";

export function buildAnalysisRecordPreview(payload, limits = ANALYSIS_RECORD_PREVIEW_LIMITS) {
  const state = {
    truncated: false,
    seen: new WeakSet(),
    objectKeys: 0,
    arrayItems: 0,
    stringCharacters: 0,
  };
  const preview = buildPreviewValue(payload ?? null, state, 0, limits);
  const envelope = {
    _preview_type: "truncated_preview",
    _preview_limits: {
      maxPreviewCharacters: limits.maxPreviewCharacters,
      maxDepth: limits.maxDepth,
      maxObjectKeys: limits.maxObjectKeys,
      maxArrayItems: limits.maxArrayItems,
    },
    _preview_truncated: state.truncated,
    payload: preview,
  };
  let text = safeStringify(envelope);
  if (text.length > limits.maxPreviewCharacters) {
    state.truncated = true;
    const suffix = "\n... [truncated preview]";
    text = text.slice(0, Math.max(0, limits.maxPreviewCharacters - suffix.length)) + suffix;
  }
  return {
    text,
    characterCount: text.length,
    truncated: state.truncated,
    limits,
  };
}

export function downloadAnalysisRecordJson(payload, filename = DEFAULT_FILENAME) {
  const json = safeStringify(payload ?? null);
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || DEFAULT_FILENAME;
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(url);
  }
}

export default function AnalysisRecordDetails({
  summary,
  payload,
  fileName = DEFAULT_FILENAME,
  className = "",
}) {
  const [open, setOpen] = useState(false);
  const preview = useMemo(
    () => (open ? buildAnalysisRecordPreview(payload) : null),
    [open, payload],
  );

  return (
    <details className={className} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>{summary}</summary>
      {open ? (
        <div className="analysis-record-preview">
          <div className="analysis-record-preview__header">
            <p>Truncated preview. Download the full JSON to inspect the complete analysis payload.</p>
            <button type="button" className="secondary-command-button" onClick={() => downloadAnalysisRecordJson(payload, fileName)}>
              Download full JSON
            </button>
          </div>
          <pre className="advanced-json" data-testid="analysis-record-preview"><code>{preview.text}</code></pre>
        </div>
      ) : null}
    </details>
  );
}

function buildPreviewValue(value, state, depth, limits) {
  if (value === null || value === undefined) return value ?? null;
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (typeof value === "bigint") return String(value);
  if (typeof value === "string") return previewString(value, state, limits);
  if (typeof value !== "object") return String(value);

  if (state.seen.has(value)) {
    state.truncated = true;
    return "[repeated object omitted]";
  }
  state.seen.add(value);

  if (depth >= limits.maxDepth) {
    state.truncated = true;
    return Array.isArray(value)
      ? { _type: "array", _items: value.length, _omitted: true }
      : { _type: "object", _keys: Object.keys(value).slice(0, 8), _omitted: true };
  }

  if (Array.isArray(value)) {
    const remainingItems = Math.max(0, limits.maxArrayItems - state.arrayItems);
    const take = Math.min(value.length, remainingItems);
    state.arrayItems += take;
    const output = value.slice(0, take).map((item) => buildPreviewValue(item, state, depth + 1, limits));
    if (take < value.length) {
      state.truncated = true;
      output.push({ _omitted_items: value.length - take });
    }
    return output;
  }

  const keys = Object.keys(value);
  const remainingKeys = Math.max(0, limits.maxObjectKeys - state.objectKeys);
  const selectedKeys = keys.slice(0, remainingKeys);
  state.objectKeys += selectedKeys.length;
  const output = {};
  for (const key of selectedKeys) {
    output[key] = buildPreviewValue(value[key], state, depth + 1, limits);
  }
  if (selectedKeys.length < keys.length) {
    state.truncated = true;
    output._omitted_keys = keys.length - selectedKeys.length;
  }
  return output;
}

function previewString(value, state, limits) {
  const remaining = Math.max(0, limits.maxPreviewCharacters - state.stringCharacters);
  const limit = Math.min(limits.maxStringLength, remaining);
  state.stringCharacters += Math.min(value.length, limit);
  if (value.length <= limit) return value;
  state.truncated = true;
  return value.slice(0, limit) + "... [truncated " + (value.length - limit) + " characters]";
}

function safeStringify(value) {
  try {
    return JSON.stringify(value, null, 2) ?? "null";
  } catch (error) {
    return JSON.stringify({
      error: "Analysis record could not be serialized.",
      message: String(error?.message ?? error),
    }, null, 2);
  }
}
