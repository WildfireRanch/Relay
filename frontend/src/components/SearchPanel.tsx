// File: components/SearchPanel.tsx
// Directory: frontend/src/components
// Purpose: UI panel for semantic knowledge base search against the backend API

"use client"

import { useState } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

// Base API URL from environment
const apiUrl = process.env.NEXT_PUBLIC_API_URL || ""
if (process.env.NODE_ENV === 'development' && !apiUrl) {
  console.error("NEXT_PUBLIC_API_URL is not defined")
}

// Type definition for KB search result
export type KBResult = {
  path: string
  title: string
  snippet: string
  updated: string
  similarity: number
}

export default function SearchPanel() {
  // Component state
  const [query, setQuery] = useState<string>("")
  const [results, setResults] = useState<KBResult[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  /**
   * Trigger a semantic search against the KB endpoint.
   */
  const search = async () => {
    const q = query.trim()
    if (!q) return
    if (!apiUrl) {
      setError("API URL not configured.")
      return
    }
    setError(null)
    setLoading(true)
    try {
      const res = await fetch(`${apiUrl}/kb/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, k: 5 }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setResults(data.results || [])
    } catch (err) {
      console.error("Search error:", err)
      setError("Search failed. Check console for details.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Search input and button */}
      <div className="flex gap-2">
        <Input
          placeholder="Ask a question..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
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
                <strong>{r.title}</strong> ({r.similarity.toFixed(2)})
              </div>
              <div className="whitespace-pre-wrap">{r.snippet}</div>
              <div className="text-xs text-muted-foreground">Updated: {r.updated}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
