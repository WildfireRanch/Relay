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

    try {
      const res = await fetch("/api/ask/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ prompt: query })
      })

      const data = await res.json()
      setResponse(
        data.final_text ||
        data.answer ||
        data.routed_result?.response ||
        data.function_call?.arguments ||
        "No answer."
      )
    } catch (error) {
      setResponse("Error: " + (error instanceof Error ? error.message : "Failed to get response"))
    } finally {
      setLoading(false)
    }
  }

  if (response && typeof response !== "string") {
    console.log("DEBUG 418:", typeof response, response)
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
