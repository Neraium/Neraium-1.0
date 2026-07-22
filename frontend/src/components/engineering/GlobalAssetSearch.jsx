import React, { useId, useMemo, useState } from "react";

export default function GlobalAssetSearch({ items = [], onSelect }) {
  const [query, setQuery] = useState("");
  const listId = useId();
  const matches = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return [];
    return items.filter((item) => `${item.label} ${item.type} ${item.id}`.toLowerCase().includes(normalized)).slice(0, 8);
  }, [items, query]);
  function choose(item) {
    setQuery(item.label);
    onSelect?.(item);
  }
  return (
    <div className="global-asset-search" role="search">
      <label htmlFor={`${listId}-input`} className="sr-only">Search sites, systems, assets, signals, findings, investigations, or evidence packages</label>
      <span aria-hidden="true">⌕</span>
      <input id={`${listId}-input`} role="combobox" aria-autocomplete="list" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search site, asset tag, signal, finding, investigation…" autoComplete="off" aria-controls={matches.length ? listId : undefined} aria-expanded={matches.length > 0} />
      {query ? <button type="button" aria-label="Clear search" onClick={() => setQuery("")}>×</button> : <kbd>⌘ K</kbd>}
      {matches.length ? <ul id={listId} className="global-asset-search__results" aria-label="Search results">{matches.map((item) => <li key={`${item.type}-${item.id}`}><button type="button" aria-label={`${item.type}: ${item.label}`} onClick={() => choose(item)}><span>{item.type}</span><strong>{item.label}</strong><small>{item.id}</small></button></li>)}</ul> : null}
      {query && !matches.length ? <p className="global-asset-search__empty">No mapped result matches this search.</p> : null}
    </div>
  );
}
