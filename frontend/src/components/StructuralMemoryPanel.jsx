import React from "react";

export default function StructuralMemoryPanel({ frame }) {
  const matches = frame?.memory_similarity ?? [];
  return (
    <div className="structural-memory-panel">
      {matches.length === 0 ? (
        <p className="narrative-text">Historical structural memory matches will appear as behavior evidence accumulates.</p>
      ) : (
        matches.map((match) => (
          <div key={match.fingerprint_id ?? match.label} className="structural-memory-panel__match">
            <div className="structural-memory-panel__top">
              <strong>{match.label ?? "Unnamed memory fingerprint"}</strong>
              <span>{Math.round((Number(match.similarity_score) || 0) * 100)}% overlap</span>
            </div>
            <p>{(match.archetypes ?? []).join(", ") || "Archetype overlap developing"}</p>
            <p className="metadata-text">{match.confidence_band ?? "Confidence band unavailable"}</p>
          </div>
        ))
      )}
    </div>
  );
}
