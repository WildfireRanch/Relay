// components/SearchPanel.tsx
"use client"

import { useState } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export default function SearchPanel() {
  // Define the expected shape of a knowledge base search result
  type KBResult = {
    path: string
    title: string
    snippet: string
    updated: string
    similarity: number
  }

  // Local state for user query, search results, and loading status
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<KBResult[]>([])
  const [loading, setLoading] = useState(false)

  // Send the query to the FastAPI backend for semantic search
  const search = async () => {
    if (!query.trim()) return
    setLoading(true)
    const res = await fetch("/api/kb/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, k: 5 })
    })
    const data = await res.json()
    setResults(data.results || [])
    setLoading(false)
  }

  return (
    <div className="space-y-4">
      {/* Input field + button */}
      <div className="flex gap-2">
        <Input
          placeholder="Ask a question..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <Button onClick={search} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </Button>
      </div>

      {/* Render results if present */}
      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((r, i) => (
            <div key={i} className="border rounded p-4 text-sm">
              <div className="text-muted-foreground mb-1">
                {r.title} ({r.similarity.toFixed(2)})
              </div>
              <div className="whitespace-pre-wrap">{r.snippet}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}