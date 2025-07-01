// File: frontend/src/components/SearchPanel.tsx
// Purpose: Robust, debounced UI panel for semantic KB search (GET /kb/search).
//          Now renders result snippets with SafeMarkdown for readable markdown/code.
// Notes: 2025‑07‑01 – All features preserved; only result snippet rendering is upgraded.

"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { API_ROOT, API_KEY } from "@/lib/api";
import SafeMarkdown from "@/components/SafeMarkdown";
import { toMDString } from "@/lib/toMDString";

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
  const [query, setQuery] = useState<string>("");
  const [results, setResults] = useState<KBResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const controllerRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearDebounce = () => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
  };

  // Core fetch logic
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

    controllerRef.current?.abort();
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
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data: KBResult[] = await res.json();
      const mapped = data.map((r) => ({
        ...r,
        snippet: toMDString(r.snippet),
      }));
      setResults(mapped);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return; // request was cancelled
      }
      console.error("KB search error", err);
      setError((err as Error).message ?? "Search failed");
    } finally {
      setLoading(false);
    }
  };

  // Debounce typing
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setError(null);
      return;
    }

    clearDebounce();
    debounceRef.current = setTimeout(() => fetchResults(query.trim()), DEBOUNCE_MS);

    return () => {
      clearDebounce();
    };
  }, [query]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    clearDebounce();
    fetchResults(query.trim());
  };

  for (const r of results) {
    if (typeof r.snippet !== "string") {
      console.log("DEBUG 418:", typeof r.snippet, r.snippet);
    }
  }

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
              <div className="mb-1">
                <div className="prose prose-neutral dark:prose-invert max-w-none">
                  <SafeMarkdown>{r.snippet}</SafeMarkdown>
                </div>
              </div>
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
