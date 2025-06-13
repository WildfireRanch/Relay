// File: SearchPanel.tsx
// Directory: frontend/src/components
// Purpose: UI panel for semantic KB search (aligned with GET /kb/search)
// Last Updated: 2025-06-12

"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { API_ROOT, API_KEY } from "@/lib/api"; // expose API_KEY via env

export type KBResult = {
  path: string;
  title: string;
  snippet: string;
  updated: string;
  similarity: number;
};

export default function SearchPanel() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KBResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    const q = query.trim();
    if (!q) return;

    if (!API_ROOT) {
      setError("⚠️ API URL not configured");
      return;
    }
    setError(null);
    setLoading(true);

    try {
      const url = new URL("/kb/search", API_ROOT);
      url.searchParams.set("q", q);
      url.searchParams.set("k", "5");

      const res = await fetch(url.toString(), {
        method: "GET",
        headers: {
          "x-api-key": API_KEY ?? "",       // ✱ guarded route
          Accept: "application/json",
        },
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Backend returns plain array
      const data: KBResult[] = await res.json();
      setResults(data);
    } catch (err) {
      console.error("Search error:", err);
      setError("Search failed – see console");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input
          id="kb-query"
          placeholder="Ask a question…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <Button disabled={loading} onClick={search}>
          {loading ? "⏳" : "Search"}
        </Button>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((r, i) => (
            <div key={i} className="border rounded p-4 text-sm space-y-1">
              <div className="text-muted-foreground">
                <strong>{r.title}</strong>{" "}
                ({r.similarity.toFixed(2)})
              </div>
              <pre className="whitespace-pre-wrap">{r.snippet}</pre>
              <div className="text-xs text-muted-foreground">
                Updated: {r.updated || "—"}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
