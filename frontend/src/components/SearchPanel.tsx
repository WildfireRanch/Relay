// File: SearchPanel.tsx
// Directory: frontend/src/components
// Purpose: Robust, debounced UI panel for semantic KB search (GET /kb/search).
// Notes:
//   • Uses `query` param (canonical) to avoid 422 mismatch.
//   • Debounces keystrokes (400 ms) & cancels stale fetches via AbortController.
//   • Pulls API root/key from @/lib/api; shows config error prominently.
//   • Accessible: form with <label>, aria‑busy, keyboard submit.
//   • Staging/prod ready: handles 401/403 specifically.
// Last Updated: 2025‑06‑13

"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { API_ROOT, API_KEY } from "@/lib/api";

export type KBResult = {
  path: string;
  title: string;
  snippet: string;
  updated: string;
  similarity: number;
};

const DEBOUNCE_MS = 400;
const TOP_K = 5;

export default function SearchPanel() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KBResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<number | null>(null);

  // Core fetch logic (idempotent)
  const fetchResults = async (q: string) => {
    if (!API_ROOT) {
      setError("API URL not configured");
      return;
    }
    if (!API_KEY) {
      setError("API key missing");
      return;
    }
    setError(null);
    setLoading(true);
    controllerRef.current?.abort(); // cancel any in‑flight
    const controller = new AbortController();
    controllerRef.current = controller;

    try {
      const url = new URL("/kb/search", API_ROOT);
      url.searchParams.set("query", q);
      url.searchParams.set("k", String(TOP_K));

      const res = await fetch(url.toString(), {
        method: "GET",
        headers: {
          "x-api-key": API_KEY,
          Accept: "application/json",
        },
        signal: controller.signal,
      });

      if (res.status === 401 || res.status === 403) {
        throw new Error("Unauthorized – check API key / login");
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: KBResult[] = await res.json();
      setResults(data);
    } catch (err: unknown) {
      if ((err as { name?: string }).name === "AbortError") return; // stale request
      console.error("KB search error", err);
      setError((err as Error).message ?? "Search failed");
    } finally {
      setLoading(false);
    }
  };

  // Debounce user typing
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setError(null);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => fetchResults(query.trim()), DEBOUNCE_MS);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [query]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    debounceRef.current && clearTimeout(debounceRef.current);
    fetchResults(query.trim());
  };

  return (
    <div className="space-y-4" aria-busy={loading}>
      <form onSubmit={onSubmit} className="flex gap-2">
        <label htmlFor="kb-query" className="sr-only">
          Search knowledge base
        </label>
        <Input
          id="kb-query"
          placeholder="Ask a question…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" disabled={loading}>
          {loading ? "⏳" : "Search"}
        </Button>
      </form>

      {error ? <p className="text-sm text-red-500">{error}</p> : null}

      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((r, i) => (
            <article key={i} className="border rounded p-4 text-sm space-y-1">
              <header className="text-muted-foreground">
                <strong>{r.title}</strong> ({r.similarity.toFixed(2)})
              </header>
              <pre className="whitespace-pre-wrap">{r.snippet}</pre>
              <footer className="text-xs text-muted-foreground">
                Updated: {r.updated || "—"}
              </footer>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
