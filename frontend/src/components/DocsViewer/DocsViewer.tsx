"use client"

import { useState } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"

export default function DocsViewer() {
  const [query, setQuery] = useState("")
  const [result, setResult] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function searchDocs() {
    if (!query) return
    setLoading(true)
    const res = await fetch("https://relay.wildfireranch.us/docs/search?q=" + encodeURIComponent(query), {
      headers: {
        "X-API-Key": process.env.NEXT_PUBLIC_RELAY_KEY || ""
      }
    })
    const data = await res.json()
    setResult(data.result || "No docs found.")
    setLoading(false)
  }

  return (
    <div className="max-w-xl space-y-4">
      <Textarea
        placeholder="Search your docs..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={loading}
      />
      <Button onClick={searchDocs} disabled={loading || !query}>
        {loading ? "Searching..." : "Search"}
      </Button>
      {result && (
        <div className="bg-muted p-4 rounded text-sm whitespace-pre-wrap border">
          {result}
        </div>
      )}
    </div>
  )
}
