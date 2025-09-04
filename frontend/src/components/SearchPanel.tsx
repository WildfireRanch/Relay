// File: src/components/SearchPanel.tsx
// Purpose: Fast, resilient semantic search UI with debounce, abort, and SafeMarkdown rendering.
// Features:
//  - Debounced input (300ms), AbortController to cancel stale requests
//  - Keyboard focus shortcut: Cmd/Ctrl+K
//  - Uses SafeMarkdown for snippet rendering (XSS-safe)
//  - Tolerates slight API shape drifts (results[] or bare array)
//  - Clean empty/loading/error states; accessible semantics
//  - Small, dependency-free (built on fetch)
//
// Notes:
//  - If your API base differs, change API_BASE or wire NEXT_PUBLIC_RELAY_API.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SafeMarkdown from "@/components/SafeMarkdown";

type KBItem = {
  title?: string;
  snippet?: string;
  score?: number;  // 0..1
  path?: string;   // repo/doc path
};

type KBResponse =
  | { results: KBItem[] }
  | KBItem[];

const API_BASE =
  (process.env.NEXT_PUBLIC_RELAY_API || "").trim() || "/api"; // e.g., "https://relay.wildfireranch.us"

const DEFAULT_K = 8;
const DEBOUNCE_MS = 300;

function normalizeResponse(json: KBResponse): KBItem[] {
  const items = Array.isArray(json) ? json : Array.isArray((json as any).results) ? (json as any).results : [];
  return (items || []).map((it: any) => ({
    title: typeof it?.title === "string" ? it.title : it?.path || "Untitled",
    snippet: typeof it?.snippet === "string" ? it.snippet : "",
    score: typeof it?.score === "number" ? it.score : undefined,
    path: typeof it?.path === "string" ? it.path : undefined,
  }));
}

function toPct(score?: number) {
  if (typeof score !== "number") return "";
  const pct = Math.round(score * 100);
  return `${pct}%`;
}

function viewHref(path?: string) {
  if (!path) return undefined;
  const u = new URL(`${API_BASE}/docs/view`, "http://local"); // base for relative safety
  u.searchParams.set("path", path);
  return u.pathname + u.search; // keep relative for Next routing through /api
}

export default function SearchPanel() {
  const [q, setQ] = useState("");
  const [k, setK] = useState(DEFAULT_K);
  const [rows, setRows] = useState<KBItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);

  const runSearch = useCallback(
    async (query: string, topK: number) => {
      if (!query || query.trim().length < 2) {
        setRows([]);
        setErr(null);
        setLoading(false);
        return;
      }

      // Cancel any in-flight request
      if (abortRef.current) abortRef.current.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      setLoading(true);
      setErr(null);

      try {
        const res = await fetch(`${API_BASE}/kb/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, k: topK }),
          signal: ac.signal,
        });

        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(`KB_SEARCH_${res.status}: ${text.slice(0, 200)}`);
        }

        const json = (await res.json()) as KBResponse;
        setRows(normalizeResponse(json));
      } catch (e: any) {
        if (e?.name === "AbortError") return; // ignore aborted calls
        setErr(e?.message || "Search failed");
        setRows([]);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // Debounce search
  useEffect(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      runSearch(q, k);
    }, DEBOUNCE_MS);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [q, k, runSearch]);

  // Cmd/Ctrl+K to focus
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toLowerCase().includes("mac");
      if ((isMac && e.metaKey && e.key.toLowerCase() === "k") || (!isMac && e.ctrlKey && e.key.toLowerCase() === "k")) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const hasQuery = q.trim().length > 0;
  const empty = !loading && !err && hasQuery && rows.length === 0;

  const header = useMemo(
    () => (
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Semantic Search</span>
          <kbd className="rounded bg-neutral-800/60 px-2 py-0.5 text-xs text-neutral-200 border border-neutral-700">⌘/Ctrl</kbd>
          <span className="text-xs text-neutral-400">+ K</span>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-neutral-400">Top-K</label>
          <input
            type="number"
            min={1}
            max={50}
            value={k}
            onChange={(e) => setK(Math.max(1, Math.min(50, Number(e.target.value) || DEFAULT_K)))}
            className="w-16 rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-100"
          />
        </div>
      </div>
    ),
    [k]
  );

  return (
    <section className="w-full max-w-3xl rounded-2xl border border-neutral-800 bg-neutral-900/60 p-4 shadow-sm">
      {header}

      <div className="mt-3 flex items-center gap-2">
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search your docs…"
          className="flex-1 rounded-md border border-neutral-700 bg-neutral-950 px-3 py-2 text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-sky-600/40"
          aria-label="Search query"
          autoComplete="off"
        />
        <button
          onClick={() => runSearch(q, k)}
          className="rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 hover:bg-neutral-700"
          aria-label="Run search"
        >
          Search
        </button>
      </div>

      {/* Status row */}
      <div className="mt-3 min-h-6 text-sm">
        {loading && <span className="text-neutral-400">Searching…</span>}
        {err && <span className="text-red-400">Error: {err}</span>}
        {empty && <span className="text-neutral-400">No matches. Try refining your query.</span>}
        {!hasQuery && <span className="text-neutral-500">Type 2+ characters to search.</span>}
      </div>

      {/* Results */}
      <ol className="mt-2 space-y-3">
        {rows.map((r, i) => {
          const href = viewHref(r.path);
          return (
            <li key={`${r.path || r.title || "row"}-${i}`} className="rounded-lg border border-neutral-800 bg-neutral-950 p-3">
              <div className="flex justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-neutral-100">{r.title || r.path || "Untitled"}</div>
                  {r.path && <div className="truncate text-xs text-neutral-500">{r.path}</div>}
                </div>
                <div className="shrink-0 text-xs text-neutral-400">{toPct(r.score)}</div>
              </div>

              {r.snippet ? (
                <div className="prose prose-invert mt-2 max-w-none text-sm leading-snug">
                  <SafeMarkdown>{r.snippet}</SafeMarkdown>
                </div>
              ) : null}

              <div className="mt-2 flex items-center gap-2">
                {href && (
                  <a
                    href={href}
                    className="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs text-neutral-100 hover:bg-neutral-700"
                  >
                    Open
                  </a>
                )}
                {r.path && (
                  <button
                    onClick={() => navigator.clipboard.writeText(r.path!)}
                    className="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs text-neutral-100 hover:bg-neutral-700"
                  >
                    Copy Path
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
