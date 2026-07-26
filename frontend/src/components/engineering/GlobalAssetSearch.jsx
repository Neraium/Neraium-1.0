import React, { memo, useDeferredValue, useEffect, useId, useMemo, useRef, useState } from "react";

const RECENT_SEARCHES_KEY = "neraium.search.recent";
const MAX_RESULTS = 8;
const MAX_RECENT = 5;

function itemKey(item) {
  return `${item?.type ?? "item"}:${item?.id ?? item?.label ?? "unknown"}`;
}

function readRecentKeys() {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(RECENT_SEARCHES_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string").slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}

function HighlightedText({ value, query }) {
  const text = String(value ?? "");
  const normalized = query.trim().toLowerCase();
  const index = normalized ? text.toLowerCase().indexOf(normalized) : -1;
  if (index < 0) return <>{text}</>;
  return <>{text.slice(0, index)}<mark>{text.slice(index, index + normalized.length)}</mark>{text.slice(index + normalized.length)}</>;
}

function GlobalAssetSearch({ items = [], onSelect }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [recentKeys, setRecentKeys] = useState(readRecentKeys);
  const deferredQuery = useDeferredValue(query);
  const listId = useId();
  const rootRef = useRef(null);
  const inputRef = useRef(null);
  const normalizedQuery = deferredQuery.trim().toLowerCase();

  const matches = useMemo(() => {
    if (!normalizedQuery) return [];
    return items
      .filter((item) => `${item.label} ${item.type} ${item.id}`.toLowerCase().includes(normalizedQuery))
      .slice(0, MAX_RESULTS);
  }, [items, normalizedQuery]);

  const recentItems = useMemo(() => {
    const byKey = new Map(items.map((item) => [itemKey(item), item]));
    return recentKeys.map((key) => byKey.get(key)).filter(Boolean);
  }, [items, recentKeys]);

  const options = normalizedQuery ? matches : recentItems;
  const showPanel = Boolean(open && (normalizedQuery || options.length > 0));

  useEffect(() => {
    function handlePointerDown(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  useEffect(() => {
    setActiveIndex(options.length ? 0 : -1);
  }, [normalizedQuery, options.length]);

  function choose(item) {
    const key = itemKey(item);
    const nextRecent = [key, ...recentKeys.filter((recent) => recent !== key)].slice(0, MAX_RECENT);
    setRecentKeys(nextRecent);
    try {
      window.localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(nextRecent));
    } catch {
      // Search remains fully usable when browser storage is unavailable.
    }
    setQuery(item.label);
    setOpen(false);
    onSelect?.(item);
  }

  function handleKeyDown(event) {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      inputRef.current?.select();
      setOpen(true);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      setActiveIndex(-1);
      return;
    }
    if (!options.length || !["ArrowDown", "ArrowUp", "Enter"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "ArrowDown") setActiveIndex((current) => (current + 1) % options.length);
    if (event.key === "ArrowUp") setActiveIndex((current) => (current <= 0 ? options.length - 1 : current - 1));
    if (event.key === "Enter") choose(options[Math.max(activeIndex, 0)]);
  }

  function clear() {
    setQuery("");
    setOpen(true);
    inputRef.current?.focus();
  }

  return (
    <div className="global-asset-search" role="search" ref={rootRef} onKeyDown={handleKeyDown}>
      <label htmlFor={`${listId}-input`} className="sr-only">Search sites, systems, assets, signals, findings, investigations, or evidence packages</label>
      <span className="global-asset-search__icon" aria-hidden="true" />
      <input
        ref={inputRef}
        id={`${listId}-input`}
        role="combobox"
        aria-autocomplete="list"
        aria-controls={showPanel ? listId : undefined}
        aria-expanded={showPanel}
        aria-activedescendant={activeIndex >= 0 && showPanel ? `${listId}-option-${activeIndex}` : undefined}
        value={query}
        onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="Search sites, systems, signals, findings…"
        autoComplete="off"
      />
      {query ? <button type="button" className="global-asset-search__clear" aria-label="Clear search" onClick={clear}>Clear</button> : <kbd><span className="desktop-shortcut">⌘</span>K</kbd>}
      {showPanel ? (
        <div className="global-asset-search__panel">
          <div className="global-asset-search__panel-label">
            <span>{normalizedQuery ? "Best matches" : "Recent searches"}</span>
            {normalizedQuery && options.length ? <small>{options.length} result{options.length === 1 ? "" : "s"}</small> : null}
          </div>
          {options.length ? (
            <ul id={listId} className="global-asset-search__results" role="listbox" aria-label={normalizedQuery ? "Search results" : "Recent searches"}>
              {options.map((item, index) => (
                <li key={itemKey(item)} role="presentation">
                  <button
                    id={`${listId}-option-${index}`}
                    type="button"
                    role="option"
                    aria-selected={activeIndex === index}
                    aria-label={`${item.type}: ${item.label}`}
                    className={activeIndex === index ? "is-active" : ""}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => choose(item)}
                  >
                    <span>{item.type}</span>
                    <strong><HighlightedText value={item.label} query={normalizedQuery} /></strong>
                    <small><HighlightedText value={item.id} query={normalizedQuery} /></small>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="global-asset-search__empty">No matching site, system, signal, or finding.</p>}
        </div>
      ) : null}
    </div>
  );
}

export default memo(GlobalAssetSearch);
