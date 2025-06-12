// File: components/SearchPanel.tsx
// Directory: frontend/src/components
// Purpose: UI panel for semantic knowledge base search against the backend API
// Author: [Your Name]
// Last Updated: 2025-06-12

"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api";

// Simulated user/session ID for API calls (replace with real auth in production)
const USER_ID = "bret-demo";

// Data structure for KB search results
export type KBResult = {
  path: string;
  title: string;
  snippet: string;
  updated: string;
  similarity: number;
};

export default function SearchPanel() {
  const [query, setQuery] = useState<string>("");
  const [results, setResults] = useState<KBResult[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Triggers a semantic search against the KB endpoint.
  const search = async () => {
    const q = query.trim();
    if (!q) return;
    if (!API_ROOT) {
      setError("API URL not configured.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_ROOT}/kb/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID,
        },
        body: JSON.stringify({ query: q, k: 5 }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Lint-safe mapping: Use Partial<KBResult> to satisfy ESLint/TS
      const mappedResults: KBResult[] = (data.results || []).map((r: Partial<KBResult>) => ({
        path: r.path ?? (r as { file?: string }).file ?? "",
        title: r.title ?? (r as { file?: string }).file ?? "Untitled",
        snippet: r.snippet ?? "",
        updated: r.updated ?? "",
        similarity: r.similarity ?? (r as { score?: number }).score ?? 0,
      }));
      setResults(mappedResults);
    } catch (err) {
      console.error("Search error:", err);
      setError("Search failed. Check console for details.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Search input and button */}
      <div className="flex gap-2">
        <Input
          placeholder="Ask a question..."
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === "Enter" && search()}
          name="kb-query"
          id="kb-query"
        />
        <Button onClick={search} disabled={loading}>
          {loading ? "⏳ Searching..." : "Search"}
        </Button>
      </div>

      {/* Error message */}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Render results */}
      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((r, idx) => (
            <div key={idx} className="border rounded p-4 text-sm space-y-1">
              <div className="text-muted-foreground">
                <strong>{r.title}</strong> ({typeof r.similarity === "number" ? r.similarity.toFixed(2) : "?"})
              </div>
              <div className="whitespace-pre-wrap">{r.snippet}</div>
              <div className="text-xs text-muted-foreground">Updated: {r.updated}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
