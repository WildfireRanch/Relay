// File: src/components/ui/AskAgent/AskAgent.tsx

"use client"

import { useState } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import SafeMarkdown from "@/components/SafeMarkdown"

export default function AskAgent() {
  const [query, setQuery] = useState("")
  const [response, setResponse] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function sendQuery() {
    if (!query) return
    setLoading(true)
    setResponse(null)

    const res = await fetch("https://relay.wildfireranch.us/ask?q=" + encodeURIComponent(query), {
      headers: {
        "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || ""
      }
    })

    const data = await res.json()
    setResponse(
      data.answer ||
      data.function_call?.arguments ||
      "No answer."
    )
    setLoading(false)
  }

  return (
    <div className="max-w-xl space-y-4">
      <Textarea
        placeholder="Ask Echo something..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={loading}
      />
      <Button onClick={sendQuery} disabled={loading || !query}>
        {loading ? "Thinking..." : "Ask Echo"}
      </Button>
      {response && (
        <div className="bg-muted p-4 rounded text-sm whitespace-pre-wrap border">
          <div className="prose prose-neutral dark:prose-invert max-w-none">
            <SafeMarkdown>{response}</SafeMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}
